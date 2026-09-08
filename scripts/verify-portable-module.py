"""Verify relocation and mpv loading without private environment configuration."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_inventory(bundle):
    inventory = json.loads((bundle / "bundle-inventory.json").read_text(encoding="utf-8"))
    expected = inventory["files"]
    actual = {path.relative_to(bundle).as_posix() for path in bundle.rglob("*") if path.is_file()}
    if actual != set(expected) | {"bundle-inventory.json"}:
        raise ValueError("unexpected or missing bundle files")
    for name, entry in expected.items():
        path = (bundle / name).resolve(strict=True)
        if not path.is_relative_to(bundle.resolve()) or path.stat().st_size != entry["size"] or digest(path) != entry["sha256"]:
            raise ValueError(f"bundle integrity mismatch: {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--mpv", required=True, type=Path)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    report_path = args.report.resolve()
    relocated = report_path.with_suffix("").with_name(report_path.stem + " relocated \u6d4b\u8bd5")
    if report_path.exists() or relocated.exists():
        parser.error("report and relocated test directory must not exist")
    bundle = args.bundle.resolve(strict=True)
    verify_inventory(bundle)
    shutil.copytree(bundle, relocated)
    verify_inventory(relocated)
    environment = dict(os.environ)
    environment.pop("VSSCRIPT_PATH", None)
    environment["PYTHONPATH"] = "Z:/intentionally-invalid-python-path"
    environment["PYTHONHOME"] = "Z:/intentionally-invalid-python-home"
    config = Path(os.environ["APPDATA"]) / "vapoursynth/vapoursynth.toml"
    before = digest(config) if config.exists() else None
    report = {"relocated": str(relocated), "passed": False}
    try:
        runtime = relocated / "runtime"
        python = subprocess.run([str(runtime / "python.exe"), "-I", "-B", "-c",
            "import sys,json,numpy,vapoursynth; from vapoursynth._utils import _has_implicit_config; "
            "assert sys.flags.isolated and sys.dont_write_bytecode and _has_implicit_config(); "
            "print(json.dumps([sys.executable,numpy.__version__]))"], env=environment, cwd=report_path.parent,
            capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        if python.returncode:
            raise RuntimeError(python.stderr.decode("utf-8", errors="replace"))
        report["python"] = python.stdout.decode("utf-8", errors="replace").strip()
        playback = subprocess.run([str(ROOT / ".local/build/mpv_frame_probe.exe"),
            str(args.mpv.resolve(strict=True)), str(args.video.resolve(strict=True)),
            str(ROOT / "tests/portable-pass.vpy"), "null",
            str(runtime / "Lib/site-packages/vapoursynth/vsscript.dll")],
            env=environment, cwd=report_path.parent, capture_output=True, timeout=20,
            creationflags=subprocess.CREATE_NO_WINDOW)
        report.update(exitCode=playback.returncode,
                      stdout=playback.stdout.decode("utf-8", errors="replace"),
                      stderr=playback.stderr.decode("utf-8", errors="replace"))
        if playback.returncode or "DESTROY_COMPLETE" not in report["stdout"] or report["stdout"].count("PORTABLE_RUNTIME_OK") < 3:
            raise RuntimeError("portable mpv lifecycle evidence failed")
        report["userConfigUnchanged"] = before == (digest(config) if config.exists() else None)
        if not report["userConfigUnchanged"]:
            raise RuntimeError("VapourSynth modified user configuration")
        verify_inventory(relocated)
        report["bundleUnchanged"] = True
        report["passed"] = True
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        report["error"] = str(error)
    finally:
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()

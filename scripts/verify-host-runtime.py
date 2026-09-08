"""Exercise actual OpenPlayer windows with a host-owned private runtime copy."""
import argparse
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess

from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parent.parent
helpers = runpy.run_path(str(ROOT / "scripts/verify-portable-module.py"))
verify_inventory, digest = helpers["verify_inventory"], helpers["digest"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--window-smoke", type=Path, required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report_path = args.report.resolve()
    work = report_path.with_suffix(".artifacts")
    if report_path.exists() or work.exists():
        parser.error("report and artifact directory must not exist")
    work.mkdir(parents=True)
    source = work / "package"
    shutil.copytree(args.bundle.resolve(strict=True), source)
    verify_inventory(source)
    conflict = work / "conflict"
    conflict.mkdir()
    inventory = json.loads((source / "bundle-inventory.json").read_text(encoding="utf-8"))
    inventory["metadata"]["smokeConflict"] = True
    (conflict / "bundle-inventory.json").write_text(json.dumps(inventory), encoding="utf-8")
    environment = dict(os.environ)
    environment.pop("VSSCRIPT_PATH", None)
    environment["PYTHONPATH"] = "Z:/unused-python-path"
    environment["PYTHONHOME"] = "Z:/unused-python-home"
    environment["OPENPLAYER_SMOKE_MEDIA"] = str(args.video.resolve(strict=True))
    environment["OPENPLAYER_SMOKE_NATIVE_FILTER"] = str(ROOT / "tests/host-owned-pass.vpy")
    environment["OPENPLAYER_SMOKE_RUNTIME_BUNDLE"] = str(source)
    environment["OPENPLAYER_SMOKE_RUNTIME_CACHE"] = str(work / "cache")
    environment["OPENPLAYER_SMOKE_RUNTIME_CONFLICT"] = str(conflict)
    config = Path(os.environ["APPDATA"]) / "vapoursynth/vapoursynth.toml"
    before = digest(config) if config.exists() else None
    report = {"passed": False, "runs": []}
    try:
        previous = None
        for run in range(2):
            screenshot = work / f"presented-{run}.png"
            environment["OPENPLAYER_SMOKE_SCREENSHOT"] = str(screenshot)
            result = subprocess.run([str(ROOT / ".local/build/mpv_frame_probe.exe"), "--run",
                str(args.window_smoke.resolve(strict=True)), "overlay-alt-f4"],
                cwd=work, env=environment, timeout=40, capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW)
            entry = {"exitCode": result.returncode,
                     "stdout": result.stdout.decode("utf-8", errors="replace"),
                     "stderr": result.stderr.decode("utf-8", errors="replace")}
            report["runs"].append(entry)
            if result.returncode:
                raise RuntimeError("host runtime window run failed")
            for marker in ("PASS: native filter pause", "PASS: maximized fullscreen client/video bounds",
                           "PASS: resize alignment", "PASS: conflicting resident runtime rejected"):
                if marker not in entry["stdout"]:
                    raise RuntimeError(f"missing window evidence: {marker}")
            paths = [line.removeprefix("PASS: host-owned runtime ") for line in entry["stdout"].splitlines()
                     if line.startswith("PASS: host-owned runtime ")]
            if len(paths) != 2 or paths[0] != paths[1]:
                raise RuntimeError("host did not reuse one resident runtime")
            if "HOST_OWNED_RUNTIME_OK" not in entry["stdout"] + entry["stderr"]:
                raise RuntimeError("no embedded host-owned Python evidence")
            cached = Path(paths[0])
            if cached.samefile(source) or not cached.parent.parent.samefile(work / "cache"):
                raise RuntimeError("host loaded the package instead of its own cache")
            verify_inventory(cached)
            if previous is not None and previous.exists():
                raise RuntimeError("previous process runtime was not reclaimed")
            previous = cached
            with Image.open(screenshot) as frame:
                stats = ImageStat.Stat(frame.convert("RGB"))
                if sum(stats.mean) < 3 or max(stats.stddev) < 1:
                    raise RuntimeError("blank presentation screenshot")
                entry["screenshot"] = {"width": frame.width, "height": frame.height, "mean": stats.mean}
        verify_inventory(source)
        if before != (digest(config) if config.exists() else None):
            raise RuntimeError("user VapourSynth configuration changed")
        report.update(passed=True, sourceUnchanged=True, userConfigUnchanged=True, staleRuntimeReclaimed=True)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        report["error"] = str(error)
    finally:
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "runs"}, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()

"""Run the native libmpv lifecycle probe with private VSScript configuration."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from probe_evidence import verify_artifacts


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library", type=Path)
    parser.add_argument("--video", type=Path, default=root / ".local/motion-source.mp4")
    parser.add_argument("--script", type=Path, default=root / "tests/passthrough.vpy")
    parser.add_argument("--vo", default="null")
    parser.add_argument("--window-smoke", type=Path)
    parser.add_argument("--close-target", choices=("main", "overlay", "overlay-alt-f4"), default="overlay")
    parser.add_argument("--verify-frames", action="store_true")
    parser.add_argument("--expect-fallback", action="store_true")
    parser.add_argument("--persistent", action="store_true", help="use an owner-scoped engine across filter rebuilds")
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not 0 < args.timeout <= 60 or args.report.exists():
        parser.error("timeout must be (0,60], report must not exist")
    if args.persistent and args.script.name not in ("dlssnr.vpy", "dlssnr-crash.vpy"):
        parser.error("persistent probe requires a known DLSSNR fixture")
    env = dict(os.environ)
    env["APPDATA"] = str(root / ".local/vs-config")
    env["VSSCRIPT_PATH"] = str(root / ".local/python/vapoursynth/vsscript.dll")
    env["PYTHONPATH"] = str(root / ".local/python") + os.pathsep + str(root)
    env["OPENPLAYER_PROBE_PYTHON"] = sys.executable
    artifacts = args.report.resolve().with_suffix(".frames")
    if artifacts.exists():
        parser.error("artifact directory must not exist")
    artifacts.mkdir(parents=True)
    env["OPENPLAYER_PROBE_ARTIFACTS"] = str(artifacts)
    command = [str(root / ".local/build/mpv_frame_probe.exe"), str(args.library.resolve(strict=True)),
               str(args.video.resolve(strict=True)), str(args.script.resolve(strict=True)), args.vo]
    if args.window_smoke:
        command = [command[0], "--run", str(args.window_smoke.resolve(strict=True)), args.close_target]
        env["OPENPLAYER_SMOKE_MEDIA"] = str(args.video.resolve(strict=True))
        env["OPENPLAYER_SMOKE_NATIVE_FILTER"] = str(args.script.resolve(strict=True))
        env["OPENPLAYER_SMOKE_SCREENSHOT"] = str(artifacts / "presented.png")
    if args.persistent:
        env["OPENPLAYER_PROBE_COMMAND"] = json.dumps(command)
        env["OPENPLAYER_PROBE_FACTORY"] = "crash" if args.script.name == "dlssnr-crash.vpy" else "dlssnr"
        command = [command[0], "--owned-run", sys.executable, str(root / "scripts/owned_native_probe.py")]
    try:
        # The official config helper writes only under this child's private APPDATA.
        configured = subprocess.run(
            [sys.executable, "-c", "from vapoursynth._utils import vapoursynth_config; vapoursynth_config()"],
            env=env, cwd=root, capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        if configured.returncode:
            raise RuntimeError(configured.stderr.decode("utf-8", errors="replace"))
        result = subprocess.run(command, env=env, cwd=root, capture_output=True, timeout=args.timeout,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        code, stdout, stderr = result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as error:
        code, stdout, stderr = 124, error.stdout or b"", error.stderr or b""
    except (OSError, RuntimeError) as error:
        code, stdout, stderr = 10, b"", str(error).encode("utf-8")
    report = {"command": command, "exit_code": code, "timed_out": code == 124,
              "stdout": stdout.decode("utf-8", errors="replace"),
              "stderr": stderr.decode("utf-8", errors="replace")}
    if args.persistent:
        report["playback_command"] = json.loads(env["OPENPLAYER_PROBE_COMMAND"])
    if args.verify_frames or args.expect_fallback or args.script.name == "dlssnr.vpy":
        try:
            report["frame_evidence"] = verify_artifacts(
                artifacts, window=bool(args.window_smoke), expect_fallback=args.expect_fallback,
                expect_reuse=args.persistent)
            report["evidence_passed"] = True
        except (OSError, ValueError, KeyError, TypeError) as error:
            report["evidence_passed"] = False
            report["evidence_error"] = str(error)
            code = code or 9
    report["passed"] = code == 0
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    raise SystemExit(code)


if __name__ == "__main__":
    main()

"""Verify installed native video ownership and recovery in actual OpenPlayer windows."""
import argparse
import json
import os
from pathlib import Path
import runpy
import subprocess
import time

from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parent.parent
helpers = runpy.run_path(str(ROOT / "scripts/verify-portable-module.py"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--window-smoke", required=True, type=Path)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--replacement-video", type=Path)
    parser.add_argument("--normalize-sdr", action="store_true", help="exercise the host's explicit SDR input conversion")
    parser.add_argument("--seek", type=float, default=.2, help="actual in-file seek position for scene inspection")
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--gpu", required=True, help="explicit NVIDIA GPU UUID; never a display ordinal")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--scenario", action="append", choices=["stop", "disable", "upgrade", "uninstall", "crash", "app-exit", "media-change", "detach"])
    args = parser.parse_args()
    if args.scenario and "media-change" in args.scenario and not args.replacement_video:
        parser.error("media-change requires --replacement-video")
    report_path = args.report.resolve()
    work = report_path.with_suffix(".artifacts")
    if report_path.exists() or work.exists():
        parser.error("report and artifact directory must not exist")
    work.mkdir(parents=True)
    bundle = args.bundle.resolve(strict=True)
    helpers["verify_inventory"](bundle)
    environment = {key: value for key, value in os.environ.items()
                   if key != "VSSCRIPT_PATH" and not key.startswith("OPENPLAYER_SMOKE_")}
    environment.update(PYTHONPATH="Z:/unused-python-path", PYTHONHOME="Z:/unused-python-home",
                       OPENPLAYER_SMOKE_MEDIA=str(args.video.resolve(strict=True)),
                       OPENPLAYER_SMOKE_RUNTIME_BUNDLE=str(bundle),
                       OPENPLAYER_SMOKE_FRAME_OPTIONS=json.dumps({"inputConversion": "sdr-bt709" if args.normalize_sdr else "none", "settings": {"gpu_uuid": args.gpu, "intensity": .5}}),
                       OPENPLAYER_SMOKE_NVIDIA_RUNTIME=str(args.runtime.resolve(strict=True)))
    config = Path(os.environ["APPDATA"]) / "vapoursynth/vapoursynth.toml"
    environment["OPENPLAYER_SMOKE_SEEK_SECONDS"] = str(args.seek)
    if args.replacement_video:
        environment["OPENPLAYER_SMOKE_REPLACEMENT_MEDIA"] = str(args.replacement_video.resolve(strict=True))
    before = helpers["digest"](config) if config.exists() else None
    report = {"passed": False, "runs": []}
    try:
        for action in args.scenario or ["stop", "disable", "upgrade", "uninstall", "crash", "app-exit"]:
            directory = work / action
            environment.update(OPENPLAYER_SMOKE_NATIVE_ATTACHMENT=action,
                               OPENPLAYER_SMOKE_ATTACHMENT_WORK=str(directory))
            started = time.monotonic()
            print(f"RUN: {action}", flush=True)
            result = subprocess.run([str(ROOT / ".local/build/mpv_frame_probe.exe"), "--run",
                str(args.window_smoke.resolve(strict=True)), "overlay-alt-f4"],
                cwd=work, env=environment, timeout=40, capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW)
            entry = {"action": action, "exitCode": result.returncode,
                     "elapsedSeconds": round(time.monotonic() - started, 3),
                     "stdout": result.stdout.decode("utf-8", errors="replace"),
                     "stderr": result.stderr.decode("utf-8", errors="replace")}
            report["runs"].append(entry)
            if result.returncode:
                raise RuntimeError(f"{action}: window attachment run failed")
            if "Disabling filter" in entry["stderr"] or "error/vapoursynth" in entry["stderr"]:
                raise RuntimeError(f"{action}: mpv reported a failed filter")
            for marker in ("PASS: registered native frame worker", "PASS: session attachment pause seek",
                           "PASS: maximized fullscreen client/video bounds with native filter",
                           ("PASS: active attachment app exit released filter and native job" if action == "app-exit"
                            else f"PASS: attachment {action} removed owned filter"),
                           "PASS: window smoke process ready to exit",
                           "PASS: resize alignment, fullscreen restore, companion close, mpv teardown"):
                if marker not in entry["stdout"]:
                    raise RuntimeError(f"{action}: missing evidence: {marker}")
            frames = [json.loads(line.removeprefix("HOST_FRAME "))
                      for line in (entry["stdout"] + entry["stderr"]).splitlines()
                      if line.startswith("HOST_FRAME ")]
            if (len(frames) < 2 or any(not frame["processed"] or frame["changedMean"] <= 0 for frame in frames)
                    or len({frame["workerPid"] for frame in frames}) != 1
                    or not any(frame["reused"] for frame in frames)
                    or any((frame.get("device") or {}).get("uuid") != args.gpu for frame in frames)):
                raise RuntimeError(f"{action}: no processed/reused frame evidence")
            entry["frames"] = frames
            entry["screenshots"] = {}
            for name in (("processed.png",) if action == "app-exit" else ("processed.png", "recovered.png")):
                with Image.open(directory / name) as image:
                    stats = ImageStat.Stat(image.convert("RGB"))
                    if sum(stats.mean) < 3 or max(stats.stddev) < 1:
                        raise RuntimeError(f"{action}: blank {name}")
                    entry["screenshots"][name] = {"width": image.width, "height": image.height, "mean": stats.mean}
            if list(directory.glob("native-owned-*.vpy")):
                raise RuntimeError(f"{action}: detached script was not cleaned")
            print(f"PASS: {action} ({entry['elapsedSeconds']}s)", flush=True)
        helpers["verify_inventory"](bundle)
        if before != (helpers["digest"](config) if config.exists() else None):
            raise RuntimeError("user VapourSynth configuration changed")
        report.update(passed=True, sourceUnchanged=True, userConfigUnchanged=True)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        report["error"] = str(error)
        if isinstance(error, subprocess.TimeoutExpired):
            report["timeoutOutput"] = {
                "stdout": (error.stdout or b"").decode("utf-8", errors="replace"),
                "stderr": (error.stderr or b"").decode("utf-8", errors="replace")}
    finally:
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "runs"}, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()

"""Measure the isolated SDR frame path, not OpenPlayer playback performance."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

import numpy as np
from PIL import Image, ImageOps

from dlssnr_backend import DlssnrProcessor
from frame_session import FrameSession


def sha256(path):
    with open(path, "rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    options = {"host": str(args.host.resolve()), "runtime": str(args.runtime.resolve()),
               "log": str(output / "native.log"), "settings": {"intensity": 1.0}}
    report = {
        "scope": "SDR RGBA8 CPU shared memory + GPU upload/inference/readback; not player FPS",
        "width": args.width, "height": args.height, "frames": args.frames,
        "host_sha256": sha256(args.host), "runtime_sha256": sha256(args.runtime),
        "source": str(args.image or args.video), "status": "initializing",
    }
    session = None
    source_process = None
    writer = None
    timings, means, differences, reset_frames = [], [], [], []
    if args.image:
        still = Image.open(args.image).convert("RGBA")
        # Still-image sequences test inference, not optical motion or temporal quality.
        still = np.array(ImageOps.pad(still, (args.width, args.height), color=(0, 0, 0, 255)))
    try:
        if args.video:
            source_process = subprocess.Popen([
                "ffmpeg", "-nostdin", "-v", "error", "-i", str(args.video), "-an",
                "-vf", f"scale={args.width}:{args.height}:force_original_aspect_ratio=decrease,pad={args.width}:{args.height}:(ow-iw)/2:(oh-ih)/2,fps={args.fps}",
                "-frames:v", str(args.frames), "-f", "rawvideo", "-pix_fmt", "rgba", "pipe:1",
            ], stdout=subprocess.PIPE)
        session = FrameSession(args.width, args.height, DlssnrProcessor, options,
                               timeout=10, startup_timeout=45, fallback=False)
        report["startup_ms"] = session.startup_ms
        report["worker_pid"] = session.worker_pid
        if args.encode:
            writer = subprocess.Popen([
                "ffmpeg", "-nostdin", "-v", "error", "-n", "-f", "rawvideo",
                "-pix_fmt", "rgba", "-s", f"{args.width * 2}x{args.height}",
                "-r", str(args.fps), "-i", "pipe:0", "-an", "-c:v", "libx264",
                "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                str(output / "comparison.mp4"),
            ], stdin=subprocess.PIPE)
        for index in range(args.frames):
            if source_process:
                data = source_process.stdout.read(args.width * args.height * 4)
                if len(data) != args.width * args.height * 4:
                    raise RuntimeError(f"video ended before requested frame {index}")
                frame = np.frombuffer(data, np.uint8).reshape((args.height, args.width, 4))
            else:
                frame = still
            reset = index in (0, args.frames // 2)
            started = time.perf_counter()
            processed = session.process(frame, reset=reset)
            timings.append((time.perf_counter() - started) * 1000)
            if reset:
                reset_frames.append(index)
            means.append(float(processed[..., :3].mean()))
            differences.append(float(np.abs(processed[..., :3].astype(np.int16)
                                            - frame[..., :3].astype(np.int16)).mean()))
            if index == 0:
                Image.fromarray(frame).save(output / "input.png")
                Image.fromarray(processed).save(output / "output.png")
                Image.fromarray(np.concatenate((frame, processed), axis=1)).save(output / "comparison.png")
            if writer:
                writer.stdin.write(np.concatenate((frame, processed), axis=1).tobytes())
            print(f"frame {index + 1}/{args.frames}: {timings[-1]:.1f} ms, delta={differences[-1]:.2f}", flush=True)
        if writer:
            writer.stdin.close()
            if writer.wait(timeout=20):
                raise RuntimeError("comparison encoding failed")
        if source_process and source_process.wait(timeout=10):
            raise RuntimeError("source decoding failed")
        # Exercise a live settings change, independently of the steady-state timing samples.
        session.update({"intensity": 0.25})
        updated = session.process(frame)
        Image.fromarray(updated).save(output / "updated.png")
        report["update_delta_from_previous"] = float(np.abs(updated[..., :3].astype(np.int16)
                                                             - processed[..., :3].astype(np.int16)).mean())
        report["status"] = "passed" if min(means) > 0 and max(differences) > 0 else "invalid_output"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        for process in (writer, source_process):
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                for pipe in (process.stdin, process.stdout):
                    if pipe is not None:
                        pipe.close()
        if session:
            started = time.perf_counter()
            session.close()
            report["close_ms"] = (time.perf_counter() - started) * 1000
            report["worker_exitcode"] = session.worker_exitcode
            report["fallback_frames"] = session.fallback_frames
        # Discard initial warm-up only; keep mid-sequence reset costs in the results.
        warm = timings[min(3, len(timings)):]
        report.update({"frame_ms": timings, "reset_frames": reset_frames,
                       "output_rgb_means": means, "mean_absolute_differences": differences})
        if warm:
            report.update({"steady_mean_ms": float(np.mean(warm)),
                           "steady_p95_ms": float(np.percentile(warm, 95)),
                           "processing_fps": 1000 / float(np.mean(warm))})
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in report.items() if not isinstance(v, list)}, indent=2), flush=True)
    if report["status"] != "passed":
        raise RuntimeError("no usable changed output")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--image", type=Path)
    source.add_argument("--video", type=Path, help="SDR test clip only; HDR metadata is not handled")
    parser.add_argument("--host", type=Path, default=Path(".local/build/dlssnr_host_v2.dll"))
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new output directory; never overwritten")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--frames", type=int, default=24)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--encode", action="store_true", help="save silent side-by-side MP4 (original left)")
    args = parser.parse_args()
    if not 4 <= args.frames <= 120 or not 1 <= args.fps <= 60:
        parser.error("frames must be 4..120 and fps 1..60")
    if not 16 <= args.width <= 1920 or not 16 <= args.height <= 1080 or args.width % 2 or args.height % 2:
        parser.error("dimensions must be even, at least 16, and at most 1920x1080")
    run(args)


if __name__ == "__main__":
    main()

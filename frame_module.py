"""Trusted frame owner implementing the existing OpenPlayer native v1 protocol."""
import argparse
import math
import multiprocessing as mp
from pathlib import Path
import statistics
import sys
import time

import numpy as np

from dlssnr_backend import DlssnrProcessor, validate_settings
from frame_client import FrameClient
from frame_service import FrameService
from native_protocol import serve


def validate_frame_rate_probe(probe):
    if not isinstance(probe, dict) or set(probe) != {"width", "height", "frameRate", "speed"}:
        raise ValueError("invalid frame rate probe")
    width, height = probe["width"], probe["height"]
    if type(width) is not int or type(height) is not int or not 16 <= width <= 3840 or not 16 <= height <= 2160:
        raise ValueError("invalid frame rate probe dimensions")
    speed, rate = probe["speed"], probe["frameRate"]
    if type(speed) not in (int, float) or not math.isfinite(speed) or not .01 <= speed <= 100:
        raise ValueError("invalid frame rate probe speed")
    if rate is not None and (type(rate) not in (int, float) or not math.isfinite(rate) or not 0 < rate <= 1000):
        raise ValueError("invalid source frame rate")
    return probe


def rate_from_timings(timings, probe):
    high_cost = statistics.quantiles(timings, n=10, method="inclusive")[8]
    if not math.isfinite(high_cost) or high_cost <= 0:
        raise RuntimeError("invalid frame rate calibration result")
    # Match the live policy's budget, reserving 40% for the rest of the pipeline.
    rate = max(1.0, min(120.0, float(math.floor(.6 / high_cost / probe["speed"] + 1e-9))))
    return max(1.0, min(rate, probe["frameRate"])) if probe["frameRate"] is not None else rate


def calibrate_frame_rate(owner, probe):
    width, height = probe["width"], probe["height"]
    source = [np.zeros((height, width), dtype=np.uint8) for _ in range(3)]
    output = [np.empty((height, width), dtype=np.uint8) for _ in range(3)]
    timings = []
    with FrameClient(owner.endpoint, width, height) as client:
        for index in range(15):
            started = time.perf_counter()
            if not client.process_into(source, output, reset=index == 0):
                raise RuntimeError(client.error or "frame rate calibration failed")
            if index >= 3:
                timings.append(time.perf_counter() - started)
    return rate_from_timings(timings, probe)


def configure_worker_executable():
    if sys.platform == "win32":
        # Use the same private runtime without a console in the SDK's GUI job.
        executable = Path(sys.executable).with_name("pythonw.exe").resolve(strict=True)
        if not executable.is_file():
            raise ValueError("the frame module requires a sibling pythonw.exe")
        mp.set_executable(str(executable))


class FrameModule:
    def __init__(self, options, *, factory=DlssnrProcessor):
        self.options = options
        self.factory = factory
        self.owner = None
        self.frame_rate_probe = None
        self.profiled_frame_rate = None

    def call(self, method, params):
        params = {} if params is None else params
        if not isinstance(params, dict):
            raise ValueError("frame module params must be an object")
        if method == "frames.open":
            if set(params) - {"settings", "adaptive", "frameRateProbe"}:
                raise ValueError("unsupported frame owner options")
            settings = validate_settings(params.get("settings", {"intensity": .5}))
            adaptive = params.get("adaptive", False)
            if type(adaptive) is not bool:
                raise ValueError("adaptive must be boolean")
            probe = validate_frame_rate_probe(params["frameRateProbe"]) if "frameRateProbe" in params else None
            if probe is not None and not adaptive:
                raise ValueError("frame rate probing requires adaptive policy")
            if self.owner is not None and (self.owner.options["settings"] != settings or self.owner.adaptive != adaptive
                                           or self.frame_rate_probe != probe):
                raise ValueError("close the frame owner before changing settings or frame policy")
            if self.owner is None:
                # Calibration starts the worker immediately; otherwise the first frame does.
                self.owner = FrameService(self.factory, {**self.options, "settings": settings}, adaptive=adaptive,
                                          playback_speed=probe["speed"] if probe is not None else 1.0)
                try:
                    self.profiled_frame_rate = calibrate_frame_rate(self.owner, probe) if probe is not None else None
                    self.frame_rate_probe = probe
                except Exception:
                    self.close()
                    raise
            result = {"protocol": "openplayer-frame-experimental-v1", "endpoint": self.owner.endpoint}
            if self.profiled_frame_rate is not None:
                result["frameRateLimit"] = self.profiled_frame_rate
            return result
        if method == "frames.speed":
            if set(params) != {"speed"} or self.owner is None:
                raise ValueError("open the frame owner before updating playback speed")
            self.owner.set_playback_speed(params["speed"])
            return {"speed": self.owner.playback_speed}
        if method == "frames.update":
            try:
                if set(params) != {"settings"} or not params["settings"]:
                    raise ValueError("frames.update requires a non-empty settings patch")
                settings = validate_settings(params["settings"])
                if self.owner is None:
                    raise ValueError("open the frame owner before updating settings")
                return self.owner.update(settings)
            except (ValueError, RuntimeError) as error:
                # Invalid controls must not tear down an otherwise healthy session.
                return {"applied": False, "error": str(error)}
        if params:
            raise ValueError("this frame method takes no parameters")
        if method == "frames.status":
            session = self.owner.session if self.owner else None
            return {"running": self.owner is not None, "workerPid": session.worker_pid if session else None,
                    "device": session.device if session else None,
                    "error": session.error if session else None,
                    "generation": self.owner.generation if self.owner else 0,
                    "revision": self.owner.revision if self.owner else 0,
                    "processedFrames": self.owner.processed_frames if self.owner else 0,
                    "profiledFrameRate": self.profiled_frame_rate,
                    "settings": self.owner.options.get("settings", {}) if self.owner else {}}
        if method == "frames.close":
            self.close()
            return None
        raise ValueError("unknown frame module method")

    def close(self):
        if self.owner is not None:
            self.owner.close()
            self.owner = None
        self.frame_rate_probe = None
        self.profiled_frame_rate = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    configure_worker_executable()
    module = FrameModule({"host": str(args.host.resolve(strict=True)),
                          "runtime": str(args.runtime.resolve(strict=True)),
                          "log": str(args.log.resolve())})
    try:
        serve(sys.stdin.buffer, sys.stdout.buffer, module.call)
    finally:
        module.close()


if __name__ == "__main__":
    main()

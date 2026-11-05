"""Private SDR adapter for a host-owned native frame session, not a public SDK."""
import json
import math
import time
import numpy as np
import vapoursynth as vs

from frame_client import FrameClient


class Processor:
    def __init__(self, source, endpoint):
        self.client = FrameClient(endpoint, source.width, source.height)
        self.last = None
        self.reported = False
        self.cached = None
        self.cost = None
        self.phase = 0.0
        self.adaptive = self.client.adaptive is True
        speed = getattr(self.client, "playback_speed", 1.0)
        self.playback_speed = speed if type(speed) in (int, float) and math.isfinite(speed) and speed > 0 else 1.0
        try:
            duration = float(source.fps_den) / float(source.fps_num)
            self.fallback_duration = duration if math.isfinite(duration) and 1 / 240 <= duration <= 10 else 1 / 60
        except (AttributeError, TypeError, ValueError, ZeroDivisionError):
            self.fallback_duration = 1 / 60

    def _duration(self, frame):
        try:
            duration = float(frame.props["_DurationNum"]) / float(frame.props["_DurationDen"])
            return duration if math.isfinite(duration) and 1 / 240 <= duration <= 10 else self.fallback_duration
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return self.fallback_duration

    def process(self, n, f):
        frame = f
        if frame.props.get("_Transfer", 2) in (16, 18):
            raise ValueError("HDR is not supported by this SDR adapter")
        reset = self.last is None or n != self.last + 1
        duration = self._duration(frame)
        speed = getattr(self.client, "playback_speed", self.playback_speed)
        if type(speed) in (int, float) and math.isfinite(speed) and speed > 0:
            self.playback_speed = speed
        if self.adaptive and not reset and self.cached is not None and self.cost and duration:
            # Match the startup calibration budget, leaving time for the host pipeline.
            self.phase += min(1.0, duration * .6 / (self.cost * self.playback_speed))
            if self.phase < 1.0:
                result = self.cached.copy()
                result.props.clear()
                result.props.update(frame.props)
                self.last = n
                return result
            self.phase -= 1.0
        elif reset:
            self.phase = 0.0
        result = frame.copy()
        source = [np.asarray(frame[channel]) for channel in range(3)]
        output = [np.asarray(result[channel]) for channel in range(3)]
        started = time.perf_counter()
        processed = self.client.process_into(source, output, reset=reset)
        elapsed = time.perf_counter() - started
        if processed and self.adaptive:
            self.cost = elapsed if self.cost is None else self.cost * .8 + elapsed * .2
            self.cached = result
        else:
            self.cached = None
        self.last = n
        if not self.reported:
            changed = float(np.mean([np.abs(dst[::16, ::16].astype(np.int16) -
                                           src[::16, ::16].astype(np.int16)).mean()
                                     for src, dst in zip(source, output)]))
            print("HOST_FRAME " + json.dumps({"processed": processed, "changedMean": changed,
                  "workerPid": self.client.worker_pid, "reused": self.client.reused,
                  "device": self.client.device, "adaptive": self.adaptive,
                  "frameDuration": duration}), flush=True)
            self.reported = True
        return result

    def __del__(self):
        if getattr(self, "client", None) is not None:
            self.client.close()
            self.client = None


def create_filter(source, endpoint):
    if (source.format is None or source.width > 3840 or source.height > 2160
            or source.format.bits_per_sample != 8 or source.format.color_family != vs.YUV):
        raise ValueError("adapter requires constant 8-bit SDR YUV up to 3840x2160; convert HDR before attachment")
    rgb = vs.core.resize.Bicubic(source, format=vs.RGB24, matrix_in_s="709", range_in_s="limited")
    processor = Processor(source, endpoint)
    result = vs.core.std.ModifyFrame(rgb, clips=rgb, selector=processor.process)
    return vs.core.resize.Bicubic(result, format=source.format.id, matrix_s="709", range_s="limited")

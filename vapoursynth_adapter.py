"""Experimental SDR frame adapter, used by the native mpv probe only."""
import json
import multiprocessing
import os
from pathlib import Path
import time

import numpy as np
import vapoursynth as vs

from dlssnr_backend import DlssnrProcessor
from frame_session import FrameSession
from frame_client import FrameClient


class FrameProcessor:
    def __init__(self, width, height, root, factory):
        self.session = None
        self.root = root
        self.artifacts = Path(os.environ["OPENPLAYER_PROBE_ARTIFACTS"])
        self.id = f"{os.getpid()}-{time.time_ns()}"
        self.count = 0
        self.last = None
        self.owner_managed = "OPENPLAYER_FRAME_ENDPOINT" in os.environ
        self.planar = self.owner_managed and os.environ.get("OPENPLAYER_PROBE_PLANAR") == "1"
        python = os.environ.get("OPENPLAYER_PROBE_PYTHON")
        if not python:
            raise RuntimeError("OPENPLAYER_PROBE_PYTHON must point to the private Python runtime")
        multiprocessing.set_executable(python)
        options = {
            "host": str(root / ".local/build/dlssnr_host_v2.dll"),
            "runtime": str(root / ".local/runtime/nvngx_dlssnr.dll"),
            "log": str(self.artifacts / f"{self.id}-native.log"),
            "settings": {"intensity": 0.5},
        }
        if self.owner_managed:
            self.session = FrameClient(json.loads(os.environ["OPENPLAYER_FRAME_ENDPOINT"]), width, height)
        else:
            self.session = FrameSession(width, height, factory, options, timeout=0.5, startup_timeout=15)
        self.log("start", width=width, height=height, worker_pid=self.session.worker_pid,
                 startup_ms=self.session.startup_ms, owner_managed=self.owner_managed,
                 generation=getattr(self.session, "generation", None),
                 engine=getattr(self.session, "engine", None),
                 reused=getattr(self.session, "reused", False),
                 attach_ms=getattr(self.session, "attach_ms", self.session.startup_ms))

    def log(self, event, **fields):
        with (self.artifacts / "events.jsonl").open("a", encoding="utf-8") as out:
            out.write(json.dumps({"session": self.id, "event": event, **fields}) + "\n")

    def process(self, n, f):
        frame = f
        if frame.props.get("_Transfer", 2) in (16, 18):
            raise ValueError("HDR input is not supported by this SDR probe")
        started = time.perf_counter()
        if self.planar:
            return self.process_planar(n, frame, started)
        rgba = np.empty((frame.height, frame.width, 4), dtype=np.uint8)
        for channel in range(3):
            rgba[:, :, channel] = np.asarray(frame[channel])
        rgba[:, :, 3] = 255
        reset = self.last is None or n != self.last + 1
        output = self.session.process(rgba, reset=reset)
        result = frame.copy()
        for channel in range(3):
            np.copyto(np.asarray(result[channel]), output[:, :, channel])
        self.count += 1
        self.last = n
        if self.count == 1:
            from PIL import Image
            Image.fromarray(rgba).save(self.artifacts / f"{self.id}-input.png")
            Image.fromarray(output).save(self.artifacts / f"{self.id}-output.png")
        self.log("frame", n=n, reset=reset, mean=float(output[:, :, :3].mean()),
                 changed_mean=float(np.abs(output.astype(np.int16) - rgba.astype(np.int16)).mean()),
                 elapsed_ms=(time.perf_counter() - started) * 1000, fallback=self.session.error)
        return result

    def process_planar(self, n, frame, started):
        result = frame.copy()
        source = [np.asarray(frame[channel]) for channel in range(3)]
        output = [np.asarray(result[channel]) for channel in range(3)]
        reset = self.last is None or n != self.last + 1
        self.session.process_into(source, output, reset=reset)
        processing_ms = (time.perf_counter() - started) * 1000
        self.count += 1
        self.last = n
        if self.count == 1:
            from PIL import Image
            Image.fromarray(np.stack(source, axis=2)).save(self.artifacts / f"{self.id}-input.png")
            Image.fromarray(np.stack(output, axis=2)).save(self.artifacts / f"{self.id}-output.png")
        # Diagnostic sampling stays off the full-frame copy path. Presentation
        # screenshots and transport unit tests still check complete images.
        samples = [plane[::16, ::16] for plane in output]
        changes = [np.abs(out.astype(np.int16) - src[::16, ::16].astype(np.int16)).mean()
                   for out, src in zip(samples, source)]
        self.log("frame", n=n, reset=reset, mean=float(np.mean([plane.mean() for plane in samples])),
                 changed_mean=float(np.mean(changes)), pixel_sampling=16,
                 processing_ms=processing_ms, elapsed_ms=(time.perf_counter() - started) * 1000,
                 fallback=self.session.error)
        return result

    def __del__(self):
        try:
            if self.session is not None:
                self.session.close()
                self.log("close", frames=self.count, worker_exitcode=self.session.worker_exitcode,
                         owner_managed=self.owner_managed)
        except Exception:
            # Teardown must not raise into the filter engine during unwinding.
            pass


def create_filter(source, *, factory=DlssnrProcessor):
    root = Path(__file__).resolve().parent
    if source.width > 1920 or source.height > 1080 or source.format.bits_per_sample != 8 or source.format.color_family != vs.YUV:
        raise ValueError("probe is limited to 1080p 8-bit SDR YUV")
    core = vs.core
    rgb = core.resize.Bicubic(source, format=vs.RGB24, matrix_in_s="709", range_in_s="limited")
    processor = FrameProcessor(source.width, source.height, root, factory)
    processed = core.std.ModifyFrame(rgb, clips=rgb, selector=processor.process)
    return core.resize.Bicubic(processed, format=source.format.id, matrix_s="709", range_s="limited")

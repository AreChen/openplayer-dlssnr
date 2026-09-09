"""Private SDR adapter for a host-owned native frame session, not a public SDK."""
import json
import numpy as np
import vapoursynth as vs

from frame_client import FrameClient


class Processor:
    def __init__(self, source, endpoint):
        self.client = FrameClient(endpoint, source.width, source.height)
        self.last = None
        self.reported = False

    def process(self, n, f):
        frame = f
        if frame.props.get("_Transfer", 2) in (16, 18):
            raise ValueError("HDR is not supported by this SDR adapter")
        result = frame.copy()
        source = [np.asarray(frame[channel]) for channel in range(3)]
        output = [np.asarray(result[channel]) for channel in range(3)]
        processed = self.client.process_into(source, output, reset=self.last is None or n != self.last + 1)
        self.last = n
        if not self.reported:
            changed = float(np.mean([np.abs(dst[::16, ::16].astype(np.int16) -
                                           src[::16, ::16].astype(np.int16)).mean()
                                     for src, dst in zip(source, output)]))
            print("HOST_FRAME " + json.dumps({"processed": processed, "changedMean": changed,
                  "workerPid": self.client.worker_pid, "reused": self.client.reused,
                  "device": self.client.device}), flush=True)
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

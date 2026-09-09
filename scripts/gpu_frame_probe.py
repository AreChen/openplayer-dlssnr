"""Headless, explicitly selected GPU test; run in mpv_frame_probe's kill-on-close job."""
import hashlib
import json
import os
from pathlib import Path

import numpy as np
from bundled_frame_module import BundledModule
from frame_client import FrameClient
from frame_module import configure_worker_executable
from gpu_devices import normalize_uuid


def main():
    configure_worker_executable()
    root = Path(os.environ["OPENPLAYER_GPU_BUNDLE"]).resolve(strict=True)
    runtime = Path(os.environ["OPENPLAYER_GPU_RUNTIME"]).resolve(strict=True)
    gpu = normalize_uuid(os.environ["OPENPLAYER_GPU_UUID"])
    with runtime.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    module = BundledModule(root, Path(os.devnull))
    try:
        devices = module.call("devices.list", None)
        if not any(device["uuid"] == gpu for device in devices):
            raise RuntimeError("requested device is not present")
        module.call("runtime.configure", {"path": str(runtime), "sha256": digest})
        reply = module.call("frames.open", {"settings": {"gpu_uuid": gpu, "intensity": .5}})
        source = np.random.default_rng(7).integers(0, 256, (720, 1280, 4), np.uint8)
        source[:, :, 3] = 255
        runs = []
        for _ in range(2):
            with FrameClient(reply["endpoint"], 1280, 720) as client:
                if client.device is None or client.device["uuid"] != gpu:
                    raise RuntimeError("worker did not confirm selected GPU")
                output = client.process(source, reset=True)
                changed = float(np.abs(source.astype(np.int16) - output.astype(np.int16)).mean())
                if client.error or changed <= 0 or output[:, :, :3].mean() <= 1:
                    raise RuntimeError(f"frame processing failed: {client.error}")
                runs.append({"workerPid": client.worker_pid, "reused": client.reused,
                             "device": client.device, "changedMean": changed})
        if runs[0]["workerPid"] != runs[1]["workerPid"] or not runs[1]["reused"]:
            raise RuntimeError("same-GPU worker was not reused")
        module.call("frames.close", None)
        if module.call("frames.status", None)["running"]:
            raise RuntimeError("owner remained running")
        report = {"passed": True, "runs": runs}
        with Path(os.environ["OPENPLAYER_GPU_REPORT"]).open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
        print(json.dumps(report), flush=True)
    finally:
        module.close()


if __name__ == "__main__":
    main()

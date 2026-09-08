"""Test-only full-frame client for the host's native SDK lifecycle integration test."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from frame_client import FrameClient


def main():
    endpoint = json.loads(sys.stdin.buffer.readline(4097))
    source = np.empty((720, 1280, 4), np.uint8)
    source[:, :, 0] = np.arange(1280, dtype=np.uint16)[None, :] % 256
    source[:, :, 1] = np.arange(720, dtype=np.uint16)[:, None] % 256
    source[:, :, 2] = 100
    source[:, :, 3] = 255
    with FrameClient(endpoint, 1280, 720) as client:
        result = client.process(source)
        if client.error or result[:, :, :3].mean() < 1:
            raise RuntimeError(client.error or "black processed frame")
        print(json.dumps({"workerPid": client.worker_pid, "mean": float(result[:, :, :3].mean())}))


if __name__ == "__main__":
    main()

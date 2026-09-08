"""Owner lifetime fixture, launched inside mpv_frame_probe's kill-on-close job."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dlssnr_backend import DlssnrProcessor
from frame_service import FrameService
from probe_faults import ExitAfterFourFrames


def main():
    artifacts = Path(os.environ["OPENPLAYER_PROBE_ARTIFACTS"])

    def log(event, **fields):
        with (artifacts / "owner-events.jsonl").open("a", encoding="utf-8") as output:
            output.write(json.dumps({"event": event, **fields}) + "\n")

    factory = {"dlssnr": DlssnrProcessor, "crash": ExitAfterFourFrames}[os.environ["OPENPLAYER_PROBE_FACTORY"]]
    with FrameService(factory, {
        "host": str(ROOT / ".local/build/dlssnr_host_v2.dll"),
        "runtime": str(ROOT / ".local/runtime/nvngx_dlssnr.dll"),
        "log": str(artifacts / "owner-native.log"),
        "settings": {"intensity": 0.5},
    }, log=log) as owner:
        env = dict(os.environ)
        env["OPENPLAYER_FRAME_ENDPOINT"] = json.dumps(owner.endpoint)
        result = subprocess.run(json.loads(env["OPENPLAYER_PROBE_COMMAND"]), env=env,
                                stdin=subprocess.DEVNULL, stdout=sys.stdout, stderr=sys.stderr,
                                timeout=40, creationflags=subprocess.CREATE_NO_WINDOW)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())

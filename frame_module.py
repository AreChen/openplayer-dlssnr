"""Trusted frame owner implementing the existing OpenPlayer native v1 protocol."""
import argparse
import multiprocessing as mp
from pathlib import Path
import sys

from dlssnr_backend import DlssnrProcessor, validate_settings
from frame_service import FrameService
from native_protocol import serve


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

    def call(self, method, params):
        params = {} if params is None else params
        if not isinstance(params, dict):
            raise ValueError("frame module params must be an object")
        if method == "frames.open":
            if set(params) - {"settings"}:
                raise ValueError("unsupported frame owner options")
            settings = validate_settings(params.get("settings", {"intensity": .5}))
            if self.owner is not None and self.owner.options["settings"] != settings:
                raise ValueError("close the frame owner before changing settings")
            if self.owner is None:
                # Engine startup runs on first frame attachment, outside the SDK RPC.
                self.owner = FrameService(self.factory, {**self.options, "settings": settings})
            return {"protocol": "openplayer-frame-experimental-v1", "endpoint": self.owner.endpoint}
        if params:
            raise ValueError("this frame method takes no parameters")
        if method == "frames.status":
            session = self.owner.session if self.owner else None
            return {"running": self.owner is not None, "workerPid": session.worker_pid if session else None,
                    "device": session.device if session else None,
                    "error": session.error if session else None,
                    "generation": self.owner.generation if self.owner else 0}
        if method == "frames.close":
            self.close()
            return None
        raise ValueError("unknown frame module method")

    def close(self):
        if self.owner is not None:
            self.owner.close()
            self.owner = None


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

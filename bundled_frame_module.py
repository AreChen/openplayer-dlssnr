"""Relocatable native entry point. NVIDIA's runtime is explicitly user-supplied."""
import hashlib
import os
from pathlib import Path
import sys

from frame_module import FrameModule, configure_worker_executable
from native_protocol import serve


class BundledModule:
    def __init__(self, root, log, *, module_factory=FrameModule):
        self.root = root
        self.log = log
        self.module_factory = module_factory
        self.module = None

    def call(self, method, params):
        if method == "runtime.inspect":
            if not isinstance(params, dict) or set(params) != {"path"}:
                raise ValueError("runtime.inspect requires a local path")
            path, digest = inspect_runtime(params["path"])
            return {"path": str(path), "sha256": digest}
        if method == "devices.list":
            if params not in (None, {}):
                raise ValueError("devices.list takes no parameters")
            from gpu_devices import list_devices
            return list_devices()
        if method == "runtime.configure":
            if (not isinstance(params, dict) or set(params) != {"path", "sha256"}
                    or not isinstance(params["path"], str) or not isinstance(params["sha256"], str)
                    or len(params["sha256"]) != 64
                    or any(c not in "0123456789abcdefABCDEF" for c in params["sha256"])):
                raise ValueError("runtime.configure requires an explicit local path and SHA256")
            path, digest = inspect_runtime(params["path"])
            if digest != params["sha256"].lower():
                raise ValueError("runtime integrity mismatch")
            if self.module is not None:
                self.module.close()
            self.module = self.module_factory({"host": str(self.root / "native/dlssnr_host_v2.dll"),
                                               "runtime": str(path), "log": str(self.log)})
            return {"configured": True, "sha256": digest}
        if self.module is None:
            if method == "frames.status" and (params is None or params == {}):
                return {"running": False, "runtimeConfigured": False}
            raise ValueError("configure an authorized local runtime before opening frames")
        return self.module.call(method, params)

    def close(self):
        if self.module is not None:
            self.module.close()
            self.module = None


def inspect_runtime(value):
    if not isinstance(value, str):
        raise ValueError("runtime path must be a string")
    path = Path(value)
    if not path.is_absolute() or path.name.lower() != "nvngx_dlssnr.dll":
        raise ValueError("select an absolute nvngx_dlssnr.dll path")
    path = path.resolve(strict=True)
    if not path.is_file() or not 0 < path.stat().st_size <= 256 * 1024 * 1024:
        raise ValueError("invalid runtime file size")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return path, digest


def main():
    configure_worker_executable()
    # Forced job termination cannot run finally blocks. Do not create persistent
    # logs or temporary directories outside the host's managed plugin storage.
    module = BundledModule(Path(__file__).resolve().parent.parent, Path(os.devnull))
    try:
        serve(sys.stdin.buffer, sys.stdout.buffer, module.call)
    finally:
        module.close()


if __name__ == "__main__":
    main()

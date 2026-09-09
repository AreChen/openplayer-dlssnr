"""Adapter to the pinned DLSS5Tool engine; imported only in the worker."""

import math
import ctypes
from pathlib import Path
import sys
from gpu_devices import normalize_uuid, resolve_device


def validate_settings(settings):
    supported = {"style", "intensity", "local_tone", "local_struct", "skin_struct", "use_auto_mask", "gpu_uuid"}
    if not isinstance(settings, dict) or set(settings) - supported:
        raise ValueError("unsupported DLSSNR setting")
    for key, value in settings.items():
        if key == "gpu_uuid":
            normalize_uuid(value)
        elif key == "style":
            if type(value) is not int or value not in (0, 1, 2):
                raise ValueError("style must be 0, 1 or 2")
        elif key == "use_auto_mask":
            if type(value) is not bool:
                raise ValueError("use_auto_mask must be boolean")
        elif type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"{key} must be finite and between 0 and 1")
    result = dict(settings)
    if "gpu_uuid" in result:
        result["gpu_uuid"] = normalize_uuid(result["gpu_uuid"])
    return result


class DlssnrProcessor:
    def __init__(self, width, height, options):
        root = Path(__file__).resolve().parent
        settings = validate_settings(options.get("settings", {}))
        host = Path(options["host"]).resolve(strict=True)
        runtime = Path(options["runtime"]).resolve(strict=True)
        log = Path(options["log"]).resolve()
        self.gpu_uuid = settings.pop("gpu_uuid", None)
        self.device = resolve_device(self.gpu_uuid) if self.gpu_uuid else None
        library = ctypes.CDLL(str(host))
        if self.device is not None:
            if not hasattr(library, "dlssnr_select_adapter"):
                raise RuntimeError("native host cannot honor explicit GPU selection")
            library.dlssnr_select_adapter.argtypes = [ctypes.c_uint32, ctypes.c_int32, ctypes.c_int]
            library.dlssnr_select_adapter.restype = ctypes.c_int
            luid = int(self.device["luid"], 16)
            if not library.dlssnr_select_adapter(luid & 0xffffffff, luid >> 32, 1):
                raise RuntimeError("cannot change GPU while the native device is active")
        sys.path.insert(0, str(root / "third_party" / "DLSS5Tool"))
        import dlss_engine

        dlss_engine.HOST_DLL_V2 = str(host)
        dlss_engine.DLSSNR_DLL = str(runtime)
        dlss_engine.LOG_PATH = str(log)
        self._live = dlss_engine.Live(width, height, {
            "host_backend": "v2", "host_auto_fallback": False,
            "host_in_flight": 1, "frame_format": "rgba8", "color_profile": "srgb",
            **settings,
        })
        if self.device is not None:
            library.dlssnr_adapter_luid.argtypes = []
            library.dlssnr_adapter_luid.restype = ctypes.c_uint64
            if library.dlssnr_adapter_luid() != int(self.device["luid"], 16):
                raise RuntimeError("native D3D12 device does not match selected GPU")

    def process(self, frame, reset=False):
        return self._live.process(frame, reset=reset)

    def update(self, settings):
        settings = validate_settings(settings)
        if settings.pop("gpu_uuid", self.gpu_uuid) != self.gpu_uuid:
            raise ValueError("close the frame owner before selecting another GPU")
        self._live.update(settings)

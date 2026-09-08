"""Adapter to the pinned DLSS5Tool engine; imported only in the worker."""

import math
from pathlib import Path
import sys


def validate_settings(settings):
    supported = {"style", "intensity", "local_tone", "local_struct", "skin_struct", "use_auto_mask"}
    if not isinstance(settings, dict) or set(settings) - supported:
        raise ValueError("unsupported DLSSNR setting")
    for key, value in settings.items():
        if key == "style":
            if type(value) is not int or value not in (0, 1, 2):
                raise ValueError("style must be 0, 1 or 2")
        elif key == "use_auto_mask":
            if type(value) is not bool:
                raise ValueError("use_auto_mask must be boolean")
        elif type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"{key} must be finite and between 0 and 1")
    return dict(settings)


class DlssnrProcessor:
    def __init__(self, width, height, options):
        root = Path(__file__).resolve().parent
        settings = validate_settings(options.get("settings", {}))
        host = Path(options["host"]).resolve(strict=True)
        runtime = Path(options["runtime"]).resolve(strict=True)
        log = Path(options["log"]).resolve()
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

    def process(self, frame, reset=False):
        return self._live.process(frame, reset=reset)

    def update(self, settings):
        self._live.update(validate_settings(settings))

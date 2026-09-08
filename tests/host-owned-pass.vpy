import sys
from pathlib import Path

import vapoursynth
from vapoursynth._utils import _has_implicit_config

assert sys.flags.isolated and sys.dont_write_bytecode
assert _has_implicit_config()
prefix = Path(sys.executable).parent
assert prefix.name == "runtime" and prefix.parent.name == "content"
assert prefix.parent.parent.name.startswith("runtime-")
print("HOST_OWNED_RUNTIME_OK", ascii(sys.executable), flush=True)
video_in.set_output()

import sys
from pathlib import Path

import vapoursynth as vs
from vapoursynth._utils import _has_implicit_config

assert sys.flags.isolated, "embedded Python must ignore the host environment"
assert sys.dont_write_bytecode, "embedded Python must not modify the runtime bundle"
assert _has_implicit_config(), "VSScript must locate the sibling Python without user config"
assert Path(sys.executable).with_name("python312._pth").is_file()
print("PORTABLE_RUNTIME_OK", ascii(sys.executable), flush=True)
video_in.set_output()

from probe_faults import ExitAfterFourFrames
from vapoursynth_adapter import create_filter

create_filter(video_in, factory=ExitAfterFourFrames).set_output()

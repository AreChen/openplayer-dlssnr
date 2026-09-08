"""Opt-in native probe fault fixture; never selected by the normal adapter."""
import os

from dlssnr_backend import DlssnrProcessor


class ExitAfterFourFrames(DlssnrProcessor):
    def __init__(self, width, height, options):
        super().__init__(width, height, options)
        self.frames = 0

    def process(self, frame, *, reset=False):
        self.frames += 1
        if self.frames == 5:
            os._exit(89)
        return super().process(frame, reset=reset)

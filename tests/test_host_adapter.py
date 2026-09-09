import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np


class Frame:
    def __init__(self):
        self.planes = [np.full((16, 16), 50, dtype=np.uint8) for _ in range(3)]
        self.props = {"_Transfer": 1, "_DurationNum": 1, "_DurationDen": 24}

    def __getitem__(self, channel):
        return self.planes[channel]

    def copy(self):
        frame = Frame()
        frame.planes = [plane.copy() for plane in self.planes]
        frame.props = self.props.copy()
        return frame


class HostAdapterTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("host_adapter_test",
                    Path(__file__).resolve().parent.parent / "host_vapoursynth.py")
        self.adapter = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", {"vapoursynth": SimpleNamespace(YUV="yuv")}):
            spec.loader.exec_module(self.adapter)

    def test_preserves_properties_and_resets_on_discontinuity(self):
        client = Mock(worker_pid=1, reused=False, device=None)
        def process(source, output, *, reset):
            for src, dst in zip(source, output):
                np.copyto(dst, src)
            return False
        client.process_into.side_effect = process
        frame = Frame()
        with patch.object(self.adapter, "FrameClient", return_value=client), patch("builtins.print"):
            processor = self.adapter.Processor(SimpleNamespace(width=16, height=16), {})
            for n in (0, 1, 9):
                output = processor.process(n=n, f=frame)
                self.assertEqual(output.props, frame.props)
                np.testing.assert_array_equal(output[0], frame[0])
        self.assertEqual([call.kwargs["reset"] for call in client.process_into.call_args_list], [True, False, True])
        processor.__del__()
        client.close.assert_called_once()

    def test_hdr_rejected_before_processing(self):
        client = Mock()
        with patch.object(self.adapter, "FrameClient", return_value=client):
            processor = self.adapter.Processor(SimpleNamespace(width=16, height=16), {})
            frame = Frame()
            frame.props["_Transfer"] = 16
            with self.assertRaises(ValueError):
                processor.process(n=0, f=frame)
            client.process_into.assert_not_called()

    def test_variable_format_rejected_before_client(self):
        with patch.object(self.adapter, "FrameClient") as client:
            with self.assertRaises(ValueError):
                self.adapter.create_filter(SimpleNamespace(format=None), {})
            client.assert_not_called()

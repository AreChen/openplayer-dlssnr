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

    def test_adaptive_rate_repeats_enhanced_frames_and_preserves_current_properties(self):
        client = Mock(worker_pid=1, reused=False, device=None, adaptive=True)
        def process(source, output, *, reset):
            for dst in output:
                dst.fill(120)
            return True
        client.process_into.side_effect = process
        ticks = iter(value for n in range(100) for value in (n, n + .02))
        with patch.object(self.adapter, "FrameClient", return_value=client), \
                patch.object(self.adapter.time, "perf_counter", side_effect=lambda: next(ticks)), \
                patch("builtins.print"):
            processor = self.adapter.Processor(SimpleNamespace(width=16, height=16), {})
            for n in range(60):
                frame = Frame()
                frame.props.update({"_DurationDen": 60, "stamp": n})
                output = processor.process(n=n, f=frame)
                self.assertEqual(output.props, frame.props)
                np.testing.assert_array_equal(output[0], 120)
            self.assertGreater(client.process_into.call_count, 15)
            self.assertLess(client.process_into.call_count, 40)
            processor.process(n=99, f=frame)
            self.assertTrue(client.process_into.call_args.kwargs["reset"])

    def test_adaptive_rate_keeps_all_frames_when_processing_is_fast(self):
        client = Mock(worker_pid=1, reused=False, device=None, adaptive=True)
        client.process_into.return_value = True
        ticks = iter(value for n in range(100) for value in (n, n + .004))
        with patch.object(self.adapter, "FrameClient", return_value=client), \
                patch.object(self.adapter.time, "perf_counter", side_effect=lambda: next(ticks)), \
                patch("builtins.print"):
            processor = self.adapter.Processor(SimpleNamespace(width=16, height=16), {})
            frame = Frame()
            frame.props["_DurationDen"] = 60
            for n in range(60):
                processor.process(n=n, f=frame)
            self.assertEqual(client.process_into.call_count, 60)

    def test_adaptive_rate_accounts_for_playback_speed_at_attachment(self):
        client = Mock(worker_pid=1, reused=False, device=None, adaptive=True, playback_speed=2.0)
        client.process_into.return_value = True
        ticks = iter(value for n in range(100) for value in (n, n + .02))
        with patch.object(self.adapter, "FrameClient", return_value=client), \
                patch.object(self.adapter.time, "perf_counter", side_effect=lambda: next(ticks)), \
                patch("builtins.print"):
            processor = self.adapter.Processor(SimpleNamespace(width=16, height=16), {})
            frame = Frame()
            frame.props["_DurationDen"] = 30
            for n in range(60):
                processor.process(n=n, f=frame)
            self.assertLess(client.process_into.call_count, 40)

    def test_adaptive_rate_follows_later_playback_speed_changes(self):
        client = Mock(worker_pid=1, reused=False, device=None, adaptive=True, playback_speed=1.0)
        client.process_into.return_value = True
        ticks = iter(value for n in range(300) for value in (n, n + .02))
        with patch.object(self.adapter, "FrameClient", return_value=client), \
                patch.object(self.adapter.time, "perf_counter", side_effect=lambda: next(ticks)), \
                patch("builtins.print"):
            processor = self.adapter.Processor(SimpleNamespace(width=16, height=16), {})
            frame = Frame()
            frame.props["_DurationDen"] = 30
            for n in range(60):
                processor.process(n=n, f=frame)
            first = client.process_into.call_count
            client.playback_speed = 2.0
            for n in range(60, 120):
                processor.process(n=n, f=frame)
            second = client.process_into.call_count - first
            self.assertGreater(first, second * 1.5)

    def test_adaptive_rate_recovers_after_a_temporary_slowdown(self):
        client = Mock(worker_pid=1, reused=False, device=None, adaptive=True, playback_speed=1.0)
        client.process_into.return_value = True
        state = {"frame": 0, "end": False}
        def clock():
            state["end"] = not state["end"]
            cost = .03 if 60 <= state["frame"] < 150 else .004
            return state["frame"] * 10 + (0 if state["end"] else cost)
        with patch.object(self.adapter, "FrameClient", return_value=client), \
                patch.object(self.adapter.time, "perf_counter", side_effect=clock), \
                patch("builtins.print"):
            processor = self.adapter.Processor(SimpleNamespace(width=16, height=16), {})
            frame = Frame()
            frame.props["_DurationDen"] = 60
            counts = []
            for n in range(240):
                state["frame"] = n
                processor.process(n=n, f=frame)
                if n in (59, 149, 239):
                    counts.append(client.process_into.call_count)
            self.assertEqual(counts[0], 60)
            self.assertLess(counts[1] - counts[0], 45)
            self.assertGreater(counts[2] - counts[1], 65)

    def test_adaptive_rate_handles_very_slow_inference_without_overload(self):
        client = Mock(worker_pid=1, reused=False, device=None, adaptive=True, playback_speed=1.0)
        client.process_into.return_value = True
        ticks = iter(value for n in range(10) for value in (n * 10, n * 10 + 1.0))
        with patch.object(self.adapter, "FrameClient", return_value=client), \
                patch.object(self.adapter.time, "perf_counter", side_effect=lambda: next(ticks)), \
                patch("builtins.print"):
            processor = self.adapter.Processor(SimpleNamespace(width=16, height=16), {})
            frame = Frame()
            frame.props["_DurationDen"] = 60
            for n in range(60):
                processor.process(n=n, f=frame)
            self.assertEqual(client.process_into.call_count, 1)

    def test_adaptive_rate_uses_clip_rate_when_frame_duration_is_missing(self):
        client = Mock(worker_pid=1, reused=False, device=None, adaptive=True, playback_speed=1.0)
        client.process_into.return_value = True
        ticks = iter(value for n in range(100) for value in (n, n + .04))
        with patch.object(self.adapter, "FrameClient", return_value=client), \
                patch.object(self.adapter.time, "perf_counter", side_effect=lambda: next(ticks)), \
                patch("builtins.print"):
            processor = self.adapter.Processor(SimpleNamespace(width=16, height=16, fps_num=30, fps_den=1), {})
            frame = Frame()
            del frame.props["_DurationNum"]
            for n in range(60):
                processor.process(n=n, f=frame)
            self.assertGreater(client.process_into.call_count, 20)
            self.assertLess(client.process_into.call_count, 40)

    def test_variable_format_rejected_before_client(self):
        with patch.object(self.adapter, "FrameClient") as client:
            with self.assertRaises(ValueError):
                self.adapter.create_filter(SimpleNamespace(format=None), {})
            client.assert_not_called()

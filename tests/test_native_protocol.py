import io
import json
import multiprocessing.spawn
import sys
import unittest
from unittest.mock import patch

import numpy as np

from frame_client import FrameClient
from frame_module import FrameModule, configure_worker_executable, rate_from_timings
from native_protocol import MAX_MESSAGE, serve
from test_session import FakeProcessor


class NativeProtocolTests(unittest.TestCase):
    def exchange(self, requests, handler=lambda *_: None):
        source = b"".join(json.dumps(request).encode() + b"\n" for request in requests)
        output = io.BytesIO()
        serve(io.BytesIO(source), output, handler)
        return [json.loads(line) for line in output.getvalue().splitlines()]

    def test_handshake_dispatch_and_fail_closed(self):
        requests = [{"id": 1, "method": "host.initialize", "params": {"protocol": "openplayer-native-v1"}},
                    {"id": 2, "method": "frames.status", "params": None},
                    {"id": 3, "method": "host.initialize", "params": None},
                    {"id": 4, "method": "frames.status", "params": None}]
        replies = self.exchange(requests, lambda *_: {"running": False})
        self.assertEqual(len(replies), 3)
        self.assertEqual(replies[1]["result"], {"running": False})
        self.assertIn("error", replies[2])
        self.assertIn("error", self.exchange(requests[1:])[0])

    def test_framing_and_id_limits(self):
        for source in (b"x" * (MAX_MESSAGE + 1), b"{}", b'{}\n',
                       b'{"id":true,"method":"x","params":null}\n'):
            with self.subTest(source=source[:50]), self.assertRaises(ValueError):
                serve(io.BytesIO(source), io.BytesIO(), lambda *_: None)

    def test_duplicate_id_and_oversized_response(self):
        handshake = {"id": 1, "method": "host.initialize", "params": {"protocol": "openplayer-native-v1"}}
        with self.assertRaises(ValueError):
            self.exchange([handshake, handshake])
        with self.assertRaises(ValueError):
            self.exchange([handshake, {"id": 2, "method": "frames.status", "params": None}],
                          lambda *_: "x" * MAX_MESSAGE)

    def test_module_rejects_unrequested_options(self):
        module = FrameModule({}, factory=FakeProcessor)
        try:
            for method, params in (("unknown", None), ("frames.open", {"executable": "worker.exe"}),
                                   ("frames.status", {"extra": 1}), ("frames.open", {"settings": {"intensity": 6}})):
                with self.subTest(method=method, params=params), self.assertRaises(ValueError):
                    module.call(method, params)
            module.call("frames.open", None)
            with self.assertRaises(ValueError):
                module.call("frames.open", {"settings": {"intensity": .25}})
        finally:
            module.close()

    def test_calibration_returns_bounded_limit_and_reuses_owner(self):
        module = FrameModule({}, factory=FakeProcessor)
        probe = {"width": 64, "height": 32, "frameRate": 60.0, "speed": 1.0}
        try:
            with patch("frame_module.calibrate_frame_rate", return_value=35.0) as calibrate:
                reply = module.call("frames.open", {"adaptive": True, "frameRateProbe": probe})
                self.assertEqual(reply["frameRateLimit"], 35.0)
                self.assertEqual(module.call("frames.status", None)["profiledFrameRate"], 35.0)
                self.assertEqual(module.call("frames.open", {"adaptive": True, "frameRateProbe": probe}), reply)
                calibrate.assert_called_once()
        finally:
            module.close()

    def test_calibration_rejects_invalid_metadata(self):
        module = FrameModule({}, factory=FakeProcessor)
        try:
            for probe in (None, {}, {"width": True, "height": 32, "frameRate": 60, "speed": 1},
                          {"width": 7680, "height": 32, "frameRate": 60, "speed": 1},
                          {"width": 64, "height": 32, "frameRate": 60, "speed": 0}):
                with self.subTest(probe=probe), self.assertRaises(ValueError):
                    module.call("frames.open", {"adaptive": True, "frameRateProbe": probe})
        finally:
            module.close()

    def test_calibration_rate_has_headroom_and_respects_source_and_speed(self):
        self.assertEqual(rate_from_timings([.015] * 12, {"speed": 1, "frameRate": 60}), 40)
        self.assertEqual(rate_from_timings([.015] * 12, {"speed": 2, "frameRate": 60}), 20)
        self.assertEqual(rate_from_timings([.005] * 12, {"speed": 1, "frameRate": 24}), 24)
        self.assertEqual(rate_from_timings([.001] * 12, {"speed": 1, "frameRate": None}), 120)
        self.assertEqual(rate_from_timings([.015] * 12, {"speed": 1, "frameRate": .5}), 1)
        with self.assertRaises(RuntimeError):
            rate_from_timings([0] * 12, {"speed": 1, "frameRate": 60})

    def test_calibration_failure_closes_owner(self):
        module = FrameModule({}, factory=FakeProcessor)
        probe = {"width": 64, "height": 32, "frameRate": 60.0, "speed": 1.0}
        with patch("frame_module.calibrate_frame_rate", side_effect=RuntimeError("failed")):
            with self.assertRaisesRegex(RuntimeError, "failed"):
                module.call("frames.open", {"adaptive": True, "frameRateProbe": probe})
        self.assertIsNone(module.owner)

    @unittest.skipUnless(sys.platform == "win32", "Windows windowless runtime")
    def test_windowless_worker(self):
        executable = multiprocessing.spawn.get_executable()
        try:
            configure_worker_executable()
            self.test_module_owns_worker_and_closes_active_client()
        finally:
            multiprocessing.set_executable(executable)

    def test_live_updates_preserve_worker_buffers_and_reject_device_change(self):
        module = FrameModule({}, factory=FakeProcessor)
        frame = np.full((32, 64, 4), 48, np.uint8)
        try:
            self.assertFalse(module.call("frames.update", {"settings": {"style": 1}})["applied"])
            reply = module.call("frames.open", None)
            before = module.call("frames.update", {"settings": {"style": 2}})
            self.assertEqual(before["revision"], 1)
            with FrameClient(reply["endpoint"], 64, 32) as client:
                pid = client.worker_pid
                names = [m.name for m in client.memories]
                client.process(frame)
                updated = module.call("frames.update", {"settings": {"intensity": 3, "use_auto_mask": True}})
                self.assertTrue(updated["applied"])
                self.assertEqual(updated["revision"], 2)
                np.testing.assert_array_equal(client.process(frame)[0, 0, :3], [101, 1, 200])
                np.testing.assert_array_equal(client.process(frame)[0, 0, :3], [101, 0, 200])
                for settings in ({"intensity": 6}, {"style": True}, {},
                                 {"gpu_uuid": "GPU-76e0cbba-1c68-0d53-26ca-b999df6f0e9b"}):
                    self.assertFalse(module.call("frames.update", {"settings": settings})["applied"])
                status = module.call("frames.status", None)
                self.assertEqual(status["revision"], 2)
                self.assertEqual(status["workerPid"], pid)
                self.assertEqual(names, [m.name for m in client.memories])
                self.assertEqual(status["settings"]["style"], 2)
                self.assertIsNone(client.error)
        finally:
            module.close()

    def test_module_owns_worker_and_closes_active_client(self):
        module = FrameModule({}, factory=FakeProcessor)
        try:
            reply = module.call("frames.open", None)
            self.assertEqual(reply, module.call("frames.open", None))
            with FrameClient(reply["endpoint"], 64, 32) as client:
                client.process(np.full((32, 64, 4), 100, np.uint8))
                self.assertEqual(module.call("frames.status", None)["workerPid"], client.worker_pid)
                module.call("frames.close", None)
                self.assertFalse(module.call("frames.status", None)["running"])
        finally:
            module.close()

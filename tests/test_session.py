import multiprocessing as mp
from multiprocessing.shared_memory import SharedMemory
import os
import time
import unittest

import numpy as np

from dlssnr_backend import validate_settings
from frame_session import FrameSession, ProcessorError


class FakeProcessor:
    def __init__(self, width, height, options):
        self.options = options
        if options.get("mode") == "init-error":
            raise RuntimeError("initialization test failure")
        if options.get("mode") == "init-hang":
            time.sleep(10)
        self.updates = 0

    def update(self, settings):
        if settings.get("fail"):
            raise RuntimeError("update test failure")
        self.updates += 1

    def process(self, frame, reset=False):
        mode = self.options.get("mode")
        if mode == "hang":
            time.sleep(10)
        if mode == "crash":
            os._exit(7)
        if mode == "none":
            return None
        if mode == "error":
            raise RuntimeError("evaluation test failure")
        result = frame.copy()
        result[0, 0, :3] = (100 + self.updates, int(reset), 200)
        return result


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.full((32, 64, 4), 48, np.uint8)
        self.frame[..., 3] = 255

    def assert_released(self, session):
        self.assertFalse(any(p.pid == session.worker_pid for p in mp.active_children()))
        for name in session.buffer_names:
            with self.assertRaises(FileNotFoundError):
                SharedMemory(name=name)

    def test_order_reset_update_and_cleanup(self):
        with FrameSession(64, 32, FakeProcessor) as session:
            first = session.process(self.frame)
            second = session.process(self.frame[:, ::-1])
            session.update({})
            updated = session.process(self.frame)
            seek = session.process(self.frame, reset=True)
            self.assertEqual(first[0, 0, :3].tolist(), [100, 1, 200])
            self.assertEqual(second[0, 0, :3].tolist(), [100, 0, 200])
            self.assertEqual(updated[0, 0, :3].tolist(), [101, 1, 200])
            self.assertEqual(seek[0, 0, :3].tolist(), [101, 1, 200])
            np.testing.assert_array_equal(self.frame[0, 0], [48, 48, 48, 255])
            np.testing.assert_array_equal(first[0, 0, :3], [100, 1, 200])
        session.close()
        self.assert_released(session)
        with self.assertRaises(ProcessorError):
            session.process(self.frame)

    def test_failures_disable_and_pass_through(self):
        for mode in ("crash", "hang", "error", "none"):
            with self.subTest(mode=mode):
                with FrameSession(64, 32, FakeProcessor, {"mode": mode}, timeout=0.2) as session:
                    started = time.monotonic()
                    np.testing.assert_array_equal(session.process(self.frame), self.frame)
                    self.assertLess(time.monotonic() - started, 4)
                    self.assertTrue(session.error)
                    np.testing.assert_array_equal(session.process(self.frame), self.frame)
                    self.assertEqual(session.fallback_frames, 2)
                self.assert_released(session)

    def test_strict_failure_stays_strict(self):
        with FrameSession(64, 32, FakeProcessor, {"mode": "none"}, fallback=False) as session:
            for _ in range(2):
                with self.assertRaises(ProcessorError):
                    session.process(self.frame)
        self.assert_released(session)

    def test_update_failure_stops_worker(self):
        with FrameSession(64, 32, FakeProcessor) as session:
            with self.assertRaises(ProcessorError):
                session.update({"fail": True})
            self.assertTrue(session.error)
            np.testing.assert_array_equal(session.process(self.frame), self.frame)
        self.assert_released(session)

    def test_initialization_failure_and_timeout(self):
        before = {p.pid for p in mp.active_children()}
        for mode in ("init-error", "init-hang"):
            with self.assertRaises(ProcessorError):
                FrameSession(64, 32, FakeProcessor, {"mode": mode}, startup_timeout=1)
        self.assertEqual({p.pid for p in mp.active_children()}, before)

    def test_frame_and_dimension_validation(self):
        for dimensions in ((0, 32), (3841, 32), (64.5, 32), (64, 2161)):
            with self.assertRaises(ValueError):
                FrameSession(*dimensions, FakeProcessor)
        with FrameSession(64, 32, FakeProcessor) as session:
            for invalid in (self.frame.astype(np.float32), self.frame[..., :3], None):
                with self.assertRaises(ValueError):
                    session.process(invalid)
        self.assert_released(session)

    def test_settings_validation(self):
        for settings in ({"arbitrary": 1}, {"intensity": float("nan")},
                         {"intensity": 5.01}, {"style": 4}, {"use_auto_mask": 2}, {"skin_struct": True}):
            with self.assertRaises(ValueError):
                validate_settings(settings)
        self.assertEqual(validate_settings({"intensity": 0.5}), {"intensity": 0.5})
        self.assertEqual(validate_settings({"local_tone": 5, "local_struct": 0, "skin_struct": 5}),
                         {"local_tone": 5, "local_struct": 0, "skin_struct": 5})


if __name__ == "__main__":
    unittest.main()

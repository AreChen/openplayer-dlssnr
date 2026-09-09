import multiprocessing as mp
from multiprocessing.shared_memory import SharedMemory
import unittest
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from frame_client import FrameClient
from frame_service import FrameService
from frame_session import ProcessorError
from frame_wire import receive_message, send_message
from test_session import FakeProcessor


class FrameServiceTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.full((32, 64, 4), 48, np.uint8)
        self.events = []

    def service(self, **kwargs):
        return FrameService(FakeProcessor, log=lambda kind, **data: self.events.append((kind, data)), **kwargs)

    def test_rebuild_reuses_engine_and_resets_history(self):
        with self.service() as owner:
            with FrameClient(owner.endpoint, 64, 32) as first:
                pid = first.worker_pid
                names = [memory.name for memory in first.memories]
                np.testing.assert_array_equal(first.process(self.frame)[0, 0, :3], [100, 1, 200])
                np.testing.assert_array_equal(first.process(self.frame)[0, 0, :3], [100, 0, 200])
            with FrameClient(owner.endpoint, 64, 32) as rebuilt:
                self.assertEqual(rebuilt.worker_pid, pid)
                self.assertTrue(rebuilt.reused)
                self.assertEqual(rebuilt.generation, 2)
                self.assertEqual(rebuilt.startup_ms, 0)
                np.testing.assert_array_equal(rebuilt.process(self.frame)[0, 0, :3], [100, 1, 200])
        self.assertFalse(any(process.pid == pid for process in mp.active_children()))
        for name in names:
            with self.assertRaises(FileNotFoundError):
                SharedMemory(name=name)
        self.assertEqual([event[0] for event in self.events].count("engine-start"), 1)
        self.assertEqual([event[0] for event in self.events].count("engine-close"), 1)

    def test_updates_serialize_with_live_frames(self):
        with self.service() as owner:
            with FrameClient(owner.endpoint, 64, 32) as client:
                def process():
                    return [int(client.process(self.frame)[0, 0, 0]) for _ in range(50)]
                with ThreadPoolExecutor(max_workers=1) as pool:
                    frames = pool.submit(process)
                    for n in range(10):
                        self.assertEqual(owner.update({"intensity": n / 10})["revision"], n + 1)
                    values = frames.result(timeout=10)
                self.assertEqual(values, sorted(values))
                self.assertTrue(all(100 <= value <= 110 for value in values))
                self.assertEqual(client.process(self.frame)[0, 0, 0], 110)
                self.assertIsNone(client.error)

    def test_format_change_replaces_instead_of_accumulating_workers(self):
        with self.service() as owner:
            for width in (64, 80, 64):
                with FrameClient(owner.endpoint, width, 32) as client:
                    self.assertFalse(client.reused)
                    client.process(np.full((32, width, 4), 48, np.uint8))
        kinds = [event[0] for event in self.events]
        self.assertEqual(kinds.count("engine-start"), 3)
        self.assertEqual(kinds.count("engine-close"), 3)

    def test_failed_worker_is_not_silently_restarted_on_reconnect(self):
        with self.service(options={"mode": "crash"}) as owner:
            with FrameClient(owner.endpoint, 64, 32) as first:
                pid = first.worker_pid
                np.testing.assert_array_equal(first.process(self.frame), self.frame)
                self.assertTrue(first.error)
            with FrameClient(owner.endpoint, 64, 32) as second:
                self.assertEqual(second.worker_pid, pid)
                self.assertTrue(second.reused)
                np.testing.assert_array_equal(second.process(self.frame), self.frame)
                self.assertTrue(second.error)
        self.assertEqual([event[0] for event in self.events].count("engine-start"), 1)

    def test_bad_token_does_not_start_worker(self):
        with self.service() as owner:
            for token in ("invalid", "\u4e2d", None):
                with self.subTest(token=token), self.assertRaisesRegex(ProcessorError, "token"):
                    FrameClient({**owner.endpoint, "token": token}, 64, 32)
            self.assertIsNone(owner.session)

    def test_uhd_shared_buffers_preserve_dimensions(self):
        with self.service() as owner:
            with FrameClient(owner.endpoint, 3840, 2160) as client:
                frame = np.full((2160, 3840, 4), 48, np.uint8)
                output = client.process(frame)
                self.assertEqual(output.shape, frame.shape)
                self.assertEqual(output.dtype, frame.dtype)
                np.testing.assert_array_equal(output[0, 0, :3], [100, 1, 200])
                np.testing.assert_array_equal(output[-1, -1], frame[-1, -1])
                self.assertIsNone(client.error)

    def test_timeout_disables_worker_without_stale_output(self):
        with self.service(options={"mode": "hang"}, timeout=.1) as owner:
            with FrameClient(owner.endpoint, 64, 32) as client:
                np.testing.assert_array_equal(client.process(self.frame), self.frame)
                self.assertIn("timed out", client.error)
                np.testing.assert_array_equal(client.process(self.frame), self.frame)

    def test_old_generation_cannot_evaluate(self):
        with self.service() as owner:
            with FrameClient(owner.endpoint, 64, 32) as client:
                send_message(client.connection, {"op": "process", "generation": 0,
                                                 "sequence": 1, "reset": False})
                self.assertIn("stale", receive_message(client.connection, 2)["error"])

    def test_owner_close_with_active_lease_falls_back(self):
        owner = self.service()
        try:
            with FrameClient(owner.endpoint, 64, 32) as client:
                client.process(self.frame)
                owner.close()
                np.testing.assert_array_equal(client.process(self.frame), self.frame)
                self.assertTrue(client.error)
        finally:
            owner.close()

    def test_planar_transfer_matches_rgba_and_does_not_mutate_source(self):
        source = [self.frame[:, :, channel] for channel in range(3)]
        output = [np.empty_like(plane) for plane in source]
        with self.service() as owner:
            with FrameClient(owner.endpoint, 64, 32) as client:
                self.assertTrue(client.process_into(source, output))
                expected = self.frame.copy()
                expected[0, 0, :3] = (100, 1, 200)
                for channel in range(3):
                    np.testing.assert_array_equal(output[channel], expected[:, :, channel])
                    np.testing.assert_array_equal(source[channel], 48)
                with self.assertRaises(ValueError):
                    client.process_into(source[:2], output)
                output[0].flags.writeable = False
                with self.assertRaises(ValueError):
                    client.process_into(source, output)

    def test_planar_failure_preserves_every_original_pixel(self):
        with self.service(options={"mode": "crash"}) as owner:
            with FrameClient(owner.endpoint, 64, 32) as client:
                source = [self.frame[:, :, channel] for channel in range(3)]
                output = [np.zeros_like(plane) for plane in source]
                for _ in range(2):
                    self.assertFalse(client.process_into(source, output))
                    for actual, original in zip(output, source):
                        np.testing.assert_array_equal(actual, original)


if __name__ == "__main__":
    unittest.main()

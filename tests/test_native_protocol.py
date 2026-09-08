import io
import json
import multiprocessing.spawn
import sys
import unittest

import numpy as np

from frame_client import FrameClient
from frame_module import FrameModule, configure_worker_executable
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
                                   ("frames.status", {"extra": 1}), ("frames.open", {"settings": {"intensity": 2}})):
                with self.subTest(method=method, params=params), self.assertRaises(ValueError):
                    module.call(method, params)
            module.call("frames.open", None)
            with self.assertRaises(ValueError):
                module.call("frames.open", {"settings": {"intensity": .25}})
        finally:
            module.close()

    @unittest.skipUnless(sys.platform == "win32", "Windows windowless runtime")
    def test_windowless_worker(self):
        executable = multiprocessing.spawn.get_executable()
        try:
            configure_worker_executable()
            self.test_module_owns_worker_and_closes_active_client()
        finally:
            multiprocessing.set_executable(executable)

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

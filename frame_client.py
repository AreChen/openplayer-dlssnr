"""Short-lived filter lease onto a long-lived trusted frame service."""
from multiprocessing.shared_memory import SharedMemory
import math
import socket
import time

import numpy as np

from frame_session import ProcessorError
from frame_wire import receive_message, send_message


class FrameClient:
    def __init__(self, endpoint, width, height):
        self.connection = None
        self.memories = []
        self.source = self.output = None
        self.shape = (height, width, 4)
        self.sequence = 0
        self.error = None
        self.worker_exitcode = None
        self.closed = False
        started = time.perf_counter()
        try:
            self.connection = socket.create_connection(("127.0.0.1", endpoint["port"]), timeout=2)
            self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            send_message(self.connection, {"op": "attach", "token": endpoint["token"],
                                           "width": width, "height": height})
            reply = receive_message(self.connection, 7)
            if "error" in reply:
                raise ProcessorError(reply["error"])
            if reply["width"] != width or reply["height"] != height or len(reply["buffers"]) != 2:
                raise ProcessorError("invalid frame buffer descriptor")
            self.generation = reply["generation"]
            self.worker_pid = reply["worker_pid"]
            self.engine = reply["engine"]
            self.device = reply.get("device")
            self.adaptive = reply.get("adaptive", False)
            if type(self.adaptive) is not bool:
                raise ProcessorError("invalid adaptive frame policy")
            self.playback_speed = reply.get("playback_speed", 1.0)
            if (type(self.playback_speed) not in (int, float) or not math.isfinite(self.playback_speed)
                    or not .01 <= self.playback_speed <= 100):
                raise ProcessorError("invalid adaptive playback speed")
            self.reused = reply["reused"]
            self.startup_ms = reply["startup_ms"]
            for name in reply["buffers"]:
                memory = SharedMemory(name=name)
                self.memories.append(memory)
                if memory.size < width * height * 4:
                    raise ProcessorError("frame buffer too small")
            self.source, self.output = [np.ndarray(self.shape, np.uint8, buffer=memory.buf)
                                       for memory in self.memories]
        except Exception:
            self.close()
            raise
        self.attach_ms = (time.perf_counter() - started) * 1000

    def process(self, frame, *, reset=False):
        if self.closed:
            raise ProcessorError("frame lease is closed")
        if not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or frame.shape != self.shape:
            raise ValueError("invalid RGBA8 frame")
        if self.error:
            return frame.copy()
        np.copyto(self.source, frame)
        return self.output.copy() if self._evaluate(reset) else frame.copy()

    def process_into(self, source_planes, output_planes, *, reset=False):
        """Copy RGB planes directly through owned RGBA buffers, without staging arrays."""
        if self.closed:
            raise ProcessorError("frame lease is closed")
        if len(source_planes) != 3 or len(output_planes) != 3:
            raise ValueError("three RGB planes required")
        for plane in (*source_planes, *output_planes):
            if not isinstance(plane, np.ndarray) or plane.dtype != np.uint8 or plane.shape != self.shape[:2]:
                raise ValueError("invalid RGB plane")
        if any(not plane.flags.writeable for plane in output_planes):
            raise ValueError("output planes must be writable")
        processed = False
        if not self.error:
            for channel, plane in enumerate(source_planes):
                np.copyto(self.source[:, :, channel], plane)
            self.source[:, :, 3] = 255
            processed = self._evaluate(reset)
        for channel, plane in enumerate(output_planes):
            np.copyto(plane, self.output[:, :, channel] if processed else source_planes[channel])
        return processed

    def _evaluate(self, reset):
        try:
            self.sequence += 1
            send_message(self.connection, {"op": "process", "generation": self.generation,
                                           "sequence": self.sequence, "reset": bool(reset)})
            reply = receive_message(self.connection, 2)
            if (reply.get("generation") != self.generation or reply.get("sequence") != self.sequence
                    or type(reply.get("processed")) is not bool):
                raise ProcessorError("stale or invalid frame reply")
            if not reply["processed"]:
                raise ProcessorError(reply.get("fallback") or "frame processor failed")
            speed = reply.get("playback_speed", self.playback_speed)
            if type(speed) not in (int, float) or not math.isfinite(speed) or not .01 <= speed <= 100:
                raise ProcessorError("invalid adaptive playback speed")
            self.playback_speed = speed
            return True
        except (OSError, EOFError, ValueError, ProcessorError) as error:
            self.error = str(error)
            self.connection.close()
            return False

    def close(self):
        self.source = self.output = None
        for memory in self.memories:
            memory.close()
        self.memories.clear()
        if self.connection is not None:
            self.connection.close()
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

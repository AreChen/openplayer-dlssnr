"""Bounded, synchronous CPU RGBA8 transport for an isolated frame processor.

This is a prototype transport, not an OpenPlayer SDK API or GPU texture bridge.
Only one caller/frame may be in flight. Native libraries never load in the caller.
"""

import math
import multiprocessing as mp
from multiprocessing.shared_memory import SharedMemory
import time

import numpy as np


class ProcessorError(RuntimeError):
    pass


def _worker(connection, names, shape, factory, options):
    memories = []
    try:
        for name in names:
            memories.append(SharedMemory(name=name))
        source, output = [np.ndarray(shape, np.uint8, buffer=m.buf) for m in memories]
        processor = factory(shape[1], shape[0], options)
        connection.send({"ok": True})
        while True:
            command = connection.recv()
            if command["op"] == "stop":
                break
            if command["op"] == "update":
                processor.update(command["settings"])
            elif command["op"] == "process":
                result = processor.process(source, reset=command["reset"])
                if result is None or result.dtype != np.uint8 or result.shape != shape:
                    raise ProcessorError("processor returned no valid RGBA8 frame")
                np.copyto(output, result)
            else:
                raise ProcessorError("unknown frame operation")
            connection.send({"ok": True})
    except (EOFError, BrokenPipeError):
        pass
    except BaseException as error:
        try:
            connection.send({"ok": False, "error": f"{type(error).__name__}: {error}"})
        except (EOFError, BrokenPipeError, OSError):
            pass
    finally:
        # Upstream reports hangs during NGX shutdown. This disposable process exits
        # without reinitializing or explicitly shutting down its native backend.
        connection.close()
        for memory in memories:
            memory.close()


class FrameSession:
    def __init__(self, width, height, factory, options=None, *, timeout=3.0,
                 startup_timeout=30.0, fallback=True):
        if (type(width) is not int or type(height) is not int
                or not 16 <= width <= 1920 or not 16 <= height <= 1080):
            raise ValueError("prototype supports integer dimensions 16..1920 x 16..1080")
        for value in (timeout, startup_timeout):
            if not math.isfinite(value) or not 0 < value <= 120:
                raise ValueError("timeouts must be finite and in (0, 120]")
        self.shape = (height, width, 4)
        self.timeout = timeout
        self.fallback = fallback
        self.error = None
        self.closed = False
        self.fallback_frames = 0
        self._reset = True
        self._memories = []
        self._process = None
        self._connection = None
        self._source = self._output = None
        self.worker_pid = None
        self.buffer_names = ()
        self.worker_exitcode = None
        started = time.perf_counter()
        context = mp.get_context("spawn")
        child = None
        try:
            for _ in range(2):
                self._memories.append(SharedMemory(create=True, size=width * height * 4))
            self.buffer_names = tuple(m.name for m in self._memories)
            self._source, self._output = [
                np.ndarray(self.shape, np.uint8, buffer=m.buf) for m in self._memories
            ]
            self._connection, child = context.Pipe()
            self._process = context.Process(
                target=_worker, args=(child, self.buffer_names, self.shape, factory, options or {}),
                daemon=True, name="openplayer-frame-processor",
            )
            self._process.start()
            self.worker_pid = self._process.pid
            child.close()
            child = None
            self._receive(startup_timeout)
        except Exception as error:
            self.error = str(error)
            self.close()
            raise ProcessorError(self.error) from error
        finally:
            if child is not None:
                child.close()
        self.startup_ms = (time.perf_counter() - started) * 1000

    def _receive(self, timeout):
        try:
            if not self._connection.poll(timeout):
                raise ProcessorError(f"frame worker timed out after {timeout}s")
            message = self._connection.recv()
        except (EOFError, BrokenPipeError, OSError) as error:
            raise ProcessorError("frame worker disconnected") from error
        if not message.get("ok"):
            raise ProcessorError(message.get("error", "frame worker failed"))

    def _request(self, command):
        try:
            self._connection.send(command)
            self._receive(self.timeout)
        except (EOFError, BrokenPipeError, OSError) as error:
            raise ProcessorError("frame worker disconnected") from error

    def process(self, frame, *, reset=False):
        if self.closed:
            raise ProcessorError("frame session is closed")
        if not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or frame.shape != self.shape:
            raise ValueError(f"expected uint8 RGBA frame with shape {self.shape}")
        if self.error:
            if not self.fallback:
                raise ProcessorError(self.error)
            self.fallback_frames += 1
            return frame.copy()
        np.copyto(self._source, frame)
        if self.process_shared(reset=reset):
            return self._output.copy()
        return frame.copy()

    def process_shared(self, *, reset=False):
        """Evaluate the owned input buffer, for a trusted single-caller transport.

        The caller must finish writing input before this call and finish reading
        output before the next call. False means use the original, not output.
        Buffer mappings remain valid until close(), including after worker failure.
        """
        if self.closed:
            raise ProcessorError("frame session is closed")
        if self.error:
            if not self.fallback:
                raise ProcessorError(self.error)
            self.fallback_frames += 1
            return False
        try:
            self._request({"op": "process", "reset": bool(reset or self._reset)})
            self._reset = False
            return True
        except ProcessorError as error:
            self.error = str(error)
            self._dispose(keep_buffers=True)
            if not self.fallback:
                raise
            self.fallback_frames += 1
            return False

    def update(self, settings):
        if self.closed or self.error:
            raise ProcessorError("frame session is not active")
        try:
            self._request({"op": "update", "settings": settings})
            self._reset = True
        except ProcessorError as error:
            self.error = str(error)
            self._dispose(keep_buffers=True)
            raise

    def _dispose(self, *, keep_buffers=False):
        process = self._process
        if process is not None:
            if process.pid is not None:
                if process.is_alive():
                    try:
                        self._connection.send({"op": "stop"})
                    except (BrokenPipeError, EOFError, OSError):
                        pass
                    process.join(0.25)
                if process.is_alive():
                    process.terminate()
                    process.join(2)
                if process.is_alive():
                    process.kill()
                    process.join(2)
                if process.is_alive():
                    raise ProcessorError("worker could not be stopped")
                self.worker_exitcode = process.exitcode
            process.close()
            self._process = None
        if self._connection is not None:
            self._connection.close()
            self._connection = None
        if keep_buffers:
            return
        self._source = self._output = None
        for memory in self._memories:
            memory.close()
            try:
                memory.unlink()
            except FileNotFoundError:
                pass
        self._memories.clear()

    def close(self):
        self._dispose()
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

"""Owner-scoped, single-client frame service. Not an OpenPlayer SDK endpoint.

The owner outlives filter rebuilds, but must close this service before unloading
its processor package. Loopback plus a per-owner token prevents accidental joins;
this is trusted local software, not an OS sandbox or a multi-tenant service.
"""
import hmac
import secrets
import select
import socket
import threading

from frame_session import FrameSession
from frame_wire import receive_message, send_message


class FrameService:
    def __init__(self, factory, options=None, *, log=None, timeout=.5, startup_timeout=5):
        self.factory = factory
        self.options = options or {}
        self.log = log or (lambda *_args, **_kwargs: None)
        self.timeout = timeout
        self.startup_timeout = startup_timeout
        self.session = None
        self.dimensions = None
        self.generation = 0
        self.engine = 0
        self.error = None
        self.stopping = threading.Event()
        self.connection = None
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.listener.settimeout(.1)
        self.endpoint = {"port": self.listener.getsockname()[1], "token": secrets.token_hex(32)}
        self.thread = threading.Thread(target=self._serve, daemon=True, name="frame-session-owner")
        self.thread.start()

    def _close_session(self):
        if self.session is not None:
            self.session.close()
            self.log("engine-close", engine=self.engine, worker_pid=self.session.worker_pid,
                     worker_exitcode=self.session.worker_exitcode)
            self.session = None

    def _attach(self, request):
        if set(request) != {"op", "token", "width", "height"} or request["op"] != "attach":
            raise ValueError("expected frame attach")
        token = request["token"]
        if not isinstance(token, str) or not token.isascii() or not hmac.compare_digest(token, self.endpoint["token"]):
            raise ValueError("invalid frame owner token")
        width, height = request["width"], request["height"]
        if type(width) is not int or type(height) is not int or not 16 <= width <= 1920 or not 16 <= height <= 1080:
            raise ValueError("unsupported frame dimensions")
        reused = self.session is not None and self.dimensions == (width, height)
        if not reused:
            self._close_session()
            self.session = FrameSession(width, height, self.factory, self.options,
                                        timeout=self.timeout, startup_timeout=self.startup_timeout)
            self.dimensions = (width, height)
            self.engine += 1
            self.log("engine-start", engine=self.engine, worker_pid=self.session.worker_pid,
                     width=width, height=height, startup_ms=self.session.startup_ms)
        self.generation += 1
        reply = {"generation": self.generation, "buffers": self.session.buffer_names,
                 "width": width, "height": height, "worker_pid": self.session.worker_pid,
                 "engine": self.engine, "reused": reused,
                 "startup_ms": 0 if reused else self.session.startup_ms,
                 "device": self.session.device}
        self.log("attach", **{key: value for key, value in reply.items() if key != "buffers"})
        return reply

    def _handle(self, connection):
        send_message(connection, self._attach(receive_message(connection, 2)))
        sequence = 0
        try:
            while not self.stopping.is_set():
                if not select.select([connection], [], [], .1)[0]:
                    continue
                request = receive_message(connection, 1)
                if (set(request) != {"op", "generation", "sequence", "reset"}
                        or request["op"] != "process"
                        or type(request["generation"]) is not int
                        or request["generation"] != self.generation
                        or type(request["sequence"]) is not int
                        or request["sequence"] != sequence + 1
                        or type(request["reset"]) is not bool):
                    raise ValueError("stale or invalid frame request")
                reset = sequence == 0 or request["reset"]
                sequence += 1
                processed = self.session.process_shared(reset=reset)
                send_message(connection, {"generation": self.generation, "sequence": sequence,
                                           "processed": processed, "fallback": self.session.error})
        finally:
            self.log("detach", generation=self.generation, engine=self.engine, frames=sequence)

    def _serve(self):
        try:
            while not self.stopping.is_set():
                try:
                    connection, _ = self.listener.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if self.stopping.is_set():
                        break
                    raise
                self.connection = connection
                connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                try:
                    self._handle(connection)
                except EOFError:
                    pass
                except (OSError, ValueError, RuntimeError) as error:
                    try:
                        send_message(connection, {"error": str(error)})
                    except OSError:
                        pass
                finally:
                    connection.close()
                    self.connection = None
        except Exception as error:
            self.error = error
        finally:
            try:
                self._close_session()
            except Exception as error:
                self.error = error

    def close(self):
        self.stopping.set()
        self.listener.close()
        connection = self.connection
        if connection is not None:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        self.thread.join(8)
        if self.thread.is_alive():
            raise RuntimeError("frame service did not stop")
        if self.error:
            raise RuntimeError("frame service failed") from self.error

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

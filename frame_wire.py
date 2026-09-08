"""Bounded JSON control messages for the local experimental frame transport."""
import json
import socket
import struct
import time

MAX_MESSAGE = 4096


def send_message(connection, message):
    data = json.dumps(message, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(data) > MAX_MESSAGE:
        raise ValueError("frame control message too large")
    connection.sendall(struct.pack("!I", len(data)) + data)


def receive_message(connection, timeout):
    deadline = time.monotonic() + timeout

    def read_exact(size):
        data = bytearray()
        while len(data) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("frame control deadline exceeded")
            connection.settimeout(remaining)
            chunk = connection.recv(size - len(data))
            if not chunk:
                raise EOFError("frame connection closed")
            data.extend(chunk)
        return data

    size, = struct.unpack("!I", read_exact(4))
    if not 0 < size <= MAX_MESSAGE:
        raise ValueError("invalid frame control message length")
    message = json.loads(read_exact(size))
    if not isinstance(message, dict):
        raise ValueError("frame control message must be an object")
    return message

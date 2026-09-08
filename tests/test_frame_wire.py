import socket
import struct
import unittest

from frame_wire import MAX_MESSAGE, receive_message, send_message


class FrameWireTests(unittest.TestCase):
    def test_round_trip_and_outgoing_bound(self):
        sender, receiver = socket.socketpair()
        with sender, receiver:
            send_message(sender, {"sequence": 1})
            self.assertEqual(receive_message(receiver, .5), {"sequence": 1})
            with self.assertRaises(ValueError):
                send_message(sender, {"data": "x" * MAX_MESSAGE})

    def test_oversize_incoming_header_rejected_without_body(self):
        sender, receiver = socket.socketpair()
        with sender, receiver:
            sender.sendall(struct.pack("!I", MAX_MESSAGE + 1))
            with self.assertRaises(ValueError):
                receive_message(receiver, .5)

    def test_partial_body_hits_deadline(self):
        sender, receiver = socket.socketpair()
        with sender, receiver:
            sender.sendall(struct.pack("!I", 100) + b"{")
            with self.assertRaises(TimeoutError):
                receive_message(receiver, .03)

import struct

from messages import Message


class Keepalive(Message):
    def __init__(self):
        super().__init__(0, None)

    def to_bytes(self) -> bytes:
        return struct.pack('>I', self.message_length)

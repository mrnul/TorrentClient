import struct

from messages.message import Message


class KeepAlive(Message):
    def __init__(self):
        super().__init__(0, None)

    def to_bytes(self) -> bytes:
        return struct.pack('>I', self.len)

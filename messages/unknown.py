import struct

from messages.message import Message


class Unknown(Message):
    def __init__(self, length: int, uid: int, payload: bytes):
        super().__init__(length, uid)
        self.payload = payload

    def to_bytes(self) -> bytes:
        return struct.pack('>IB', self.len, self.id) + self.payload

import struct

from messages import Message


class Unknown(Message):
    def __init__(self, uid: int, payload: bytes):
        super().__init__(1 + len(payload), uid)
        self.payload = payload

    def to_bytes(self) -> bytes:
        return struct.pack('>IB', self.message_length, self.id) + self.payload

import struct

from messages.ids import IDs
from messages.message import Message


class Interested(Message):
    def __init__(self):
        super().__init__(1, IDs.interested.value)

    def to_bytes(self) -> bytes:
        return struct.pack('>IB', self.len, self.id)

import struct

from messages.ids import IDs
from messages.message import Message


class Choke(Message):
    def __init__(self):
        super().__init__(1, IDs.choke.value)

    def to_bytes(self) -> bytes:
        return struct.pack('>IB', self.message_length, self.uid)

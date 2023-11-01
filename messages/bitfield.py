import struct

from messages import IDs
from messages.message import Message


class BitField(Message):
    def __init__(self, bitfield: bytes):
        super().__init__(1 + len(bitfield), IDs.bitfield.value)
        self.bitfield = bitfield

    def to_bytes(self) -> bytes:
        return struct.pack('>IB', self.len, self.id) + self.bitfield

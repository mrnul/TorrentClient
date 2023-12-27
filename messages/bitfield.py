import struct

from messages import Message
from messages.ids import IDs


class Bitfield(Message):
    def __init__(self, bitfield: bytes):
        super().__init__(1 + len(bitfield), IDs.bitfield.value)
        self.bitfield: bytearray = bytearray(bitfield)

    def to_bytes(self) -> bytes:
        return struct.pack('>IB', self.len, self.id) + self.bitfield

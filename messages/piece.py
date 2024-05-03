import struct

from messages import Message
from messages.ids import IDs


class Piece(Message):
    def __init__(self, index: int, begin: int, block: bytes):
        super().__init__(9 + len(block), IDs.piece.value)
        self.index = index
        self.begin = begin
        self.block = block

    def to_bytes(self) -> bytes:
        return struct.pack('>IBII', self.message_length, self.uid, self.index, self.begin) + self.block

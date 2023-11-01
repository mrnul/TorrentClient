import struct

from messages import IDs
from messages.message import Message


class Piece(Message):
    def __init__(self, index: int, begin: int, block: bytes):
        super().__init__(9 + len(block), IDs.piece.value)
        self.index = index
        self.begin = begin
        self.block = block

    def to_bytes(self) -> bytes:
        return struct.pack('>IBII', self.len, self.id, self.index, self.begin) + self.block

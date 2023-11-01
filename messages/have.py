import struct

from messages import IDs
from messages.message import Message


class Have(Message):
    def __init__(self, piece_index: int):
        super().__init__(5, IDs.have.value)
        self.piece_index = piece_index

    def to_bytes(self) -> bytes:
        return struct.pack('>IBI', self.len, self.id, self.piece_index)

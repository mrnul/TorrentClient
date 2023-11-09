import struct

from messages.ids import IDs
from messages.message import Message


class Cancel(Message):
    def __init__(self, index: int, begin: int, length: int):
        super().__init__(13, IDs.cancel.value)
        self.index = index
        self.begin = begin
        self.length = length

    def to_bytes(self) -> bytes:
        return struct.pack('>IBIII', self.len, self.id, self.index, self.begin, self.length)

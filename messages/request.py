import struct

from messages import Message
from messages.ids import IDs


class Request(Message):
    def __init__(self, index: int, begin: int, data_length: int):
        super().__init__(13, IDs.request.value)
        self.index = index
        self.begin = begin
        self.data_length = data_length

    def to_bytes(self) -> bytes:
        return struct.pack('>IBIII', self.message_length, self.id, self.index, self.begin, self.data_length)

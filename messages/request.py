import asyncio
import struct
from asyncio import Event

from messages import Message
from messages.ids import IDs


class Request(Message):
    def __init__(self, index: int, begin: int, data_length: int, active_piece=None):
        super().__init__(13, IDs.request.value)
        self.index = index
        self.begin = begin
        self.data_length = data_length
        self.active_piece = active_piece
        self.completed: Event = asyncio.Event()

    def put_request_back(self):
        if self.active_piece:
            self.active_piece.put_request_back(self)

    def to_bytes(self) -> bytes:
        return struct.pack('>IBIII', self.message_length, self.id, self.index, self.begin, self.data_length)

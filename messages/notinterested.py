import struct

from messages import Message
from messages.ids import IDs


class Notinterested(Message):
    def __init__(self):
        super().__init__(1, IDs.not_interested.value)

    def to_bytes(self) -> bytes:
        return struct.pack('>IB', self.len, self.id)

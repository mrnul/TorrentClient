import struct

from messages import Message, IDs


class Extended(Message):
    def __init__(self, ext_id: int, data: bytes):
        super().__init__(2 + len(data), IDs.extended.value)
        self.ext_id = ext_id
        self.data = data

    def to_bytes(self) -> bytes:
        return struct.pack('>IBB', self.message_length, self.id, self.ext_id) + self.data

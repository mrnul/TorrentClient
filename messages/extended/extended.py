import struct

from messages import Message, IDs


class Extended(Message):
    def __init__(self, ext_id: int, raw_data: bytes):
        super().__init__(2 + len(raw_data), IDs.extended.value)
        self.ext_id = ext_id
        self.raw_data = raw_data

    def to_bytes(self) -> bytes:
        return struct.pack('>IBB', self.message_length, self.uid, self.ext_id) + self.raw_data

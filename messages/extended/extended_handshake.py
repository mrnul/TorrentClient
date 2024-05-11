import bencdec
from messages import Message, IDs
from messages.extended.constants import METADATA_SIZE, M, METADATA
from messages.extended.extended import Extended


class ExtendedHandshake(Message):
    def __init__(self, message_length: int, ext_id: int, metadata_uid: int, metadata_size: int):
        super().__init__(message_length, IDs.extended.value)
        self.ext_id = ext_id
        self.metadata_uid = metadata_uid
        self.metadata_size = metadata_size

    def to_bytes(self) -> bytes:
        return Extended(self.ext_id, bencdec.encode(
            {M: {METADATA: self.metadata_uid}, METADATA_SIZE: self.metadata_size}
        )).to_bytes()

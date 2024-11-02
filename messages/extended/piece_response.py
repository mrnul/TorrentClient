import bencdec
from messages import Message, IDs
from messages.extended.constants import MSG_TYPE, PIECE, TOTAL_SIZE
from messages.extended.extended import Extended
from messages.ids import ExtMetadataIDs


class ExtendedMetadataPieceResponse(Message):
    def __init__(self, message_length: int, ext_id: int, piece: int, total_size: int, metadata_part: bytes):
        super().__init__(message_length, IDs.extended.value)
        self.ext_id = ext_id
        self.piece = piece
        self.total_size = total_size
        self.metadata_part = metadata_part

    def to_bytes(self) -> bytes:
        return Extended(self.ext_id, bencdec.encode(
            {
                MSG_TYPE: ExtMetadataIDs.data.value,
                PIECE: self.piece,
                TOTAL_SIZE: self.total_size
            }
        ) + self.metadata_part).to_bytes()

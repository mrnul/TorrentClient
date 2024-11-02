import bencdec
from messages import Message, IDs
from messages.extended.constants import MSG_TYPE, PIECE
from messages.extended.extended import Extended
from messages.ids import ExtMetadataIDs


class ExtendedMetadataPieceReject(Message):
    def __init__(self, message_length: int, ext_id: int, piece: int):
        super().__init__(message_length, IDs.extended.value)
        self.ext_id = ext_id
        self.piece = piece

    def to_bytes(self) -> bytes:
        return Extended(self.ext_id, bencdec.encode(
            {
                MSG_TYPE: ExtMetadataIDs.reject.value,
                PIECE: self.piece
            }
        )).to_bytes()

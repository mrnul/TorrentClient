import struct

import bencdec
from messages import Message, IDs
from messages.ids import ExtMetadataIDs


class Extended(Message):
    def __init__(self, ext_id: int, raw_data: bytes):
        super().__init__(2 + len(raw_data), IDs.extended.value)
        self.ext_id = ext_id
        self.raw_data = raw_data

    def to_bytes(self) -> bytes:
        return struct.pack('>IBB', self.message_length, self.uid, self.ext_id) + self.raw_data


class ExtendedHandshake(Message):
    def __init__(self, message_length: int, ext_id: int, metadata_uid: int, metadata_size: int):
        super().__init__(message_length, IDs.extended.value)
        self.ext_id = ext_id
        self.metadata_uid = metadata_uid
        self.metadata_size = metadata_size

    def to_bytes(self) -> bytes:
        return Extended(self.ext_id, bencdec.encode(
            {b'm': {b'ut_metadata': self.metadata_uid}, b'metadata_size': self.metadata_size}
        )).to_bytes()


class ExtendedMetadataPieceRequest(Message):
    def __init__(self, message_length: int, ext_id: int,  piece: int):
        super().__init__(message_length, IDs.extended.value)
        self.ext_id = ext_id
        self.piece = piece

    def to_bytes(self) -> bytes:
        return Extended(self.ext_id, bencdec.encode(
            {
                b'msg_type': ExtMetadataIDs.request.value,
                b'piece': self.piece
            }
        )).to_bytes()


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
                b'msg_type': ExtMetadataIDs.data.value,
                b'piece': self.piece,
                b'total_size': self.total_size
            }
        ) + self.metadata_part).to_bytes()


class ExtendedMetadataPieceReject(Message):
    def __init__(self, message_length: int, ext_id: int, piece: int):
        super().__init__(message_length, IDs.extended.value)
        self.ext_id = ext_id
        self.piece = piece

    def to_bytes(self) -> bytes:
        return Extended(self.ext_id, bencdec.encode(
            {
                b'msg_type': ExtMetadataIDs.reject.value,
                b'piece': self.piece
            }
        )).to_bytes()


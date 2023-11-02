import hashlib
from typing import Literal

import bencdec
from messages import *


def get_info_sha1_hash(info_decoded_data: dict) -> bytes:
    """
    Takes info dictionary as input and returns the sha1 hash bytes
    """
    info_encoded_data = bencdec.encode(info_decoded_data)
    return hashlib.sha1(info_encoded_data).digest()


def get_message_from_bytes(data: bytes, byteorder: Literal['little', 'big'] = 'big') -> Message:
    msg_len = int.from_bytes(data[0: 4])
    if msg_len == 0:
        return KeepAlive()

    msg_id = int.from_bytes(data[4:5])
    match msg_id:
        case IDs.choke.value:
            return Choke()
        case IDs.unchoke.value:
            return Unchoke()
        case IDs.interested.value:
            return Interested()
        case IDs.not_interested.value:
            return NotInterested()
        case IDs.have.value:
            return Have(piece_index=int.from_bytes(data[5:5], byteorder=byteorder))
        case IDs.bitfield.value:
            return BitField(bitfield=data[5:])
        case IDs.request.value:
            return Request(index=int.from_bytes(data[5:9], byteorder=byteorder),
                           begin=int.from_bytes(data[9:13], byteorder=byteorder),
                           length=int.from_bytes(data[13:17], byteorder=byteorder))
        case IDs.piece.value:
            return Piece(index=int.from_bytes(data[5:9], byteorder=byteorder),
                         begin=int.from_bytes(data[9:13], byteorder=byteorder),
                         block=data[13:])
        case IDs.cancel.value:
            return Cancel(index=int.from_bytes(data[5:9], byteorder=byteorder),
                          begin=int.from_bytes(data[9:13], byteorder=byteorder),
                          length=int.from_bytes(data[13:17], byteorder=byteorder))
        case _:
            return Unknown(msg_len, msg_id, data[5:])

import hashlib

from messages import Message, Choke, Unchoke, Interested, Notinterested, Have, Bitfield, Request, Piece, Cancel, \
    Unknown
from messages.ids import IDs


def calculate_hash(data: bytes) -> bytes:
    return hashlib.sha1(data).digest()


def bytes_to_msg(msg_id: int, data: bytes) -> Message:
    """
    Translates data to the appropriate message given the message id
    """
    match msg_id:
        case IDs.choke.value:
            return Choke()
        case IDs.unchoke.value:
            return Unchoke()
        case IDs.interested.value:
            return Interested()
        case IDs.not_interested.value:
            return Notinterested()
        case IDs.have.value:
            return Have(piece_index=int.from_bytes(data))
        case IDs.bitfield.value:
            return Bitfield(bitfield=data)
        case IDs.request.value:
            return Request(index=int.from_bytes(data[0:4]),
                           begin=int.from_bytes(data[4:8]),
                           length=int.from_bytes(data[8:12]))
        case IDs.piece.value:
            return Piece(index=int.from_bytes(data[0:4]),
                         begin=int.from_bytes(data[4:8]),
                         block=data[8:])
        case IDs.cancel.value:
            return Cancel(index=int.from_bytes(data[0:4]),
                          begin=int.from_bytes(data[4:8]),
                          length=int.from_bytes(data[8:13]))
        case _:
            return Unknown(msg_id, data)

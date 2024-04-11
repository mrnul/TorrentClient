import asyncio
import hashlib
from typing import Coroutine

from messages import Message, Choke, Unchoke, Interested, NotInterested, Have, Bitfield, Request, Piece, Cancel, \
    Unknown, Keepalive
from messages.extended import Extended
from messages.ids import IDs


def calculate_hash(data: bytes) -> bytes:
    return hashlib.sha1(data).digest()


def mem_view_to_msg(msg_id: int, data: memoryview) -> Message:
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
            return NotInterested()
        case IDs.have.value:
            return Have(piece_index=int.from_bytes(data))
        case IDs.bitfield.value:
            return Bitfield(bitfield=bytes(data))
        case IDs.request.value:
            return Request(index=int.from_bytes(data[:4]),
                           begin=int.from_bytes(data[4:8]),
                           data_length=int.from_bytes(data[8:12]))
        case IDs.piece.value:
            return Piece(index=int.from_bytes(data[:4]),
                         begin=int.from_bytes(data[4:8]),
                         block=bytes(data[8:]))
        case IDs.cancel.value:
            return Cancel(index=int.from_bytes(data[:4]),
                          begin=int.from_bytes(data[4:8]),
                          data_length=int.from_bytes(data[8:13]))
        case IDs.extended.value:
            return Extended(int.from_bytes(data[:1]),
                            data=bytes(data[1:]))
        case _:
            return Unknown(msg_id, bytes(data))


def buffer_to_msg(data: bytearray) -> Message | None:
    data_mem_view = memoryview(data)
    if len(data_mem_view) < 4:
        return None
    msg_len = int.from_bytes(data_mem_view[0:4])
    if msg_len == 0:
        return Keepalive()
    if len(data_mem_view[4:]) < msg_len:
        return None
    msg_id = int.from_bytes(data_mem_view[4:5])
    msg = mem_view_to_msg(msg_id, data_mem_view[5: msg_len + 5 - 1])
    return msg


async def run_with_timeout(coro: Coroutine, timeout: float) -> bool:
    try:
        async with asyncio.timeout(timeout):
            await coro
    except TimeoutError:
        return False
    return True

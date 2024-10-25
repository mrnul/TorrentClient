import asyncio
import hashlib
from asyncio import Task
from typing import Coroutine

import bencdec
from messages import Message, Choke, Unchoke, Interested, NotInterested, Have, Bitfield, Request, Piece, Cancel, \
    Unknown, Keepalive
from messages.extended import ExtendedHandshake, ExtendedMetadataPieceRequest, ExtendedMetadataPieceResponse, \
    ExtendedMetadataPieceReject
from messages.extended.constants import *
from messages.ids import IDs, ExtMetadataIDs, ExtIDs


def calculate_hash(data: bytes) -> bytes:
    return hashlib.sha1(data).digest()


def mem_view_to_msg(msg_id: int, data: memoryview) -> Message:
    """
    Translates data to the appropriate message given the message id.
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
            return Have(piece_index=int.from_bytes(data, byteorder="big"))
        case IDs.bitfield.value:
            return Bitfield(bitfield=bytes(data))
        case IDs.request.value:
            return Request(index=int.from_bytes(data[:4], byteorder="big"),
                           begin=int.from_bytes(data[4:8], byteorder="big"),
                           data_length=int.from_bytes(data[8:12], byteorder="big"))
        case IDs.piece.value:
            return Piece(index=int.from_bytes(data[:4], byteorder="big"),
                         begin=int.from_bytes(data[4:8], byteorder="big"),
                         block=bytes(data[8:]))
        case IDs.cancel.value:
            return Cancel(index=int.from_bytes(data[:4], byteorder="big"),
                          begin=int.from_bytes(data[4:8], byteorder="big"),
                          data_length=int.from_bytes(data[8:13], byteorder="big"))
        case IDs.extended.value:
            ext_id = int.from_bytes(data[:1], byteorder="big")
            raw_data = bytes(data[1:])
            message_length = 2 + len(raw_data)
            decoded_data, offset = bencdec.decode(raw_data)
            if ext_id == ExtIDs.handshake.value:
                metadata_size = decoded_data[METADATA_SIZE]
                metadata_uid = None
                m: dict[bytes, int] = decoded_data[M]
                for key, value in m.items():
                    if b'metadata' in key:
                        metadata_uid = value
                return ExtendedHandshake(message_length, ext_id, metadata_uid, metadata_size)
            elif ext_id == ExtIDs.metadata.value:
                message_type = decoded_data[MSG_TYPE]
                piece = decoded_data[PIECE]
                if message_type == ExtMetadataIDs.request.value:
                    return ExtendedMetadataPieceRequest(message_length, ext_id, piece)
                elif message_type == ExtMetadataIDs.data.value:
                    return ExtendedMetadataPieceResponse(
                        message_length,
                        ext_id,
                        piece,
                        decoded_data[TOTAL_SIZE],
                        raw_data[offset:])
                elif message_type == ExtMetadataIDs.reject.value:
                    return ExtendedMetadataPieceReject(message_length, ext_id, piece)
    return Unknown(msg_id, bytes(data))


def buffer_to_msg(data: bytearray) -> Message | None:
    """
    The function expects the first four bytes of the buffer to represent the length of the message.
    If the length is zero, a Keepalive object is returned.
    If the buffer is too short or the indicated message length exceeds the available data, None is returned.
    """
    data_mem_view = memoryview(data)
    if len(data_mem_view) < 4:
        return None
    msg_len = int.from_bytes(data_mem_view[0:4], byteorder="big")
    if msg_len == 0:
        return Keepalive()
    if len(data_mem_view[4:]) < msg_len:
        return None
    msg_id = int.from_bytes(data_mem_view[4:5], byteorder="big")
    msg = mem_view_to_msg(msg_id, data_mem_view[5: msg_len + 5 - 1])
    return msg


async def run_with_timeout(coro: Coroutine, timeout: float) -> bool:
    """
    Simply awaits the coro with a timeout.
    Returns true if coro is completed and false if timeout occurs
    """
    try:
        async with asyncio.timeout(timeout):
            await coro
    except TimeoutError:
        return False
    return True


async def cancel_tasks(tasks: set[Task]):
    """
    Method to cancel and await for tasks to complete
    """
    if not tasks:
        return
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

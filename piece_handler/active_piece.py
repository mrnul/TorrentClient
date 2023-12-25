import asyncio
import hashlib

import messages
from messages import Request
from piece_handler import PieceInfo


class ActivePiece:
    __MAX_REQUEST_LENGTH__ = 2 ** 14

    def __init__(self):
        self.piece_info: PieceInfo | None = None
        self.data: bytearray = bytearray()
        self.requests: asyncio.Queue[Request] = asyncio.Queue()

    def set(self, piece_info: PieceInfo | None):
        self.piece_info: PieceInfo = piece_info
        if self.piece_info is None:
            return
        self.data = bytearray(piece_info.length)
        self._build_requests()

    def update_data_from_piece_message(self, piece: messages.Piece):
        a = piece.begin
        b = piece.begin + len(piece.block)
        self.data[a:b:] = piece.block

    def is_hash_ok(self) -> bool:
        return hashlib.sha1(self.data).digest() == self.piece_info.hash_value

    def _build_requests(self):
        bytes_left = self.piece_info.length
        offset = 0
        while bytes_left:
            length = min(self.__MAX_REQUEST_LENGTH__, bytes_left)
            self.requests.put_nowait(Request(self.piece_info.index, offset, length))
            offset += length
            bytes_left -= length

    async def join_queue(self):
        await self.requests.join()
        return self

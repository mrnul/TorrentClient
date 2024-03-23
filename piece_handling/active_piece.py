import asyncio

from messages import Request, Piece
from misc import utils
from piece_handling.piece_info import PieceInfo


class ActivePiece:
    """
    Active piece is a piece that peers can perform requests and download
    """
    __MAX_REQUEST_LENGTH__ = 2 ** 14

    def __init__(self, uid: int | None = None, piece_info: PieceInfo | None = None, data: bytearray = bytearray()):
        self.uid: int | None = uid
        self.piece_info: PieceInfo | None = piece_info
        self.data: bytearray = data
        self._requests: asyncio.Queue[Request] = asyncio.Queue() if uid is not None else None

    def set(self, piece_info: PieceInfo | None):
        self.piece_info = piece_info
        self.data = bytearray()
        if self.piece_info is None:
            return
        self.data = bytearray(piece_info.length)
        self._build_requests()

    def update_data_from_piece_message(self, piece: Piece) -> bool:
        """
        Whenever a piece is received data should be updated inside active piece
        """
        if piece.index != self.piece_info.index:
            return False
        a = piece.begin
        b = piece.begin + len(piece.block)
        self.data[a:b:] = piece.block
        self._requests.task_done()
        return True

    def is_hash_ok(self) -> bool:
        return utils.calculate_hash(self.data) == self.piece_info.hash_value

    def _build_requests(self):
        """
        In order to download pieces requests should be made to other peers
        Build the appropriate requests to be ready for transmission
        """
        bytes_left = self.piece_info.length
        offset = 0
        while bytes_left:
            length = min(self.__MAX_REQUEST_LENGTH__, bytes_left)
            self._requests.put_nowait(Request(self.piece_info.index, offset, length))
            offset += length
            bytes_left -= length

    async def join_queue(self):
        await self._requests.join()
        return self

    def get_request(self):
        return self._requests.get_nowait()

    def put_request_back(self, request: Request) -> bool:
        """
        In case a request is not fulfilled for some reason, put the request back
        Some peer will grab it to retry
        """
        if request is None or self.piece_info is None:
            return False
        if request.index != self.piece_info.index:
            return False
        self._requests.put_nowait(request)
        self._requests.task_done()
        return True

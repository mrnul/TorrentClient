from messages import Request
from misc import utils
from misc.structures import QueueExt
from piece_handling.piece_info import PieceInfo


class ActivePiece:
    """
    Active piece is a piece that peers can perform requests and download
    """
    def __init__(self, piece_info: PieceInfo, max_request_length: int = 2 ** 14):
        self.piece_info: PieceInfo = piece_info
        self._requests: QueueExt[Request] = QueueExt()
        self._max_request_length = max_request_length
        self._build_requests()

    def __repr__(self):
        return f"index: {self.piece_info.index} | requests: {self._requests.qsize()}"

    def is_hash_ok(self, data: bytes) -> bool:
        return utils.calculate_hash(data) == self.piece_info.hash_value

    def _build_requests(self):
        """
        In order to download pieces requests should be made to other peers
        Build the appropriate requests to be ready for transmission
        """
        bytes_left = self.piece_info.length
        offset = 0
        while bytes_left:
            length = min(self._max_request_length, bytes_left)
            self._requests.put_nowait(Request(self.piece_info.index, offset, length))
            offset += length
            bytes_left -= length

    async def join_queue(self):
        await self._requests.join()
        return self

    def get_request(self):
        if self._requests.qsize() > 0:
            return self._requests.get_nowait()
        return None

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
        return True

    def request_done(self):
        self._requests.task_done()

import asyncio
from asyncio import Event

from messages import Request
from piece_handling.active_piece import ActivePiece


class ActiveRequest:
    """
    Active request is a request that can be passed into XXXPeerProtocol.perform_request

    It will be handled automatically by the protocol
    """
    def __init__(self, active_piece: ActivePiece, request: Request):
        self.active_piece = active_piece
        self.request = request
        self.completed: Event = asyncio.Event()

    @staticmethod
    def from_active_piece(active_piece: ActivePiece):
        if request := active_piece.get_request():
            return ActiveRequest(active_piece, request)
        return None

    @property
    def index(self) -> int:
        return self.request.index

    @property
    def begin(self) -> int:
        return self.request.begin

    @property
    def data_length(self) -> int:
        return self.request.data_length

    def on_success(self):
        self.completed.set()
        self.active_piece.request_done()

    def on_failure(self):
        self.completed.clear()
        self.active_piece.put_request_back(self.request)
        self.active_piece.request_done()

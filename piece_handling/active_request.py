import asyncio
from asyncio import Event

from messages import Request
from piece_handling.active_piece import ActivePiece


class ActiveRequest:
    def __init__(self, active_piece: ActivePiece, request: Request):
        self.active_piece = active_piece
        self.request = request
        self.completed: Event = asyncio.Event()

    @property
    def index(self) -> int:
        return self.request.index

    @property
    def begin(self) -> int:
        return self.request.begin

    @property
    def data_length(self) -> int:
        return self.request.data_length

    def put_request_back(self):
        self.active_piece.put_request_back(self.request)

    def request_processed(self):
        self.active_piece.request_done()

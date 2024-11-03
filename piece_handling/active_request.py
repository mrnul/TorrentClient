import asyncio
import time
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
        self.start_time: float = time.time()
        self.end_time: float = 0.0

    @staticmethod
    def from_active_piece(active_piece: ActivePiece):
        """
        Builds an ActiveRequest from ActivePiece.
        None is returned if this piece has no requests in queue
        """
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
        """
        On success set completion event and update queue by marking task as done
        """
        self.completed.set()
        self.active_piece.request_done()
        self.end_time = time.time()

    def on_failure(self):
        """
        On failure clear completion event, put request back in queue
        and update queue by marking task as done
        """
        self.completed.clear()
        self.active_piece.put_request_back(self.request)
        self.active_piece.request_done()
        self.end_time = time.time()


    def duration(self) -> float:
        return self.end_time - self.start_time

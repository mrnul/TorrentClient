import time

from messages import Request
from peer import Peer


class PieceInfo:
    request_threshold_seconds = 10

    def __init__(self, hash_value: bytes, index: int, length: int):
        self.hash_value: bytes = hash_value
        self.index: int = index
        self.length: int = length
        self.time_requested: float = 0.0
        self.done: bool = False

    def should_request(self) -> bool:
        return not self.done and time.time() - self.time_requested > self.request_threshold_seconds

    def request(self, from_peer: Peer) -> bool:
        if self.should_request() and not from_peer.am_choked:
            self.time_requested = time.time()
            return from_peer.send_msg(Request(self.index, 0, self.length))
        return False

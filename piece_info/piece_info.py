import time

from messages import Request
from peer import Peer


class PieceInfo:
    request_wait = 10.0

    def __init__(self, hash_value: bytes, index: int, length: int):
        self.hash_value: bytes = hash_value
        self.index: int = index
        self.length: int = length
        self.done: bool = False
        self.requested_time: float = 0.0

    def should_request(self) -> bool:
        return time.time() - self.requested_time > self.request_wait and not self.done

    def request_from_peer(self, peer: Peer) -> bool:
        if peer.send_msg(Request(self.index, 0, self.length)):
            self.requested_time = time.time()
            return True
        return False

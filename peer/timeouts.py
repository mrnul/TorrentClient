import dataclasses


@dataclasses.dataclass
class Timeouts:
    Request: float = 10.0  # Number of seconds until a request is timed-out (not responded)
    Send: float = 5.0  # Number of seconds until send timeout occurs
    Unchoke: float = 10.0  # Number of seconds until timeout when waiting for unchoke
    Handshake: float = 12.0  # Number of seconds to wait for handshake
    Keep_alive: float = 60.0  # Number of seconds to pass before sending a Keepalive message
    Punish_queue: float = 1.0  # When no active piece is found peer is being punished by sleeping
    Punish_request: float = 10.0  # When a Request timeout occurs peer is being punished by sleeping

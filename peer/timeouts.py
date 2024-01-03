import dataclasses


@dataclasses.dataclass
class Timeouts:
    Q: float = 5.0  # Number of seconds until queue get timeout occurs
    Request: float = 5.0  # Number of seconds until a request is timed-out (not responded)
    Send: float = 5.0  # Number of seconds until send timeout occurs
    General: float = 30.0  # Number of seconds until timeout when not able to perform request
    Handshake: float = 10.0  # Number of seconds to wait for handshake
    Keep_alive: float = 60.0  # Number of seconds to pass before sending a Keepalive message
    Punish: float = 5.0  # When a Request timeout occurs peer is being punished by sleeping

import dataclasses


@dataclasses.dataclass
class Timeouts:
    Request: float = 10.0  # Number of seconds until a request is timed-out (not responded)
    Handshake: float = 12.0  # Number of seconds to wait for handshake
    Keepalive: float = 60.0  # Number of seconds to pass before sending a Keepalive message
    Metadata: float = 30.0  # Number of seconds to wait for metadata completion
    Progress: float = 1.0  # Wait at most this number of seconds to print progress


@dataclasses.dataclass
class Punishments:
    Request: float = 10.0  # When a Request timeout / error occurs peer is being punished by sleeping

import dataclasses


@dataclasses.dataclass(frozen=True)
class Timeouts:
    # Number of seconds until a request is timed-out (not responded)
    Request: float = 10.0

    # Number of seconds to wait for handshake
    Handshake: float = 12.0

    # Number of seconds to pass before sending a Keepalive message
    Keepalive: float = 60.0

    # Number of seconds to wait for metadata completion
    Metadata: float = 30.0

    # Wait at most this number of seconds to print progress
    Progress: float = 1.0


@dataclasses.dataclass(frozen=True)
class Punishments:
    # When a peer cannot grab an active request punish by sleeping
    # (for example, we are missing piece index I, but peer does not have that piece)
    ActiveRequest: float = 5.0

    # When a Request timeout / error occurs peer is being punished by sleeping
    Request: float = 10.0


@dataclasses.dataclass(frozen=True)
class Limits:
    MaxActiveRequests: int = 4  # the number of active requests a peer should wait at a time

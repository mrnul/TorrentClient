import dataclasses


@dataclasses.dataclass(frozen=True)
class PeerInfo:
    ip: str
    port: int
    peer_id_tracker: bytes = dataclasses.field(compare=False, hash=False, default=b'<Empty>')

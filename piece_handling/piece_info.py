import dataclasses


@dataclasses.dataclass(frozen=True)
class PieceInfo:
    hash_value: bytes
    index: int
    length: int

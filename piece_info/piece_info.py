import dataclasses


@dataclasses.dataclass
class PieceInfo:
    hash_value: bytes
    index: int
    length: int

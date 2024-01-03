import dataclasses
from typing import BinaryIO


@dataclasses.dataclass(frozen=True)
class File:
    io: BinaryIO
    size: int
    start_byte_in_torrent: int
    end_byte_in_torrent: int

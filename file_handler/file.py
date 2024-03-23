import dataclasses
from typing import BinaryIO

from file_handler.file_info import FileInfo


@dataclasses.dataclass(frozen=True)
class File:
    io: BinaryIO
    info: FileInfo

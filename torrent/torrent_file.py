from typing import BinaryIO


class TorrentFile:
    def __init__(self,  f: BinaryIO, size: int):
        self.__size: int = size
        self.__f: BinaryIO = f

    @property
    def size(self) -> int:
        return self.__size

    @property
    def file(self) -> BinaryIO:
        return self.__f

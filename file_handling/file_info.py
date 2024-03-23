import dataclasses


@dataclasses.dataclass
class FileInfo:
    path: str
    size: int
    start_byte_in_torrent: int
    end_byte_in_torrent: int

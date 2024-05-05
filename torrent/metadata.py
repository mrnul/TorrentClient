import bencdec
from file_handling.file_info import FileInfo
from misc import utils
from piece_handling.piece_info import PieceInfo
from torrent.constants import *


class Metadata:
    __METADATA_PIECE_SIZE__ = 2 ** 14

    def __init__(self, info_dict: dict, expected_info_hash: bytes = bytes()):
        self.info_dict: dict = info_dict
        self.files_info: tuple[FileInfo, ...] = tuple()
        self.total_size: int = 0
        self.piece_size: int = 0
        self.pieces_info: tuple[PieceInfo, ...] = tuple()
        self.expected_info_hash: bytes = expected_info_hash
        self.info_hash: bytes | None = None
        self._load_data()

    def _info_dict_contains_all_needed_fields(self) -> bool:
        if PIECE_LENGTH not in self.info_dict:
            return False
        if PIECES not in self.info_dict:
            return False
        if NAME not in self.info_dict:
            return False
        if FILES not in self.info_dict:
            return False
        for file in self.info_dict[FILES]:
            if LENGTH not in file:
                return False
            if PATH not in file:
                return False
        return True

    def _load_data(self) -> bool:
        if not self._info_dict_contains_all_needed_fields():
            return False
        self.info_hash = self._calc_info_sha1_hash()
        if self.expected_info_hash:
            if self.info_hash != self.expected_info_hash:
                return False
        self.files_info = self._parse_files()
        self.total_size = self.files_info[-1].end_byte_in_torrent + 1
        self.piece_size = self.info_dict[PIECE_LENGTH]
        self.pieces_info = self._load_torrent_pieces()
        self._encoded_info = bencdec.encode(self.info_dict)
        return True

    def _calc_info_sha1_hash(self) -> bytes:
        """
        Takes torrent dictionary as input and returns the sha1 hash bytes
        """
        info_encoded_data = bencdec.encode(self.info_dict)
        return utils.calculate_hash(info_encoded_data)

    def _load_torrent_pieces(self) -> tuple[PieceInfo, ...]:
        """
        Get list of PieceInfo for every piece in torrent
        """
        remaining_size: int = self.total_size
        piece_info_list: list[PieceInfo] = []
        if not self.info_dict:
            return tuple()
        for p, i in enumerate(self.info_dict[PIECES].hex(' ', 20).split(' ')):
            piece_info_list.append(
                PieceInfo(
                    bytes.fromhex(i), p,
                    min(self.piece_size, remaining_size)
                )
            )
            remaining_size -= self.piece_size
        return tuple(piece_info_list)

    def _parse_files(self) -> tuple[FileInfo, ...]:
        """
        Get a list of FileInfo that contain information about files in torrent
        """
        illegal_path_chars = '|:?*<>\"'
        files: list[FileInfo] = []
        root_dir = f'./{self.info_dict[NAME].decode()}'
        if len(root_dir) == 0:
            root_dir = '.'
        start_byte = 0
        for file in self.info_dict[FILES]:
            path = '/'.join([p.decode() for p in file[PATH]])
            path = ''.join(map(lambda x: '_' if x in illegal_path_chars else x, path))
            path = f"{root_dir}/{path}"
            size = int(file[LENGTH])
            files.append(FileInfo(path, size, start_byte, start_byte + size - 1))
            start_byte += size
        return tuple(files)

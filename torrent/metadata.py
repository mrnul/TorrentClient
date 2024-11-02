import bencdec
from file_handling.file_info import FileInfo
from misc import utils
from piece_handling.piece_info import PieceInfo
from torrent.constants import *


class Metadata:
    __METADATA_PIECE_SIZE__ = 2 ** 14

    def __init__(self, decoded_info_data: dict):
        self.encoded_info_data: bytes | str = bencdec.encode(decoded_info_data)
        self.expected_info_hash: bytes = utils.calculate_hash(self.encoded_info_data)
        self.decoded_info_data: dict = {}
        self.files_info: tuple[FileInfo, ...] = tuple()
        self.torrent_size: int = 0
        self.piece_size: int = 0
        self.pieces_info: tuple[PieceInfo, ...] = tuple()
        self.info_hash: bytes = bytes()
        self._validate_data()

    def _info_dict_contains_all_needed_fields(self) -> bool:
        if PIECE_LENGTH not in self.decoded_info_data:
            return False
        if PIECES not in self.decoded_info_data:
            return False
        if NAME not in self.decoded_info_data:
            return False
        if FILES not in self.decoded_info_data:
            return False
        for file in self.decoded_info_data[FILES]:
            if LENGTH not in file:
                return False
            if PATH not in file:
                return False
        return True

    def _validate_data(self) -> bool:
        self.decoded_info_data = bencdec.decode(self.encoded_info_data)[0]
        if not self._info_dict_contains_all_needed_fields():
            return False
        self.info_hash = utils.calculate_hash(self.encoded_info_data)
        if self.info_hash != self.expected_info_hash:
            return False
        self._parse_files()
        self._load_torrent_pieces()
        return True

    def _load_torrent_pieces(self):
        """
        Get list of PieceInfo for every piece in torrent
        """
        self.piece_size = self.decoded_info_data[PIECE_LENGTH]
        remaining_size: int = self.torrent_size
        piece_info_list: list[PieceInfo] = []
        if not self.decoded_info_data:
            return tuple()
        for p, i in enumerate(self.decoded_info_data[PIECES].hex(' ', 20).split(' ')):
            piece_info_list.append(
                PieceInfo(
                    bytes.fromhex(i), p,
                    min(self.piece_size, remaining_size)
                )
            )
            remaining_size -= self.piece_size
        self.pieces_info = tuple(piece_info_list)
        self.piece_count = len(self.pieces_info)

    def _parse_files(self):
        """
        Get a list of FileInfo that contain information about files in torrent
        """
        illegal_path_chars = '|:?*<>\"'
        files: list[FileInfo] = []
        root_dir = f'./{self.decoded_info_data[NAME].decode()}'
        if len(root_dir) == 0:
            root_dir = '.'
        start_byte = 0
        for file in self.decoded_info_data[FILES]:
            path = '/'.join([p.decode() for p in file[PATH]])
            path = ''.join(map(lambda x: '_' if x in illegal_path_chars else x, path))
            path = f"{root_dir}/{path}"
            size = int(file[LENGTH])
            files.append(FileInfo(path, size, start_byte, start_byte + size - 1))
            start_byte += size
        self.files_info = tuple(files)
        self.torrent_size = self.files_info[-1].end_byte_in_torrent + 1

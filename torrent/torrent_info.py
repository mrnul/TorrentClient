import bencdec
from misc import utils
from piece_handling.piece_info import PieceInfo
from torrent.constants import *
from file_handler.file_info import FileInfo


class TorrentInfo:
    def __init__(self, torrent_file: str, port: int, self_id: bytes):
        torrent_decoded_data = self._decode_torrent_file(torrent_file)
        self.torrent_file: str = torrent_file
        self.trackers: set[str] = self._parse_trackers(torrent_decoded_data)
        self.info_hash: bytes = self._calc_info_sha1_hash(torrent_decoded_data)
        self.self_port: int = port
        self.self_id: bytes = self._build_self_id(self_id)
        self.files_info: tuple[FileInfo, ...] = self._parse_files(torrent_decoded_data)
        self.total_size: int = self._calculate_total_size(torrent_decoded_data)
        self.piece_size = torrent_decoded_data[INFO][PIECE_LENGTH]
        self.pieces_info: tuple[PieceInfo, ...] = self._load_torrent_pieces(torrent_decoded_data, self.total_size)

    @staticmethod
    def _build_self_id(self_id: bytes, length: int = 20) -> bytes:
        result = bytearray(self_id)
        if len(result) > length:
            return result[:length]
        self_id += b' ' * (length - len(result))
        return bytes(self_id)

    @staticmethod
    def _decode_torrent_file(torrent_file: str) -> dict:
        with open(torrent_file, mode='rb') as f:
            return bencdec.decode(f.read())

    @staticmethod
    def _parse_trackers(torrent_decoded_data: dict) -> set[str]:
        trackers: set[str] = set()
        if ANNOUNCE in torrent_decoded_data:
            trackers |= {torrent_decoded_data[ANNOUNCE].decode()}
        if ANNOUNCE_LIST in torrent_decoded_data:
            trackers |= {tracker[0].decode() for tracker in torrent_decoded_data[ANNOUNCE_LIST]}
        return trackers

    @staticmethod
    def _calc_info_sha1_hash(torrent_decoded_data: dict) -> bytes:
        """
        Takes torrent dictionary as input and returns the sha1 hash bytes
        """
        info_encoded_data = bencdec.encode(torrent_decoded_data[INFO])
        return utils.calculate_hash(info_encoded_data)

    @staticmethod
    def _parse_files(torrent_decoded_data: dict) -> tuple[FileInfo, ...]:
        illegal_path_chars = '/|\\:?*<>\"'
        files: list[FileInfo] = []
        root_dir = f'./{torrent_decoded_data[INFO][NAME].decode()}'
        if len(root_dir) == 0:
            root_dir = '.'
        start_byte = 0
        for file in torrent_decoded_data[INFO][FILES]:
            path = '/'.join([p.decode() for p in file[PATH]])
            path = ''.join(map(lambda x: '_' if x in illegal_path_chars else x, path))
            path = f"{root_dir}/{path}"
            size = int(file[LENGTH])
            files.append(FileInfo(path, size, start_byte, start_byte + size - 1))
            start_byte += size
        return tuple(files)

    @staticmethod
    def _calculate_total_size(torrent_decoded_data: dict) -> int:
        return sum(int(file[LENGTH]) for file in torrent_decoded_data[INFO][FILES])

    @staticmethod
    def _load_torrent_pieces(torrent_decoded_data: dict, total_size: int) -> tuple[PieceInfo, ...]:
        remaining_size: int = total_size
        piece_info_list: list[PieceInfo] = []
        piece_length: int = torrent_decoded_data[INFO][PIECE_LENGTH]
        for p, i in enumerate(torrent_decoded_data[INFO][PIECES].hex(' ', 20).split(' ')):
            piece_info_list.append(
                PieceInfo(bytes.fromhex(i), p,
                          min(piece_length, remaining_size))
            )
            remaining_size -= piece_length
        return tuple(piece_info_list)

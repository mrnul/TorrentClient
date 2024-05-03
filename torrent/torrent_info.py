import bencdec
from misc import utils
from piece_handling.piece_info import PieceInfo
from torrent.constants import *
from file_handling.file_info import FileInfo


class TorrentInfo:
    """
    Class to parse torrent file and hold info in a convenient way
    """

    def __init__(self, torrent_file: str, port: int, self_id: bytes, max_request_length: int = 2 ** 14,
                 max_active_pieces: int = 0):
        torrent_decoded_data = self._decode_torrent_file(torrent_file)
        self.torrent_file: str = torrent_file
        self.trackers: set[str] = self._parse_trackers(torrent_decoded_data)
        self.info_hash: bytes = self._calc_info_sha1_hash(torrent_decoded_data)
        self.self_port: int = port
        self.self_id: bytes = self._build_self_id(self_id)
        self.files_info: tuple[FileInfo, ...] = self._parse_files(torrent_decoded_data)
        self.total_size: int = self.files_info[-1].end_byte_in_torrent + 1
        self.piece_size = torrent_decoded_data[INFO][PIECE_LENGTH]
        self.pieces_info: tuple[PieceInfo, ...] = self._load_torrent_pieces(torrent_decoded_data, self.total_size)
        self.max_request_length = max_request_length
        self.max_active_pieces = max_active_pieces

    @staticmethod
    def _build_self_id(self_id: bytes, length: int = 20) -> bytes:
        """
        Ensures that self_id is exactly length bytes long
        """
        result = bytearray(self_id)
        if len(result) > length:
            return result[:length]
        self_id += b' ' * (length - len(result))
        return bytes(self_id)

    @staticmethod
    def _decode_torrent_file(torrent_file: str) -> dict:
        """
        Decides bencoded torrent data
        """
        with open(torrent_file, mode='rb') as f:
            return bencdec.decode(f.read())[0]

    @staticmethod
    def _parse_trackers(torrent_decoded_data: dict) -> set[str]:
        """
        Get tracker info from torrent file
        """
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
        """
        Get a list of FileInfo that contain information about files in torrent
        """
        illegal_path_chars = '|:?*<>\"'
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
        """
        Get the total size of all files in torrent
        """
        return sum(int(file[LENGTH]) for file in torrent_decoded_data[INFO][FILES])

    @staticmethod
    def _load_torrent_pieces(torrent_decoded_data: dict, total_size: int) -> tuple[PieceInfo, ...]:
        """
        Get list of PieceInfo for every piece in torrent
        """
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

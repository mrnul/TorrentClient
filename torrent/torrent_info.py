from misc import utils
from piece_handler import PieceInfo
from torrent.constants import INFO, PIECE_LENGTH
from torrent.file import File


class TorrentInfo:
    def __init__(self, torrent_file: str, port: int, self_id: bytes):
        self.torrent_file: str = torrent_file
        self.torrent_decoded_data = utils.load_torrent_file(self.torrent_file)
        self.trackers: set[str] = utils.get_trackers(self.torrent_decoded_data)
        self.info_hash: bytes = utils.get_info_sha1_hash(self.torrent_decoded_data)
        self.port: int = port
        self.self_id: bytes = self_id
        self.torrent_files: list[File] = utils.get_torrent_files(self.torrent_decoded_data)
        self.total_size: int = utils.get_torrent_total_size(self.torrent_files)
        self.piece_size = self.torrent_decoded_data[INFO][PIECE_LENGTH]
        self.pieces_info: list[PieceInfo] = utils.parse_torrent_pieces(self.torrent_decoded_data, self.total_size)

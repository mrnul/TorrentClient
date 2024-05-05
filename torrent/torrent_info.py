import bencdec
from torrent.constants import *
from torrent.metadata import Metadata


class TorrentInfo:
    """
    Class to parse torrent file and hold info in a convenient way
    """

    def __init__(self, torrent_file: str, port: int, self_id: bytes, max_request_length: int = 2 ** 14,
                 max_active_pieces: int = 0):
        torrent_decoded_data = self._decode_torrent_file(torrent_file)
        self.torrent_file: str = torrent_file
        self.trackers: set[str] = self._parse_trackers(torrent_decoded_data)
        self.metadata: Metadata = Metadata(torrent_decoded_data.get(INFO, {}))
        self.self_port: int = port
        self.self_id: bytes = self._build_self_id(self_id)
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


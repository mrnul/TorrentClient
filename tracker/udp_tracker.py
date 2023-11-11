import random
import socket
import struct
import urllib.parse

from misc import utils
from peer.peer_info import PeerInfo
from torrent.torrent_info import TorrentInfo
from tracker.tracker_base import TrackerBase


class UDPTracker(TrackerBase):
    __UDP_MAX_PACKET_SIZE__ = 65535

    def request_peers(self, torrent_info: TorrentInfo) -> set[PeerInfo]:
        peer_data = set()
        transaction_id = int.from_bytes(random.randbytes(4))
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1.0)
        s.bind(('', torrent_info.port))
        msg = struct.pack(">QII", 0x41727101980, 0, transaction_id)

        parsed_url = urllib.parse.urlparse(self.tracker)
        try:
            bytes_sent = s.sendto(msg, (parsed_url.hostname, parsed_url.port))
        except socket.error:
            return peer_data

        if len(msg) != bytes_sent:
            return peer_data

        try:
            rxed_data = s.recvfrom(self.__UDP_MAX_PACKET_SIZE__)[0]
        except socket.error:
            return peer_data

        action, s_transaction_id, conn_id = struct.unpack_from('>IIQ', rxed_data)
        if action != 0 or transaction_id != s_transaction_id:
            return peer_data

        key = int.from_bytes(random.randbytes(2))
        msg = struct.pack('>QII', conn_id, 1, transaction_id)
        msg += utils.get_info_sha1_hash(torrent_info.torrent_decoded_data)
        msg += torrent_info.self_id
        msg += struct.pack('>QQQIIIiHH', 0, 0, 0, 0, 0, key, -1, torrent_info.port, 2)
        msg += struct.pack('>B', len(parsed_url.path))
        msg += parsed_url.path.encode()
        try:
            bytes_sent = s.sendto(msg, (parsed_url.hostname, parsed_url.port))
        except socket.error:
            return peer_data

        if len(msg) != bytes_sent:
            return peer_data

        try:
            rxed_data = s.recvfrom(self.__UDP_MAX_PACKET_SIZE__)[0]
        except socket.error:
            return peer_data

        action, transaction_id, interval, leechers, seeders = struct.unpack_from('>IIIII', rxed_data)
        data_len = len(rxed_data)

        for offset in range(20, data_len, 6):
            ip, port = struct.unpack_from('>IH', rxed_data, offset)
            ip_str = '.'.join(str(byte) for byte in int(ip).to_bytes(4))
            peer_data.add(PeerInfo(ip_str, port))

        return peer_data

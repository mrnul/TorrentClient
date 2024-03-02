from typing import OrderedDict

import requests

import bencdec
from misc import utils
from peer.peer_info import PeerInfo
from torrent.constants import *
from torrent.torrent_info import TorrentInfo
from tracker.tracker_base import TrackerBase


class HttpTracker(TrackerBase):
    def request_peers(self, torrent_info: TorrentInfo) -> set[PeerInfo]:
        peer_data = set()
        r = requests.get(self.tracker, params={
            'info_hash': utils.get_info_sha1_hash(torrent_info.torrent_decoded_data),
            'peer_id': torrent_info.self_id,
            'port': torrent_info.self_port
        }, timeout=5.0)
        response = bencdec.decode(r.content)
        for p in response[PEERS]:
            if not isinstance(p, OrderedDict):
                continue
            peer_data.add(PeerInfo(p[IP].decode(), p[PORT], p[PEER_ID]))
        return peer_data

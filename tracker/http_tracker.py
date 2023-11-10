from typing import OrderedDict

import requests
from requests import Timeout

import bencdec
from misc import utils
from torrent.constants import IP, PORT, PEER_ID, PEERS
from tracker.tracker_base import TrackerBase


class HttpTracker(TrackerBase):
    def request_peers(self, torrent_decoded_data: dict, self_id: bytes, port: int) -> dict:
        peer_data = dict()
        try:
            r = requests.get(self.tracker, params={
                'info_hash': utils.get_info_sha1_hash(torrent_decoded_data),
                'peer_id': self_id,
                'port': port
            }, timeout=1.0)
        except Timeout:
            return peer_data
        response = bencdec.decode(r.content)
        for p in response[PEERS]:
            if not isinstance(p, OrderedDict):
                continue
            peer_id: bytes = p[PEER_ID]
            if peer_id in peer_data:
                continue

            peer_data[peer_id] = {
                IP: p[IP].decode(),
                PORT: p[PORT],
                PEER_ID: peer_id
            }
        return peer_data

from tracker.http_tracker import HttpTracker
from tracker.tracker_base import TrackerBase
from tracker.udp_tracker import UDPTracker


class Tracker(TrackerBase):
    def request_peers(self, torrent_decoded_data: dict, self_id: bytes, port: int) -> dict:
        if self.tracker.startswith('http'):
            return HttpTracker(self.tracker).request_peers(torrent_decoded_data, self_id, port)
        elif self.tracker.startswith('udp'):
            return UDPTracker(self.tracker).request_peers(torrent_decoded_data, self_id, port)
        return {}

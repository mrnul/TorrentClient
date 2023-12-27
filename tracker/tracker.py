from peer import PeerInfo
from torrent.torrent_info import TorrentInfo
from tracker.http_tracker import HttpTracker
from tracker.tracker_base import TrackerBase
from tracker.udp_tracker import UDPTracker


class Tracker(TrackerBase):
    def request_peers(self, torrent_info: TorrentInfo) -> set[PeerInfo]:
        try:
            if self.tracker.startswith('http'):
                return HttpTracker(self.tracker).request_peers(torrent_info)
            elif self.tracker.startswith('udp'):
                return UDPTracker(self.tracker).request_peers(torrent_info)
        except (Exception,):
            pass
        return set()

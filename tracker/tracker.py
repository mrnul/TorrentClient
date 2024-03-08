import asyncio

from peer.peer_info import PeerInfo
from torrent.torrent_info import TorrentInfo
from tracker.http_tracker import HttpTracker
from tracker.tracker_base import TrackerBase
from tracker.udp_tracker import UDPTracker


class Tracker(TrackerBase):
    async def request_peers(self, torrent_info: TorrentInfo) -> tuple[set[PeerInfo], int]:

        try:
            async with asyncio.timeout(10):
                if self.tracker.startswith('http'):
                    return await HttpTracker(self.tracker).request_peers(torrent_info)
                elif self.tracker.startswith('udp'):
                    return await UDPTracker(self.tracker).request_peers(torrent_info)
        except Exception as e:
            print(f"Exception: {e}")
        return set(), 60

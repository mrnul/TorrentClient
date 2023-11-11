from torrent import Torrent
from torrent.torrent_info import TorrentInfo

torrent = Torrent(TorrentInfo('test1.torrent', 6881, b'hello i am testing  '))

torrent.refresh_peers()
torrent.connect_to_peers()

while True:
    if not torrent.download_cycle():
        break

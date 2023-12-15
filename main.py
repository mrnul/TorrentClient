import asyncio

from torrent import Torrent
from torrent.torrent_info import TorrentInfo

torrent = Torrent(TorrentInfo('test1.torrent', 6881, b'hello i am testing  '))
asyncio.run(torrent.download())

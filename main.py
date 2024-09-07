import asyncio

from torrent import Torrent
from torrent.torrent_info import TorrentInfo


async def torrent1():
    torrent = Torrent(TorrentInfo('test1.torrent', 6881, b'hello i am testing  '))
    await torrent.start()


async def torrent2():
    torrent = Torrent(TorrentInfo('test2.torrent', 6881, b'hello i am testing  '))
    await torrent.start()


async def main():
    tasks = [asyncio.create_task(torrent1()),]
    await asyncio.wait(tasks)


asyncio.run(main())

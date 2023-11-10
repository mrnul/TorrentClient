from torrent import Torrent

torrent = Torrent('test1.torrent', 6881, b'hello i am testing  ')

torrent.refresh_peers()
torrent.connect_to_peers()

while True:
    if not torrent.download_cycle():
        break

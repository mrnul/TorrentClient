from torrent import Torrent

torrent = Torrent('test1.torrent', 6881, b'hello i am testing  ')
torrent.refresh_peers()
torrent.connect_to_peers()
while torrent.perform_requests():
    pass

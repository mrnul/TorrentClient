import asyncio
import queue
import threading

from messages import Piece
from misc import utils
from peer import Peer
from peer.peer_info import PeerInfo
from torrent.torrent_info import TorrentInfo
from tracker.tracker import Tracker


class Torrent:

    def disk_writer(self):
        while True:
            piece: Piece | None = self.piece_queue.get()
            if piece is None:
                break
            print(f'Writing {piece} - ', end='')
            f1, b1 = utils.get_file_and_byte_from_byte_in_torrent(piece.index, self.torrent_info.piece_size,
                                                                  0,
                                                                  self.torrent_info.torrent_files)

            f2, b2 = utils.get_file_and_byte_from_byte_in_torrent(piece.index, self.torrent_info.piece_size,
                                                                  len(piece.block) - 1,
                                                                  self.torrent_info.torrent_files)
            if f1 == f2:
                print('Fast', end='')
                f1.file.seek(b1)
                f1.file.write(piece.block)
            else:
                print('Slow...', end='')
                for i, byte_value in enumerate(piece.block):
                    f, b = utils.get_file_and_byte_from_byte_in_torrent(piece.index, self.torrent_info.piece_size,
                                                                        i,
                                                                        self.torrent_info.torrent_files)
                    f.file.seek(b)
                    f.file.write(int(byte_value).to_bytes(1))
            print(' - Done!')

    def __init__(self, torrent_info: TorrentInfo):
        self.torrent_info = torrent_info
        self.peers: set[Peer] = set()
        self.piece_queue = queue.Queue()
        self.disk_thread = threading.Thread(target=self.disk_writer)
        self.disk_thread.start()

    def refresh_peers(self):
        peer_info: set[PeerInfo] = set()
        for tracker in self.torrent_info.trackers:
            peer_info |= Tracker(tracker).request_peers(self.torrent_info)

        new_peers: set[Peer] = set()
        for p_i in peer_info:
            peer = Peer(p_i, self.torrent_info, self.piece_queue)
            if peer not in self.peers:
                self.peers.add(peer)
                new_peers.add(peer)
        return new_peers

    async def download(self):
        [asyncio.create_task(peer.run()) for peer in self.refresh_peers()]
        await self.torrent_info.pending_requests.join()
        self.piece_queue.put(None)

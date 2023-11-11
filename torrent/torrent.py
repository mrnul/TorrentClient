import queue
import threading

from messages import Piece, Message, Terminate, Bitfield, Interested
from misc import utils
from peer import Peer
from peer.peer_info import PeerInfo
from tracker.tracker import Tracker
from .data_request import DataRequest
from .torrent_info import TorrentInfo


class Torrent:
    def __init__(self, torrent_info: TorrentInfo):
        def worker():
            while True:
                piece: Piece | None = self.worker_queue.get()
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

        self.torrent_info = torrent_info
        self.requests: list[DataRequest] = [DataRequest(p.index, 0, p.length) for p in self.torrent_info.pieces_info]
        self.worker_queue = queue.Queue()
        self.thread = threading.Thread(target=worker)
        self.thread.start()

    def refresh_peers(self):
        peer_info: set[PeerInfo] = set()
        for tracker in self.torrent_info.trackers:
            peer_info |= Tracker(tracker).request_peers(self.torrent_info)

        for p_i in peer_info:
            self.torrent_info.peers.add(Peer(p_i, self.torrent_info.info_hash, len(self.torrent_info.pieces_info)))

    def __handle_peer_msg__(self, peer: Peer, msg: Message | None) -> bool:
        if msg is None:
            return True
        if isinstance(msg, Terminate):
            return False
        if isinstance(msg, Bitfield):
            peer.insert_msg(Interested())
        elif isinstance(msg, Piece):
            self.worker_queue.put(msg)
        return True

    def download_cycle(self) -> bool:
        connected_peers = [peer for peer in self.torrent_info.peers if peer.connected]

        for peer in connected_peers:
            peer.send_data()

        for peer in connected_peers:
            if not isinstance(peer, Peer):
                continue
            peer.receive_data()
            if not self.__handle_peer_msg__(peer, peer.retrieve_msg()):
                peer.close()

        pending_requests = [request for request in self.requests if not request.done]
        if len(pending_requests) == 0:
            self.worker_queue.put(None)
            self.thread.join()
            return False

        for request in pending_requests:
            for peer in connected_peers:
                if peer.insert_request(request):
                    break
        return True

    def connect_to_peers(self):
        for peer in self.torrent_info.peers:
            if peer.connected:
                continue
            peer.connect_and_handshake(self.torrent_info.self_id)

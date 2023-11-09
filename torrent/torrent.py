import select

from messages import Interested, Piece, Message, Terminate, Bitfield
from misc import utils
from peer import Peer
from piece_info import PieceInfo
from .constants import *
from .data_request import DataRequest
from .file import File


class Torrent:
    def __init__(self, torrent_file: str, port: int, self_id: bytes):
        self.torrent_file: str = torrent_file
        self.torrent_decoded_data = utils.load_torrent_file(self.torrent_file)
        self.trackers: set[str] = utils.get_trackers(self.torrent_decoded_data)
        self.info_hash: bytes = utils.get_info_sha1_hash(self.torrent_decoded_data)
        self.port: int = port
        self.self_id: bytes = self_id
        self.torrent_files: list[File] = utils.get_torrent_files(self.torrent_decoded_data)
        self.total_size: int = utils.get_torrent_total_size(self.torrent_files)
        self.piece_size = self.torrent_decoded_data[INFO][PIECE_LENGTH]
        self.pieces_info: list[PieceInfo] = utils.parse_torrent_pieces(self.torrent_decoded_data, self.total_size)
        self.peers: dict = dict()

        self.requests: list[DataRequest] = [DataRequest(p.index, 0, p.length) for p in self.pieces_info]

    def refresh_peers(self):
        peer_data = utils.get_peer_data_from_trackers(self.trackers, self.info_hash, self.self_id, self.port)
        for peer in peer_data.values():
            if peer[PEER_ID] in self.peers:
                continue
            self.peers[peer[PEER_ID]] = Peer(peer[IP], peer[PORT], peer[PEER_ID],
                                             self.info_hash, len(self.pieces_info))

    def __handle_peer_msg__(self, peer: Peer, msg: Message | None) -> bool:
        if msg is None:
            return False
        if isinstance(msg, Terminate):
            return False
        if isinstance(msg, Bitfield):
            peer.send_interested(Interested())
        elif isinstance(msg, Piece):
            for i, byte_value in enumerate(msg.block):
                f, b = utils.get_file_and_byte_from_byte_in_torrent(msg.index, self.piece_size, i, self.torrent_files)
                file = self.torrent_files[f].file
                file.seek(b)
                file.write(int(byte_value).to_bytes(1))
                file.flush()
        return True

    def perform_requests(self) -> bool:
        r_ready, _, _ = select.select(self.peers.values(), [], [], 1.0)
        for peer in r_ready:
            if not isinstance(peer, Peer):
                continue
            if not self.__handle_peer_msg__(peer, peer.recv_msg()):
                peer.close()
                self.peers.pop(peer.peer_id_from_tracker)

        pending_requests = [request for request in self.requests if not request.done]
        if len(pending_requests) == 0:
            return False

        for request in pending_requests:
            for peer in r_ready:
                if peer.send_request(request):
                    break
        return True

    def connect_to_peers(self):
        for peer in self.peers.values():
            if peer.connected:
                continue
            peer.connect_and_handshake(self.self_id)

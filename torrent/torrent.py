import hashlib

import select

from messages import Unchoke, Interested, Piece, Message, Terminate, Choke, Bitfield
from misc import utils
from peer import Peer
from piece_info import PieceInfo
from . import FileInfo
from .constants import *


class Torrent:
    def __init__(self, file: str, port: int, self_id: bytes):
        self.file: str = file
        self.torrent_decoded_data = utils.load_torrent_file(self.file)
        self.trackers: set[str] = utils.get_trackers(self.torrent_decoded_data)
        self.info_hash: bytes = utils.get_info_sha1_hash(self.torrent_decoded_data)
        self.port: int = port
        self.self_id: bytes = self_id
        self.pieces: list[PieceInfo] = utils.get_torrent_pieces(self.torrent_decoded_data)
        self.files: list[FileInfo] = utils.get_torrent_files(self.torrent_decoded_data)
        self.peers: dict = dict()

    def refresh_peers(self):
        peer_data = utils.get_peer_data_from_trackers(self.trackers, self.info_hash, self.self_id, self.port)
        for peer in peer_data.values():
            if peer[PEER_ID] in self.peers:
                continue
            self.peers[peer[PEER_ID]] = Peer(peer[IP], peer[PORT],
                                             self.torrent_decoded_data, peer[PEER_ID])

    def __handle_peer_msg__(self, peer: Peer, msg: Message | None) -> bool:
        if msg is None:
            return False
        if isinstance(msg, Terminate):
            return False
        elif isinstance(msg, Bitfield):
            peer.send_msg(Interested())
        elif isinstance(msg, Unchoke):
            peer.am_choked = False
            if peer.am_interested:
                self.pieces[0].request(peer)
        elif isinstance(msg, Choke):
            peer.am_choked = True
        elif isinstance(msg, Piece):
            ok = hashlib.sha1(msg.block).digest() == ()
            piece = self.pieces[msg.index]
        return True

    def handle_connected_peers(self) -> bool:
        connected_peers = [peer for peer in self.peers.values() if peer.is_connected()]
        if len(connected_peers) == 0:
            return False

        r_ready, _, _ = select.select(connected_peers, [], [], 1.0)
        for peer in r_ready:
            if not isinstance(peer, Peer):
                continue
            if not self.__handle_peer_msg__(peer, peer.recv_msg()):
                peer.close()
                self.peers.pop(peer.peer_id_from_tracker)

        for peer in connected_peers:
            self.pieces[0].request(peer)
        return True

    def connect_to_peers(self):
        for peer in self.peers.values():
            if peer.is_connected():
                continue
            peer.start_communication(self.self_id)

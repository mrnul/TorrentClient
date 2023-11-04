import hashlib
from typing import BinaryIO

import select

from logger import Logger
from messages import Interested, Piece, Message, Terminate, Bitfield
from misc import utils
from peer import Peer
from piece_info import PieceInfo
from . import FileInfo
from .constants import *


class Torrent:
    def __init__(self, torrent_file: str, port: int, self_id: bytes):
        self.__logger = Logger(torrent_file, f'{torrent_file}.log', 'DEBUG').get()
        self.torrent_file: str = torrent_file
        self.torrent_decoded_data = utils.load_torrent_file(self.torrent_file)
        self.trackers: set[str] = utils.get_trackers(self.torrent_decoded_data)
        self.info_hash: bytes = utils.get_info_sha1_hash(self.torrent_decoded_data)
        self.port: int = port
        self.self_id: bytes = self_id
        self.files_info: list[FileInfo] = utils.get_torrent_files(self.torrent_decoded_data)
        self.files: list[BinaryIO] = utils.create_files(self.files_info)
        self.total_size: int = utils.get_torrent_total_size(self.files_info)
        self.piece_size = self.torrent_decoded_data[INFO][PIECE_LENGTH]
        self.pieces_info: list[PieceInfo] = utils.parse_torrent_pieces(self.torrent_decoded_data, self.total_size)
        self.peers: dict = dict()
        self.__logger.debug('piece count: %i', len(self.pieces_info))

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
            peer.send_msg(Interested())
        elif isinstance(msg, Piece):
            piece = self.pieces_info[msg.index]
            piece.done = hashlib.sha1(msg.block).digest() == piece.hash_value
            if piece.done:
                self.pieces_info[piece.index].requested_time = 0.0
                for i, byte_value in enumerate(msg.block):
                    f, b = utils.get_file_and_byte_from_byte_in_torrent(msg.index, self.piece_size, i, self.files_info)
                    file = self.files[f]
                    file.seek(b)
                    file.write(int(byte_value).to_bytes(1))
                    file.flush()
        return True

    def request_pieces(self) -> bool:
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

        pending_pieces = [piece for piece in self.pieces_info if not piece.done]
        interesting_peers = [peer for peer in connected_peers if peer.am_interested]
        if len(pending_pieces) == 0:
            return False

        for piece in pending_pieces:
            if not piece.should_request():
                continue
            for peer in interesting_peers:
                if not peer.has_piece(piece.index):
                    continue
                if piece.request_from_peer(peer):
                    break
        return True

    def connect_to_peers(self):
        for peer in self.peers.values():
            if peer.is_connected():
                continue
            peer.connect_and_handshake(self.self_id)

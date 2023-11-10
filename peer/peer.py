import math
import time

from messages import Message, Handshake, Interested, Notinterested, Bitfield, Have, \
    Terminate, Request, Unchoke, Choke, Piece, Cancel
from misc import utils
from torrent.data_request import DataRequest
from torrent_client_socket.torrent_client_socket import TorrentClientSocket


class Peer(TorrentClientSocket):
    """
    Class that handles connection with a peer.
    """
    __NO_REQUEST__ = DataRequest(-1, -1, -1)
    request_timeout = 10.0

    def __init__(self, ip: str, port: int,
                 peer_id: bytes, info_hash: bytes, piece_count: int):
        super().__init__(ip, port)
        self.peer_id_str: str = peer_id.decode(encoding='ascii', errors='ignore')

        self.am_choked: bool = True
        self.am_choking: bool = False
        self.am_interested: bool = False
        self.am_interesting: bool = False  # lol
        self.handshake_received: bool = False
        self.active_request: DataRequest = self.__NO_REQUEST__

        self.ip: str = ip
        self.port: int = port
        self.peer_id_from_tracker: bytes = peer_id
        self.peer_id_from_handshake: bytes = bytes()
        self.info_hash = info_hash
        self.piece_count = piece_count

        self.bitfield: bytearray = bytearray(math.ceil(self.piece_count / 8))

    def insert_msg(self, msg: Message):
        """
        Call this function to send messages to peer
        """
        if isinstance(msg, Interested):
            self.am_interested = True
        elif isinstance(msg, Notinterested):
            self.am_interested = False

        super().insert_msg(msg)

    def insert_request(self, data_req: DataRequest) -> bool:
        if self.am_choked:
            self.active_request.time_sent = 0.0
            self.active_request = self.__NO_REQUEST__
            return False

        if not self.has_piece(data_req.index):
            return False

        if time.time() - self.active_request.time_sent < self.request_timeout:
            return False

        if time.time() - data_req.time_sent < self.request_timeout:
            return False

        if self.active_request != self.__NO_REQUEST__:
            super().insert_msg(Cancel(self.active_request.index, self.active_request.begin, self.active_request.length))
            self.active_request.time_sent = 0.0
            self.active_request = self.__NO_REQUEST__

        self.insert_msg(Request(data_req.index, data_req.begin, data_req.length))
        data_req.time_sent = time.time()
        self.active_request = data_req
        return True

    def has_piece(self, piece_index: int) -> bool:
        return utils.get_bit_value(self.bitfield, piece_index) != 0

    def __consume_handshake__(self) -> Terminate | Handshake | None:
        msg = self.consume_handshake()
        if msg is None:
            return None
        self.handshake_received = isinstance(msg, Handshake)
        if not self.handshake_received:
            return Terminate(f'Could not receive handshake from {self.peer_id_str}')
        return msg

    def __handle_recv_piece__(self, msg: Piece):
        if (self.active_request.index == msg.index and
                self.active_request.begin == msg.begin and
                self.active_request.length == len(msg.block)):
            self.active_request.done = True
            self.active_request = self.__NO_REQUEST__

    def retrieve_msg(self) -> Message | None:
        """
        Get message from peer

        If None is returned then an error occurred
        """
        if not self.handshake_received:
            return self.__consume_handshake__()

        msg = self.consume_rx_data()
        if msg is None:
            return None

        if isinstance(msg, Unchoke):
            self.am_choked = False
        elif isinstance(msg, Choke):
            self.am_choked = True
        elif isinstance(msg, Interested):
            self.am_interesting = True
        elif isinstance(msg, Notinterested):
            self.am_interesting = False  # lol
        elif isinstance(msg, Piece):
            self.__handle_recv_piece__(msg)
        elif isinstance(msg, Bitfield):
            if len(self.bitfield) != len(msg.bitfield):
                self.close()
                return Terminate(f'Received bitfield length {len(msg.bitfield)} but expected {len(self.bitfield)}')
            self.bitfield = msg.bitfield
        elif isinstance(msg, Have):
            utils.set_bit_value(self.bitfield, msg.piece_index, 1)
        return msg

    def connect_and_handshake(self, self_id: bytes) -> bool:
        """
        Connect to peer and send handshake
        """
        if self.connect():
            self.insert_msg(Handshake(info_hash=self.info_hash, peer_id=self_id))
            return True
        return False

    def close(self):
        """
        Closes socket
        """
        self.active_request = self.__NO_REQUEST__
        super().close()

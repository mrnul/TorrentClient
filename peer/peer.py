import math
import time

from logger import Logger
from messages import Message, Handshake, Interested, Notinterested, Bitfield, Have, \
    Terminate, Request, Unchoke, Choke, Piece, Cancel
from misc import utils
from torrent.data_request import DataRequest
from torrent_client_socket import TorrentClientSocket


class Peer(TorrentClientSocket):
    """
    Class that handles connection with a peer.
    """
    __NO_REQUEST__ = DataRequest(-1, -1, -1)
    request_wait = 10.0

    def __init__(self, ip: str, port: int,
                 peer_id: bytes, info_hash: bytes, piece_count: int,
                 log_level: str = 'DEBUG'):
        super().__init__()
        self.peer_id_str: str = peer_id.decode(encoding='ascii', errors='ignore')
        self.__logger = Logger(ip, f'{ip}-{port}-{self.peer_id_str[1:3]}', log_level).get()

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
        self.__logger.info(f'New peer initialized: %s', self.peer_id_str)

    def send_msg(self, msg: Message) -> bool:
        """
        Call this function to send messages to peer
        """
        if isinstance(msg, Interested):
            self.am_interested = True
        elif isinstance(msg, Notinterested):
            self.am_interested = False

        if super().send_msg(msg):
            self.__logger.debug('TXed msg %s : %s', self.peer_id_str, msg)
            return True
        return False

    def send_request(self, data_req: DataRequest) -> bool:
        if self.am_choked:
            self.active_request.sent = False
            self.active_request = self.__NO_REQUEST__
            return False

        if not self.has_piece(data_req.index):
            return False

        if time.time() - self.active_request.time_sent < self.request_wait:
            return False

        if self.active_request != self.__NO_REQUEST__:
            self.send_msg(Cancel(self.active_request.index, self.active_request.begin, self.active_request.length))
            self.active_request.sent = False

        if data_req.sent:
            return False

        data_req.sent = self.send_msg(Request(data_req.index, data_req.begin, data_req.length))
        if data_req.sent:
            data_req.time_sent = time.time()
            self.active_request = data_req
        return data_req.sent

    def has_piece(self, piece_index: int) -> bool:
        return utils.get_bit_value(self.bitfield, piece_index) != 0

    def __recv_handshake__(self) -> Terminate | Handshake:
        msg = self.recv_handshake()
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

    def recv_msg(self) -> Message | None:
        """
        Get message from peer

        If None is returned then an error occurred
        """
        if not self.handshake_received:
            return self.__recv_handshake__()

        msg = super().recv_msg()
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
        self.__logger.debug('RXed msg %s : %s', self.peer_id_str, msg)
        return msg

    def connect_and_handshake(self, self_id: bytes) -> bool:
        """
        Connect to peer and send handshake
        """
        try:
            self.connect((self.ip, self.port))
            self.__logger.debug(f'Connected to: %s', self.peer_id_str)
            self.send_msg(Handshake(info_hash=self.info_hash, peer_id=self_id))
            return True
        except (TimeoutError, OSError) as e:
            self.__logger.error('Could not connect to: %s | %s', self.peer_id_str, e)
            return False

    def close(self):
        """
        Closes socket
        """
        self.active_request.sent = False
        self.active_request = self.__NO_REQUEST__
        super().close()

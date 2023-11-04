import math
import time

from logger import Logger
from messages import Message, Handshake, Interested, Notinterested, Bitfield, Have, \
    Terminate, Request, Unchoke, Choke, Piece
from misc import utils
from torrent_client_socket import TorrentClientSocket


class Peer(TorrentClientSocket):
    """
    Class that handles connection with a peer.

    RX and TX messages on separate threads using TorrentClientSocket
    """
    request_wait = 10.0

    def __init__(self, ip: str, port: int,
                 peer_id: bytes, info_hash: bytes, piece_count: int,
                 log_level: str = 'DEBUG'):
        super().__init__()
        self.__logger = Logger(ip, f'{ip}-{port}-{peer_id[:3].decode()}', log_level).get()

        self.am_choked: bool = True
        self.am_choking: bool = False
        self.am_interested: bool = False
        self.am_interesting: bool = False  # lol
        self.request_time: float = 0.0

        self.ip: str = ip
        self.port: int = port
        self.peer_id_from_tracker: bytes = peer_id
        self.peer_id_from_handshake: bytes = bytes()
        self.info_hash = info_hash
        self.piece_count = piece_count

        self.bitfield: bytearray = bytearray(math.ceil(self.piece_count / 8))
        self.__logger.info('Peer initialized')

    def send_msg(self, msg: Message) -> bool:
        """
        Call this function to send messages to peer
        """
        if isinstance(msg, Interested):
            self.am_interested = True
        elif isinstance(msg, Notinterested):
            self.am_interested = False
        elif isinstance(msg, Request):
            if self.am_choked:
                return False
            if time.time() - self.request_time < self.request_wait:
                return False
            self.request_time = time.time()
        self.__logger.debug('Sending msg: %s', msg)
        return super().send_msg(msg)

    def has_piece(self, piece_index: int) -> bool:
        return utils.get_bit_value(self.bitfield, piece_index) != 0

    def recv_msg(self) -> Message | None:
        """
        Get message from peer

        If None is returned then an error occurred
        """
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
            self.request_time = 0.0
        elif isinstance(msg, Bitfield):
            if len(self.bitfield) != len(msg.bitfield):
                self.close()
                return Terminate(f'Received bitfield length {len(msg.bitfield)} but expected {len(self.bitfield)}')
            self.bitfield = msg.bitfield
        elif isinstance(msg, Have):
            utils.set_bit_value(self.bitfield, msg.piece_index, 1)
        self.__logger.debug('Received msg: %s', msg)
        return msg

    def connect_and_handshake(self, self_id: bytes) -> bool:
        """
        Connect to peer and send handshake
        """
        try:
            self.connect((self.ip, self.port))
            self.send_msg(Handshake(info_hash=self.info_hash, peer_id=self_id))
            self.__logger.debug('Connected to peer')
            return True
        except (TimeoutError, OSError) as e:
            self.__logger.error('Could not connect to peer: %s', e)
            return False

    def stop_communication(self):
        """
        Closes socket
        """
        self.close()

    def is_connected(self):
        return self.connected

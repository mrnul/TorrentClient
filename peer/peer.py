from logger import Logger
from messages import Message, Handshake, Interested, Notinterested
from misc import utils
from torrent_client_socket import TorrentClientSocket


class Peer(TorrentClientSocket):
    """
    Class that handles connection with a peer.

    RX and TX messages on separate threads using TorrentClientSocket
    """
    keep_alive_timeout = 100

    def __init__(self, ip: str, port: int, torrent_data: dict, peer_id: bytes, log_level: str = 'DEBUG'):
        super().__init__()
        self.__logger = Logger(ip, f'{ip}-{port}.log', log_level).get()
        self.__logger.info('Initializing Peer')

        self.am_choked: bool = True
        self.am_choking: bool = False
        self.am_interested: bool = False
        self.am_interesting: bool = False  # lol

        self.__torrent: dict = torrent_data
        self.ip: str = ip
        self.port: int = port
        self.peer_id_from_tracker: bytes = peer_id
        self.peer_id_from_handshake: bytes = bytes()

        self.bitfield: bytes = bytes()
        self.__logger.info('Initialization complete')

    def send_msg(self, msg: Message):
        """
        Call this function to send messages to peer
        """
        if isinstance(msg, Interested):
            self.am_interested = True
        elif isinstance(msg, Notinterested):
            self.am_interested = False
        self.__logger.debug('Sending msg: %s', msg)
        super().send_msg(msg)

    def recv_msg(self) -> Message | None:
        """
        Get message from peer

        If None is returned then an error occurred
        """
        msg = super().recv_msg()
        if isinstance(msg, Interested):
            self.am_interesting = True
        elif isinstance(msg, Notinterested):
            self.am_interested = False  # lol
        self.__logger.debug('Received msg: %s', msg)
        return msg

    def start_communication(self, self_id: bytes) -> bool:
        """
        Connect to peer and send handshake
        """
        try:
            self.connect((self.ip, self.port))
            self.send_msg(Handshake(info_hash=utils.get_info_sha1_hash(self.__torrent), peer_id=self_id))
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

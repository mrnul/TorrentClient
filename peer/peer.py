import queue
import threading

from logger import Logger
from messages import Message, HandShake, KeepAlive
from messages.terminate import Terminate
from misc import utils
from torrent_client_socket import TorrentClientSocket


class Peer:
    """
    Class that handles connection with a peer.

    RX and TX messages on separate threads using TorrentClientSocket
    """
    keep_alive_timeout = 100

    def __init__(self, ip: str, port: int, torrent_data: dict):
        self.logger = Logger(ip, f'{ip} - {port}.log', 'DEBUG').get()
        self.logger.info('Initializing Peer')

        self.s: TorrentClientSocket = TorrentClientSocket()
        self.am_choked: bool = False
        self.am_choking: bool = False
        self.am_interested: bool = False
        self.am_interesting: bool = False  # lol

        self.torrent: dict = torrent_data
        self.ip: str = ip
        self.port: int = port

        self.id: str = str()
        self.bitfield: bytes = bytes()

        self.tx_queue: queue = queue.Queue()
        self.rx_queue: queue = queue.Queue()

        self.tx_thread = threading.Thread(target=self._tx_worker)
        self.rx_thread = threading.Thread(target=self._rx_worker)
        self.logger.info('Initialization complete')

    def _tx_worker(self):
        """
        Gets elements from tx_queue and TXs them to the peer
        """
        self.logger.info("Thread started")
        while True:
            try:
                item = self.tx_queue.get(block=True, timeout=self.keep_alive_timeout)
                if isinstance(item, Terminate):
                    self.logger.info(item.reason)
                    break
            except queue.Empty:
                self.enqueue_msg(KeepAlive())
                continue
            self.logger.debug(item)
            self.s.send_peer_message(item)
        self.rx_queue.put(Terminate('tx stopped'))
        self.logger.info('Thread terminated')

    def _rx_worker(self):
        """
        Gets elements from peer and adds them in rx_queue
        """
        self.logger.info('Thread started')
        handshake = self.s.recv_handshake()
        if isinstance(handshake, Terminate):
            self.logger.error(handshake.reason)
            self.tx_queue.put(Terminate(handshake.reason))
            return

        self.logger.debug(handshake)
        while True:
            msg = self.s.recv_peer_msg()
            self.rx_queue.put(msg)
            if isinstance(msg, Terminate):
                self.logger.info(msg.reason)
                break
            self.logger.debug(msg)

        self.tx_queue.put(Terminate('rx stopped'))
        self.logger.debug('Thread terminated')

    def enqueue_msg(self, msg: Message):
        """
        Call this function to send messages to peer
        """
        self.tx_queue.put(msg)

    def dequeue_msg(self, blocking: bool = True) -> Message | None:
        """
        Get RXed messages from peer in either blocking or non-blocking mode.

        If None is returned then no messages are available
        """
        msg: Message | None = None
        try:
            msg = self.rx_queue.get(block=blocking)
        except queue.Empty:
            pass
        return msg

    def start_communication(self, client_id: bytes) -> bool:
        """
        Connect to peer and begin RX / TX threads
        """
        try:
            self.s.connect((self.ip, self.port))
        except TimeoutError:
            self.logger.error("Could not connect to peer")
            return False
        self.tx_thread.start()
        self.rx_thread.start()
        self.enqueue_msg(HandShake(info_hash=utils.get_info_sha1_hash(self.torrent['info']),
                                   peer_id=client_id))
        return True

    def stop_communication(self):
        """
        Stop RX / TX threads and close socket
        """
        self.tx_queue.put(Terminate(f'stop_communication called'))
        self.tx_thread.join()
        self.s.close()
        self.rx_thread.join()
        self.rx_queue.put(Terminate(f'stop_communication called'))

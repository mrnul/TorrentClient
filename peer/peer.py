import queue
import threading

from torrent_client_socket import TorrentClientSocket
from logger import Logger
from messages import Message, HandShake, BitField, Request, Unchoke, Piece, KeepAlive
from messages.terminate import Terminate
from misc import utils


class Peer:
    keep_alive_timeout = 100

    def __init__(self, ip: str, port: int, torrent: dict):
        self.logger = Logger(ip, f'{ip} - {port}.log', 'DEBUG').get()
        self.logger.info('Initializing Peer')

        self.s: TorrentClientSocket = TorrentClientSocket()
        self.am_choking: bool = False
        self.am_interested: bool = False
        self.am_choked: bool = False
        self.am_interesting: bool = False  # lol

        self.torrent: dict = torrent
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
            self.s.send(item.to_bytes())
        self.logger.info('Thread terminated')

    def _rx_worker(self):
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

            if isinstance(msg, BitField):
                self.bitfield = msg.bitfield

            if isinstance(msg, Unchoke):
                self.enqueue_msg(Request(index=0, begin=0, length=1024))

            self.logger.debug(msg)

        self.tx_queue.put(Terminate('tx stopped'))
        self.logger.debug('Thread terminated')

    def enqueue_msg(self, msg: Message):
        self.tx_queue.put(msg)

    def dequeue_msg(self, blocking: bool = True) -> Message | None:
        msg: Message | None = None
        try:
            msg = self.rx_queue.get(block=blocking)
        except queue.Empty:
            pass
        return msg

    def start_communication(self, client_id: bytes) -> bool:
        try:
            self.s.connect((self.ip, self.port))
        except TimeoutError:
            self.logger.error("Could not connect to peer")
            return False
        self.tx_thread.start()
        self.rx_thread.start()

        self.enqueue_msg(HandShake(info_hash=utils.get_info_sha1_hash(self.torrent['info']),
                                   peer_id=client_id))

    def stop_communication(self):
        self.tx_queue.put(Terminate(f'stop_communication called'))
        self.rx_queue.put(Terminate(f'stop_communication called'))
        self.s.close()

        self.tx_thread.join()
        self.rx_thread.join()

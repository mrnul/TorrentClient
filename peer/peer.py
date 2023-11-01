import queue
import socket
import threading

from messages import Message, HandShake, BitField, Request, Unchoke, Piece, KeepAlive
from messages.terminate import Terminate
from misc import utils


class Peer:
    def __init__(self, ip: str, port: int, torrent: dict):
        self.s: socket.socket | None = None
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

    def _tx_worker(self):
        idle_count = 0
        while True:
            try:
                item = self.tx_queue.get(block=True, timeout=1.0)
            except queue.Empty:
                idle_count += 1
                print(f'TX - No data... {idle_count}')
                if idle_count >= 30:
                    self.send_msg(Request(index=0, begin=0, length=1024))
                continue
            if isinstance(item, Terminate):
                break
            print(f"TX - Data: {item} | {len(item.to_bytes())}")
            idle_count = 0
            self.s.send(item.to_bytes())
        print('TX - Goodbye')

    def _rx_worker(self):
        def recv_handshake():
            pstrlen = int.from_bytes(utils.recv_n_bytes(self.s, 1))
            data = utils.recv_n_bytes(self.s, 48 + pstrlen)
            return data

        print(f"RX - Handshake: {recv_handshake()}")
        self.send_msg(Unchoke())

        while True:
            msg_len = utils.recv_n_bytes(self.s, 4)
            if len(msg_len) == 0:
                print(f'Client disconnected')
                break

            msg_len_int = int.from_bytes(msg_len)
            if msg_len_int < 0:
                print(f"Error in msg_len_int: {msg_len_int}")
                break

            uid_payload = utils.recv_n_bytes(self.s, msg_len_int)
            msg = utils.get_message_from_bytes(msg_len + uid_payload)
            if isinstance(msg, KeepAlive):
                self.send_msg(KeepAlive())

            if isinstance(msg, BitField):
                self.bitfield = msg.bitfield

            if isinstance(msg, Unchoke):
                self.send_msg(Request(index=0, begin=0, length=1024))

            if isinstance(msg, Piece):
                print(f"RX Piece - {msg.to_bytes()}")

            print(f"RX - {msg}")

        print('RX - Goodbye')
        self.tx_queue.put(Terminate())

    def send_msg(self, msg: Message):
        self.tx_queue.put(msg)

    def recv_msg(self, blocking: bool = True) -> Message | None:
        msg: Message | None = None
        try:
            msg = self.rx_queue.get(block=blocking)
        except queue.Empty:
            pass
        return msg

    def start_communication(self, client_id: bytes) -> bool:
        try:
            self.s = socket.create_connection((self.ip, self.port), timeout=1.0)
        except TimeoutError:
            print("Could not connect to peer")
            return False
        self.tx_thread.start()
        self.rx_thread.start()

        self.send_msg(HandShake(info_hash=utils.get_info_sha1_hash(self.torrent['info']),
                                peer_id=client_id))

    def stop_communication(self):
        self.tx_queue.put(Terminate())
        self.rx_queue.put(Terminate())
        self.s.close()

        self.tx_thread.join()
        self.rx_thread.join()

import logging
import socket

import select

from messages import Message, Handshake, Terminate
from misc import utils


class TorrentClientSocket:
    """
    Wrapper class for a TCP client socket that receives / sends peer protocol messages.
    """

    __RECV_SIZE__ = 2 ** 14
    logging.basicConfig(filename='TorrentClientSockets.log', filemode='w', level=logging.DEBUG)

    def __init__(self, ip: str, port: int):
        self.ip: str = ip
        self.port: int = port
        self.s: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        self.s.setblocking(False)
        self.__connected = False
        self.__rx_array: bytearray = bytearray()
        self.__tx_array: bytearray = bytearray()
        logging.info('Peer %s:%s initialized', self.ip, self.port)

    @property
    def connected(self) -> bool:
        try:
            _, w_list, _ = select.select([], [self.s], [], 0.0)
            self.__connected = len(w_list) != 0
        except ValueError:
            self.__connected = False
        return self.__connected

    def should_read(self) -> bool:
        try:
            r_list, _, _ = select.select([self.s], [], [], 0.0)
            return len(r_list) != 0
        except ValueError:
            pass
        return False

    def connect(self) -> bool:
        try:
            self.s.connect_ex((self.ip, self.port))
        except socket.error:
            logging.info('Peer %s:%s connection error', self.ip, self.port)
            return False
        logging.info('Peer %s:%s connected', self.ip, self.port)
        return True

    def close(self):
        try:
            self.s.close()
        except socket.error:
            pass
        logging.info('Peer %s:%s closed', self.ip, self.port)
        self.__connected = False

    def receive_data(self) -> int | None:
        if not self.should_read():
            return 0

        try:
            data = bytearray(self.s.recv(self.__RECV_SIZE__))
            if not data:
                self.close()
                return None
        except socket.error:
            data = bytearray()
        self.__rx_array += data
        return len(data)

    def insert_tx_data(self, data: bytes) -> int:
        self.__tx_array += bytearray(data)
        return len(self.__tx_array)

    def insert_msg(self, msg: Message) -> int:
        logging.info('Peer %s:%s inserting msg %s', self.ip, self.port, msg)
        return self.insert_tx_data(msg.to_bytes())

    def consume_rx_data(self) -> Message | None:
        if len(self.__rx_array) == 0:
            return None
        msg = utils.bytes_to_msg(self.__rx_array)
        if msg is not None:
            self.__rx_array = self.__rx_array[msg.len + 4:]
            logging.info('Peer %s:%s consume %s', self.ip, self.port, msg)
        return msg

    def consume_handshake(self) -> Handshake | Terminate | None:
        msg = utils.bytes_to_handshake(self.__rx_array)
        if msg is not None:
            self.__rx_array = self.__rx_array[msg.len:]
            logging.info('Peer %s:%s consume %s', self.ip, self.port, msg)
        return msg

    def send_data(self) -> int:
        if len(self.__tx_array) == 0:
            return 0
        try:
            bytes_sent = self.s.send(self.__tx_array)
            self.__tx_array = self.__tx_array[bytes_sent:]
            return bytes_sent
        except socket.error:
            return 0

    def tx_size(self) -> int:
        return len(self.__tx_array)

    def rx_size(self) -> int:
        return len(self.__rx_array)

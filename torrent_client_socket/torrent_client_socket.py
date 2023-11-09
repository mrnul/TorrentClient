import socket

from messages import Message, Terminate, Handshake
from misc import utils


class TorrentClientSocket(socket.socket):
    """
    Wrapper class for a TCP client socket that receives / sends peer protocol messages.

    Socket is created with timeout = 1.0
    """

    def __init__(self):
        super().__init__(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        self.settimeout(1.0)
        self.__connected = False

    @property
    def connected(self):
        return self.__connected

    def connect(self, __address) -> bool:
        try:
            super().connect(__address)
            self.__connected = True
        except socket.error:
            self.__connected = False
        return self.connected

    def close(self):
        try:
            super().close()
        except socket.error:
            pass
        self.__connected = False

    def __recv_n__(self, n: int) -> bytes | None:
        """
        Receive exactly n bytes.

        If None is returned an error occurred or there is a disconnection
        """

        data = b''
        while len(data) != n:
            try:
                tmp_data = self.recv(n - len(data))
                if len(tmp_data) <= 0:
                    self.close()
                    return None
            except TimeoutError:
                continue
            except socket.error:
                self.close()
                return None
            data += tmp_data
        return data

    def recv_msg(self) -> Message:
        """
        Gets peer messages and returns Terminate if there is a communication error
        """
        msg_len = self.__recv_n__(4)
        if msg_len is None:
            return Terminate(f'Could not receive msg len')

        msg_len_int = int.from_bytes(msg_len)
        if msg_len_int < 0:
            return Terminate(f'Received message length: {msg_len_int}')

        uid_payload = self.__recv_n__(msg_len_int)
        if uid_payload is None:
            return Terminate(f'Could not receive msg id')
        return utils.get_message_from_bytes(msg_len + uid_payload)

    def recv_handshake(self) -> Handshake | Terminate:
        """
        Receives handshake message.

        Returns Terminate message if there was a problem with handshake
        """
        ln = self.__recv_n__(1)
        if ln is None:
            return Terminate(f'Could not receive data')
        pstrlen = int.from_bytes(ln)
        if pstrlen != 19:
            return Terminate(f'pstrlen = {pstrlen}')
        pstr = self.__recv_n__(pstrlen)
        if pstr is None or pstr != b'BitTorrent protocol':
            return Terminate(f'pstr = {pstr}')
        reserved = self.__recv_n__(8)
        if reserved is None:
            return Terminate(f'Could not receive reserved bytes')
        info_hash = self.__recv_n__(20)
        if info_hash is None:
            return Terminate(f'Could not receive info_hash')
        peer_id = self.__recv_n__(20)
        if peer_id is None:
            return Terminate(f'Could not receive peer_id')

        return Handshake(info_hash=info_hash,
                         peer_id=peer_id,
                         reserved=reserved,
                         pstr=pstr)

    def send_msg(self, msg: Message) -> bool:
        try:
            msg_bytes = msg.to_bytes()
            return self.send(msg_bytes) == len(msg_bytes)
        except socket.error:
            self.close()
        return False

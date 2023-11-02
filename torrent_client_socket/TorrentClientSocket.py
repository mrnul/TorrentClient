import socket

from messages import Message, Terminate, HandShake
from misc import utils


class TorrentClientSocket(socket.socket):
    """
    Wrapper class for a TCP client socket that receives / sends peer protocol messages.

    Socket is created with timeout = 1.0
    """

    def __init__(self):
        super().__init__(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        super().settimeout(1.0)

    def recv_n(self, n: int, seconds: int = -1) -> bytes | None:
        """
        Receive exactly n bytes.

        If None is returned an error occurred or there is a disconnection
        """
        if n == 0:
            return b''

        data = b''
        count = 0
        while len(data) != n:
            try:
                tmp_data = self.recv(n - len(data))
                if len(tmp_data) <= 0:
                    return None
                count = 0
            except TimeoutError:
                count += 1
                if 0 < seconds <= count:
                    return None
                continue
            except OSError:
                return None
            data += tmp_data
        return data

    def recv_peer_msg(self) -> Message:
        """
        Gets peer messages and returns Terminate if communication with peer should be closed
        """
        msg_len = self.recv_n(4)
        if len(msg_len) == 0:
            return Terminate(f'Connection closed')

        msg_len_int = int.from_bytes(msg_len)
        if msg_len_int < 0:
            return Terminate(f'Received message length: {msg_len_int}')

        uid_payload = self.recv_n(msg_len_int)
        return utils.get_message_from_bytes(msg_len + uid_payload)

    def recv_handshake(self) -> HandShake | Terminate:
        """
        Receives handshake message.

        Returns Terminate message if there was a problem with handshake
        """
        ln = self.recv_n(1)
        if ln is None:
            return Terminate(f'Could not receive data')
        pstrlen = int.from_bytes(ln)
        if pstrlen != 19:
            return Terminate(f'pstrlen = {pstrlen}')
        pstr = self.recv_n(pstrlen)
        if pstr is None or pstr != b'BitTorrent protocol':
            return Terminate(f'pstr = {pstr}')
        reserved = self.recv_n(8)
        if reserved is None:
            return Terminate(f'Could not receive reserved bytes')
        info_hash = self.recv_n(20)
        if info_hash is None:
            return Terminate(f'Could not receive info_hash')
        peer_id = self.recv_n(20)
        if peer_id is None:
            return Terminate(f'Could not receive peer_id')
        return HandShake(info_hash=info_hash,
                         peer_id=peer_id,
                         reserved=reserved,
                         pstr=pstr)

    def send_peer_message(self, msg: Message) -> bool:
        msg_bytes = msg.to_bytes()
        return self.send(msg_bytes) == len(msg_bytes)

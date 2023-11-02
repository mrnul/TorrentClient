import socket

from messages import Message, Terminate, HandShake
from misc import utils


class TorrentClientSocket(socket.socket):

    def __init__(self):
        super().__init__(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        super().settimeout(1.0)

    def recv_n(self, n: int, seconds: int = 10) -> bytes:
        if n == 0:
            return b''

        data = b''
        count = 0
        while len(data) != n:
            try:
                tmp_data = self.recv(n - len(data))
                if len(tmp_data) <= 0:
                    return b''
                count = 0
            except TimeoutError:
                count += 1
                if 0 < seconds <= count:
                    return b''
                continue
            except OSError:
                return b''
            data += tmp_data
        return data

    def recv_peer_msg(self) -> Message:
        msg_len = self.recv_n(4)
        if len(msg_len) == 0:
            return Terminate(f'Connection closed')

        msg_len_int = int.from_bytes(msg_len)
        if msg_len_int < 0:
            return Terminate(f'Received message length: {msg_len_int}')

        uid_payload = self.recv_n(msg_len_int)
        return utils.get_message_from_bytes(msg_len + uid_payload)

    def recv_handshake(self) -> HandShake | Terminate:
        pstrlen = int.from_bytes(self.recv_n(1))
        if pstrlen != 19:
            return Terminate(f'pstrlen = {pstrlen}')
        pstr = self.recv_n(pstrlen)
        if pstr != b'BitTorrent protocol':
            return Terminate(f'pstr = {pstr}')
        reserved = self.recv_n(8)
        if len(reserved) == 0:
            return Terminate(f'Could not receive reserved bytes')
        info_hash = self.recv_n(20)
        if len(info_hash) == 0:
            return Terminate(f'Could not receive info_hash')
        peer_id = self.recv_n(20)
        if len(peer_id) == 0:
            return Terminate(f'Could not receive peer_id')
        return HandShake(info_hash=info_hash,
                         peer_id=peer_id,
                         reserved=reserved,
                         pstr=pstr)

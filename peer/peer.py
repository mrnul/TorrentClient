import asyncio
import math
import queue
from asyncio import StreamReader, StreamWriter, IncompleteReadError

from messages import Message, Handshake, Interested, Notinterested, Bitfield, Have, \
    Terminate, Request, Unchoke, Choke, Piece, Keepalive, Cancel
from misc import utils
from peer.peer_info import PeerInfo
from torrent.torrent_info import TorrentInfo


class Peer:
    """
    Class that handles connection with a peer.
    """
    __TIMEOUT__ = 5.0

    def __init__(self, peer_info: PeerInfo, torrent_info: TorrentInfo, piece_queue: queue.Queue):
        self.peer_id_str: str = peer_info.peer_id_tracker.decode(encoding='ascii', errors='ignore')
        self.writer: StreamWriter | None = None
        self.reader: StreamReader | None = None
        self.am_choked: bool = True
        self.am_choking: bool = False
        self.am_interested: bool = False
        self.am_interesting: bool = False  # lol
        self._connected: bool = False

        self.peer_info = peer_info
        self.torrent_info: TorrentInfo = torrent_info
        self.piece_count = len(self.torrent_info.pieces_info)
        self.piece_queue = piece_queue
        self.peer_id_handshake: bytes = bytes()

        self.bitfield: bytearray = bytearray(math.ceil(self.piece_count / 8))

    def __eq__(self, other) -> bool:
        if not isinstance(other, Peer):
            return False
        return self.peer_info == other.peer_info

    def __hash__(self) -> int:
        return hash(self.peer_info)

    async def send_msg(self, msg: Message):
        """
        Call this function to send messages to peer
        """
        if isinstance(msg, Interested):
            self.am_interested = True
        elif isinstance(msg, Notinterested):
            self.am_interested = False

        try:
            self.writer.write(msg.to_bytes())
            await self.writer.drain()
        except ConnectionResetError:
            pass

    async def _recv_piece(self) -> Piece | Terminate | Choke:
        while True:
            msg = await self._recv_msg()
            if isinstance(msg, Piece) or isinstance(msg, Terminate) or isinstance(msg, Choke):
                break
        return msg

    async def request_and_get_data(self, request: Request) -> Piece | Terminate | Choke | None:
        try:
            await self.send_msg(request)
            msg = await asyncio.wait_for(
                self._recv_piece(),
                timeout=self.__TIMEOUT__
            )
            return msg
        except TimeoutError:
            return None

    def can_perform_request(self):
        return self.am_interested and not self.am_choked and not self.am_choking

    async def run(self):
        if not await self.connect_and_perform_handshake(self.torrent_info.self_id):
            return
        while True:
            msg: Message = await self._recv_msg()
            if isinstance(msg, Terminate):
                break

            while self.can_perform_request():
                data_request: Request | None = await self.torrent_info.pending_requests.get()
                if not data_request:
                    return
                if not self.has_piece(data_request.index):
                    self.torrent_info.pending_requests.put_nowait(data_request)
                    self.torrent_info.pending_requests.task_done()
                    continue
                response: Piece | Terminate | Choke | None = await self.request_and_get_data(data_request)
                if isinstance(response, Piece):
                    self.torrent_info.completed_requests.append(data_request)
                    self.piece_queue.put(response)
                    self.torrent_info.pending_requests.task_done()
                else:
                    self.torrent_info.pending_requests.put_nowait(data_request)
                    self.torrent_info.pending_requests.task_done()
                    if isinstance(response, Terminate):
                        return
                    await self.send_msg(Cancel(data_request.index, data_request.begin, data_request.length))

    def has_piece(self, piece_index: int) -> bool:
        return utils.get_bit_value(self.bitfield, piece_index) != 0

    async def _recv_handshake(self):
        try:
            pstrlen = (await self.reader.readexactly(1))[0]
            pstr = await self.reader.readexactly(pstrlen)
            reserved = await self.reader.readexactly(8)
            info_hash = await self.reader.readexactly(20)
            peer_id = await self.reader.readexactly(20)
            return Handshake(info_hash, peer_id)
        except (IncompleteReadError, ConnectionResetError):
            return Terminate(f'Could not read from socket')

    async def _recv_msg(self) -> Message:
        """
        Get message from peer

        If None is returned then an error occurred
        """
        try:
            msg_len = int.from_bytes(await self.reader.readexactly(4))
            if msg_len == 0:
                return Keepalive()
            msg_id = int.from_bytes(await self.reader.readexactly(1))
            msg_payload = await self.reader.readexactly(msg_len - 1)
            msg = utils.bytes_to_msg(msg_id, msg_payload)
        except IncompleteReadError:
            msg = Terminate(f'Could not read from socket')
        return await self._handle_received_msg(msg)

    async def _handle_received_msg(self, msg: Message) -> Message:
        if isinstance(msg, Terminate):
            self.writer.close()
            await self.peer_close()
        elif isinstance(msg, Unchoke):
            self.am_choked = False
        elif isinstance(msg, Choke):
            self.am_choked = True
        elif isinstance(msg, Interested):
            self.am_interesting = True
        elif isinstance(msg, Notinterested):
            self.am_interesting = False  # lol
        elif isinstance(msg, Bitfield):
            if len(self.bitfield) != len(msg.bitfield):
                self.writer.close()
                await self.peer_close()
                return Terminate(f'Received bitfield length {len(msg.bitfield)} but expected {len(self.bitfield)}')
            self.bitfield = msg.bitfield
            await self.send_msg(Interested())
        elif isinstance(msg, Have):
            utils.set_bit_value(self.bitfield, msg.piece_index, 1)
        return msg

    @property
    def connected(self):
        return self._connected

    @connected.setter
    def connected(self, value):
        self._connected = value

    async def connect_and_perform_handshake(self, self_id: bytes) -> bool:
        """
        Connect to peer and send handshake
        """
        try:
            async with asyncio.timeout(self.__TIMEOUT__):
                self.reader, self.writer = await asyncio.open_connection(self.peer_info.ip, self.peer_info.port)
                await self.send_msg(Handshake(self.torrent_info.info_hash, self_id))
                msg = await self._recv_handshake()
                if not isinstance(msg, Handshake):
                    await self.peer_close()
                    return False
            self.connected = True
            print(f"{self.peer_info.ip} connected!")
        except (TimeoutError, ConnectionRefusedError):
            self.connected = False
            print(f"{self.peer_info.ip} error!")
        return self.connected

    async def peer_close(self):
        """
        Closes socket
        """
        self.connected = False
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except (Exception,):
            pass

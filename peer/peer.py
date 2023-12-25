import asyncio
import math
import time
from asyncio import StreamReader, StreamWriter, QueueEmpty

from messages import Message, Handshake, Interested, Notinterested, Bitfield, Have, \
    Terminate, Request, Unchoke, Choke, Piece, Keepalive, Cancel
from misc import utils
from peer.peer_info import PeerInfo
from piece_handler.active_piece import ActivePiece
from torrent.torrent_info import TorrentInfo


class Peer:
    """
    Class that handles connection with a peer.
    """
    __Q_TIMEOUT__ = 1.0
    __PIECE_TIMEOUT__ = 5.0
    __KEEP_ALIVE_TIMEOUT__ = 60.0

    def __init__(self, peer_info: PeerInfo, torrent_info: TorrentInfo):
        self.peer_id_str: str = peer_info.peer_id_tracker.decode(encoding='ascii', errors='ignore')
        self.writer: StreamWriter | None = None
        self.reader: StreamReader | None = None
        self.am_choked: bool = True
        self.am_choking: bool = False
        self.am_interested: bool = False
        self.am_interesting: bool = False  # lol
        self.connected: bool = False

        self.peer_info = peer_info
        self.torrent_info: TorrentInfo = torrent_info
        self.peer_id_handshake: bytes = bytes()
        self.last_tx_time = 0.0

        self.bitfield: bytearray = bytearray(math.ceil(len(self.torrent_info.pieces_info) / 8))

    def __eq__(self, other) -> bool:
        if not isinstance(other, Peer):
            return False
        return self.peer_info == other.peer_info

    def __hash__(self) -> int:
        return hash(self.peer_info)

    async def _send_msg(self, msg: Message):
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
            self.last_tx_time = time.time()
        except ConnectionResetError:
            pass

    async def _recv_piece_or_terminate_or_choke(self) -> Piece | Terminate | Choke:
        """
        Awaits to receive one of the following: Piece, Terminate, Choke
        """
        msg = None
        while self.connected:
            msg = await self._recv_and_handle_msg()
            if isinstance(msg, Piece) or isinstance(msg, Terminate) or isinstance(msg, Choke):
                break
        return msg

    async def _request_and_get_data(self, request: Request) -> Piece | Terminate | Choke:
        """
        Sends a request and awaits for one of the following: Piece, Terminate, Choke
        """
        await self._send_msg(request)
        return await self._recv_piece_or_terminate_or_choke()

    def can_perform_request(self):
        """
        Checks if it is ok to send a request to the peer
        """
        return self.am_interested and not self.am_choked and not self.am_choking and self.connected

    async def run(self, active_pieces: tuple[ActivePiece, ...]):
        """
        Performs connection and handshake with the peer

        Performs piece_handler requests and handles responses
        """
        async def grab_request_and_active_piece_object():
            """
            Helper function to grab requests from active pieces
            """
            while self.connected:
                for a_p in active_pieces:
                    if a_p.piece_info is None:
                        continue
                    if not self.has_piece(a_p.piece_info.index):
                        continue
                    try:
                        return a_p.requests.get_nowait(), a_p
                    except QueueEmpty:
                        pass
                await asyncio.sleep(0.5)
            return None, None

        if not await self._connect_and_perform_handshake():
            return
        while self.connected:
            msg: Message = await self._recv_and_handle_msg()
            if isinstance(msg, Terminate):
                break
            while self.can_perform_request():
                request = None
                try:
                    async with asyncio.timeout(self.__Q_TIMEOUT__):
                        request, active_piece = await grab_request_and_active_piece_object()
                        if not request:
                            return
                    async with asyncio.timeout(self.__PIECE_TIMEOUT__):
                        response: Piece | Terminate | Choke = await self._request_and_get_data(request)
                        if isinstance(response, Piece):
                            active_piece.update_data_from_piece_message(response)
                            active_piece.requests.task_done()
                        elif isinstance(response, Choke):
                            active_piece.requests.put_nowait(request)
                            active_piece.requests.task_done()
                            await self._send_msg(
                                Cancel(
                                    request.index,
                                    request.begin,
                                    request.length
                                )
                            )
                        else:
                            active_piece.requests.put_nowait(request)
                            active_piece.requests.task_done()
                            return
                except TimeoutError:
                    if request is not None:
                        active_piece.requests.put_nowait(request)
                        active_piece.requests.task_done()
                    if time.time() - self.last_tx_time >= self.__KEEP_ALIVE_TIMEOUT__:
                        await self._send_msg(Keepalive())

    def has_piece(self, piece_index: int) -> bool:
        """
        Checks whether peer has piece_index
        """
        return utils.get_bit_value(self.bitfield, piece_index) != 0

    async def _recv_handshake(self):
        """
        Receives handshake message

        If Terminate is returned then an error occurred
        """
        try:
            p_strlen = (await self.reader.readexactly(1))[0]
            pstr = await self.reader.readexactly(p_strlen)
            reserved = await self.reader.readexactly(8)
            info_hash = await self.reader.readexactly(20)
            peer_id = await self.reader.readexactly(20)
            return Handshake(info_hash, peer_id)
        except Exception as e:
            return Terminate(f'Could not read from socket: {e}')

    async def _recv_msg(self) -> Message:
        """
        Get message from peer

        If Terminate is returned then an error occurred
        """
        try:
            msg_len = int.from_bytes(await self.reader.readexactly(4))
            if msg_len == 0:
                return Keepalive()
            msg_id = int.from_bytes(await self.reader.readexactly(1))
            msg_payload = await self.reader.readexactly(msg_len - 1)
            msg = utils.bytes_to_msg(msg_id, msg_payload)
        except Exception as e:
            msg = Terminate(f'Could not read from socket: {e}')
        return msg

    async def _handle_received_msg(self, msg: Message) -> Message:
        """
        Handles received message by sending appropriate responses and updating flags
        """
        if isinstance(msg, Terminate):
            await self.close()
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
                await self.close()
                return Terminate(f'Received bitfield length {len(msg.bitfield)} but expected {len(self.bitfield)}')
            self.bitfield = msg.bitfield
            await self._send_msg(Interested())
        elif isinstance(msg, Have):
            utils.set_bit_value(self.bitfield, msg.piece_index, 1)
        return msg

    async def _recv_and_handle_msg(self) -> Message:
        """
        Receives a message, then handles it, then returns it
        """
        return await self._handle_received_msg(await self._recv_msg())

    async def _connect_and_perform_handshake(self) -> bool:
        """
        Connect to peer and send handshake
        """
        try:
            async with asyncio.timeout(self.__PIECE_TIMEOUT__):
                self.reader, self.writer = await asyncio.open_connection(self.peer_info.ip, self.peer_info.port)
                await self._send_msg(Handshake(self.torrent_info.info_hash, self.torrent_info.self_id))
                msg = await self._recv_handshake()
                if not isinstance(msg, Handshake):
                    await self.close()
                    return False
            self.connected = True
        except (TimeoutError, ConnectionRefusedError, OSError):
            self.connected = False
        return self.connected

    async def close(self):
        """
        Closes socket
        """
        self.connected = False
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except (Exception,):
            pass

import asyncio
import dataclasses
import math
import time
from asyncio import StreamReader, StreamWriter

from messages import Message, Handshake, Interested, Notinterested, Bitfield, Have, \
    Terminate, Request, Unchoke, Choke, Piece, Keepalive, Cancel
from misc import utils
from peer.peer_info import PeerInfo
from piece_handling.active_piece import ActivePiece
from torrent.torrent_info import TorrentInfo


@dataclasses.dataclass
class PeerFlags:
    """
    Flags that hold the Peer status initialized to default values
    """
    am_choked: bool = True
    am_choking: bool = False
    am_interested: bool = False
    am_interesting: bool = False  # lol
    connected: bool = False


class Peer:
    """
    Class that handles connection with a peer.
    """
    __Q_TIMEOUT__ = 5.0
    __REQUEST_TIMEOUT__ = 5.0
    __GENERAL_COMMUNICATION_TIMEOUT__ = 30.0
    __HANDSHAKE_TIMEOUT__ = 10.0
    __KEEP_ALIVE_TIMEOUT__ = 60.0
    __REQUEST_TIMEOUT_PUNISH__ = 5.0

    def __init__(self, peer_info: PeerInfo, torrent_info: TorrentInfo, active_pieces: tuple[ActivePiece, ...]):
        self.peer_id_str: str = peer_info.peer_id_tracker.decode(encoding='ascii', errors='ignore')
        self.writer: StreamWriter | None = None
        self.reader: StreamReader | None = None
        self.flags = PeerFlags()

        self.peer_info = peer_info
        self.torrent_info: TorrentInfo = torrent_info
        self.peer_id_handshake: bytes = bytes()
        self.active_pieces: tuple[ActivePiece, ...] = active_pieces
        self.last_tx_time = 0.0

        self.bitfield: bytearray = bytearray(math.ceil(len(self.torrent_info.pieces_info) / 8))

    def __eq__(self, other) -> bool:
        if not isinstance(other, Peer):
            return False
        return self.peer_info == other.peer_info

    def __hash__(self) -> int:
        return hash(self.peer_info)

    async def _send_msg(self, msg: Message) -> bool:
        """
        Call this function to send messages to peer
        """
        if isinstance(msg, Interested):
            self.flags.am_interested = True
        elif isinstance(msg, Notinterested):
            self.flags.am_interested = False

        try:
            self.writer.write(msg.to_bytes())
            await self.writer.drain()
            self.last_tx_time = time.time()
            print(f'{self.peer_info.ip} - Send: {msg}')
        except (Exception,):
            await self.close()
            return False
        return True

    async def _recv_piece_or_terminate_or_choke(self) -> Piece | Terminate | Choke | None:
        """
        Awaits to receive one of the following: Piece, Terminate, Choke
        """
        msg = None
        while self.flags.connected:
            msg = await self._recv_and_handle_msg()
            if isinstance(msg, Piece) or isinstance(msg, Terminate) or isinstance(msg, Choke):
                break
        return msg

    def _can_perform_request(self):
        """
        Checks if it is ok to send a request to the peer
        """
        return (
                self.flags.am_interested
                and not self.flags.am_choked
                and not self.flags.am_choking  # needed?
        )

    async def _grab_request_and_active_piece_object(self) -> tuple[Request | None, ActivePiece | None]:
        """
        Helper function to grab requests from active pieces
        Need to think of something clever here...
        """
        while self.flags.connected:
            for a_p in self.active_pieces:
                if a_p.piece_info is None:
                    continue
                if not self.has_piece(a_p.piece_info.index):
                    continue
                try:
                    return a_p.get_request(), a_p
                except (Exception,):
                    pass
            await asyncio.sleep(0.5)
        return None, None

    async def _send_keep_alive_if_necessary(self):
        if time.time() - self.last_tx_time >= self.__KEEP_ALIVE_TIMEOUT__:
            await self._send_msg(Keepalive())

    async def _wait_for_response(self, request: Request, active_piece: ActivePiece):
        """
        Wait one of the following to occur
        1. Request is fulfilled
        2. Choke message received
        3. Connection should be terminated
        """

        def correct_piece_received(req: Request, res: Piece):
            return (
                    req.index == res.index
                    and req.begin == res.begin
                    and req.length == len(res.block)
            )

        while True:
            response = await self._recv_piece_or_terminate_or_choke()
            if isinstance(response, Piece):
                if correct_piece_received(request, response):
                    if active_piece.update_data_from_piece_message(response):
                        break
            else:
                await self._send_msg(Cancel(request.index, request.begin, request.length))
                active_piece.put_request_back(request)
                break

    async def _request_loop(self):
        """
        Performs the following as long as peer can accept requests
        1. Grabs a pending request
        2. Sends request to peer
        3. Awaits for appropriate response
        """
        while self._can_perform_request() and self.flags.connected:
            try:
                async with asyncio.timeout(self.__Q_TIMEOUT__):
                    request, active_piece = await self._grab_request_and_active_piece_object()
            except TimeoutError:
                await self._send_keep_alive_if_necessary()
            else:
                try:
                    async with asyncio.timeout(self.__REQUEST_TIMEOUT__):
                        if not await self._send_msg(request):
                            active_piece.put_request_back(request)
                            return
                        await self._wait_for_response(request, active_piece)
                except TimeoutError:
                    await self._send_msg(Cancel(request.index, request.begin, request.length))
                    active_piece.put_request_back(request)
                    await asyncio.sleep(self.__REQUEST_TIMEOUT_PUNISH__)

    async def _wait_till_can_perform_request(self):
        """
        Performs the following as long as peer CANNOT accept requests
        1. Receive peer msg
        2. Handle peer msg
        """
        print(f'{self.peer_info.ip} - waiting loop')
        while not self._can_perform_request() and self.flags.connected:
            try:
                async with asyncio.timeout(self.__GENERAL_COMMUNICATION_TIMEOUT__):
                    await self._recv_and_handle_msg()
            except TimeoutError:
                await self._send_keep_alive_if_necessary()

    async def run(self):
        """
        Handles all peer communication
        """
        await self._connect_and_perform_handshake()
        while self.flags.connected:
            await self._wait_till_can_perform_request()
            await self._request_loop()
        print(f'{self.peer_info.ip} - Goodbye')

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
            return Handshake(info_hash, peer_id, pstr, reserved)
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
        print(f'{self.peer_info.ip} - Recv: {msg}')
        return msg

    async def _handle_received_msg(self, msg: Message) -> Message:
        """
        Handles received message by sending appropriate responses and updating flags
        """
        if isinstance(msg, Terminate):
            await self.close()
        elif isinstance(msg, Unchoke):
            self.flags.am_choked = False
        elif isinstance(msg, Choke):
            self.flags.am_choked = True
        elif isinstance(msg, Interested):
            self.flags.am_interesting = True
        elif isinstance(msg, Notinterested):
            self.flags.am_interesting = False  # lol
        elif isinstance(msg, Bitfield):
            if len(self.bitfield) != len(msg.bitfield):
                await self.close()
                return Terminate(f'Received bitfield length {len(msg.bitfield)} but expected {len(self.bitfield)}')
            self.bitfield = msg.bitfield
            if not await self._send_msg(Interested()):
                msg = Terminate(f'Could not send Interested')
        elif isinstance(msg, Have):
            utils.set_bit_value(self.bitfield, msg.piece_index, 1)
        return msg

    async def _recv_and_handle_msg(self) -> Message | None:
        """
        Receives a message, then handles it, then returns it
        """
        return await self._handle_received_msg(await self._recv_msg())

    async def _connect_and_perform_handshake(self):
        """
        Connect to peer send handshake and await for response
        """
        try:
            async with asyncio.timeout(self.__HANDSHAKE_TIMEOUT__):
                self.reader, self.writer = await asyncio.open_connection(self.peer_info.ip, self.peer_info.port)
                if not await self._send_msg(Handshake(self.torrent_info.info_hash, self.torrent_info.self_id)):
                    await self.close()
                    return
                msg = await self._recv_handshake()
                if not isinstance(msg, Handshake):
                    await self.close()
                    return
                self.flags.connected = True
        except (Exception,):
            pass

    async def close(self):
        """
        Closes peer and resets all flags
        """
        self.flags = PeerFlags()
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except (Exception,):
            pass

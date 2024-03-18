import asyncio
import math
import time
from asyncio import StreamReader, StreamWriter

import messages.ids
from messages import Message, Handshake, Interested, Notinterested, Bitfield, Have, \
    Terminate, Request, Unchoke, Choke, Piece, Keepalive, Cancel
from misc import utils
from peer.flags import Flags
from peer.peer_info import PeerInfo
from peer.stats import Stats
from peer.timeouts import Timeouts
from piece_handling.active_piece import ActivePiece
from torrent.torrent_info import TorrentInfo


class Peer:
    """
    Class that handles connection with a peer.
    """

    def __init__(self, peer_info: PeerInfo, torrent_info: TorrentInfo, active_pieces: tuple[ActivePiece, ...]):
        self.peer_id_str: str = peer_info.peer_id_tracker.decode(encoding='ascii', errors='ignore')
        self.writer: StreamWriter | None = None
        self.reader: StreamReader | None = None
        self.timeouts = Timeouts()
        self.flags = Flags()
        self.stats = Stats()

        self.peer_info = peer_info
        self.torrent_info: TorrentInfo = torrent_info
        self.peer_id_handshake: bytes = bytes()
        self.active_pieces: tuple[ActivePiece, ...] = active_pieces
        self.last_tx_time = 0.0

        self.bitfield: bytearray = bytearray(math.ceil(len(self.torrent_info.pieces_info) / 8))

        self.total_requests_made = 0
        self.completed_requests = 0

    def __eq__(self, other) -> bool:
        if not isinstance(other, Peer):
            return False
        return self.peer_info == other.peer_info

    def __hash__(self) -> int:
        return hash(self.peer_info)

    async def send_msg(self, msg: Message) -> bool:
        """
        Call this function to send messages to peer
        """
        try:
            async with asyncio.timeout(self.timeouts.Send):
                if isinstance(msg, Interested):
                    self.flags.am_interested = True
                elif isinstance(msg, Notinterested):
                    self.flags.am_interested = False
                if isinstance(msg, Choke):
                    if self.flags.am_choking:
                        return True
                    self.flags.am_choking = True
                elif isinstance(msg, Unchoke):
                    if not self.flags.am_choking:
                        return True
                    self.flags.am_choking = False
                elif isinstance(msg, Request):
                    self.stats.total_requests_made += 1

                self.writer.write(msg.to_bytes())
                await self.writer.drain()
                self.last_tx_time = time.time()
        except Exception as e:
            await self.close()
            print(f'{self.peer_info.ip} - {e}')
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
        if time.time() - self.last_tx_time >= self.timeouts.Keep_alive:
            await self.send_msg(Keepalive())

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
                        self.stats.completed_requests += 1
                        break
            else:
                await self.send_msg(Cancel(request.index, request.begin, request.length))
                active_piece.put_request_back(request)
                break

    async def _request_loop(self):
        """
        Performs the following as long as peer can accept requests
        1. Grabs a pending request
        2. Sends request to peer
        3. Awaits for appropriate response
        """
        print(f'{self.peer_info.ip} - request loop')
        while self._can_perform_request() and self.flags.connected:
            try:
                async with asyncio.timeout(self.timeouts.Q):
                    request, active_piece = await self._grab_request_and_active_piece_object()
                    if not request or not active_piece:
                        return
            except TimeoutError:
                await self._send_keep_alive_if_necessary()
                continue
            try:
                if not await self.send_msg(request):
                    active_piece.put_request_back(request)
                    return
                async with asyncio.timeout(self.timeouts.Request):
                    await self._wait_for_response(request, active_piece)
            except TimeoutError:
                await self.send_msg(Cancel(request.index, request.begin, request.length))
                active_piece.put_request_back(request)
                await asyncio.sleep(self.timeouts.Punish)

    async def _wait_till_can_perform_request(self):
        """
        Performs the following as long as peer CANNOT accept requests
        1. Receive peer msg
        2. Handle peer msg
        """
        print(f'{self.peer_info.ip} - waiting loop')
        while not self._can_perform_request() and self.flags.connected:
            try:
                async with asyncio.timeout(self.timeouts.General):
                    await self._recv_and_handle_msg()
            except TimeoutError:
                await self._send_keep_alive_if_necessary()

    async def run(self, bitfield: bytes):
        """
        Handles all peer communication
        """
        if await self._connect_and_perform_handshake():
            await self.send_msg(Bitfield(bitfield))
            await self.send_msg(Unchoke())
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
            if msg_id not in messages.ALL_IDs:
                return Terminate(f'Unknown ID {msg_id}. Possible communication corruption. Closing connection...')
            remaining = msg_len - 1
            msg_payload = await self.reader.readexactly(remaining)
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
            self.flags.am_choked = False
            await self.send_msg(Unchoke())
        elif isinstance(msg, Choke):
            self.flags.am_choked = True
            await self.send_msg(Choke())
        elif isinstance(msg, Interested):
            self.flags.am_interesting = True
        elif isinstance(msg, Notinterested):
            self.flags.am_interesting = False  # lol
        elif isinstance(msg, Bitfield):
            if len(self.bitfield) != len(msg.bitfield):
                await self.close()
                msg = Terminate(f'Received bitfield length {len(msg.bitfield)} but expected {len(self.bitfield)}')
            self.bitfield = msg.bitfield
            if not await self.send_msg(Interested()):
                msg = Terminate(f'Could not send Interested')
        elif isinstance(msg, Have):
            utils.set_bit_value(self.bitfield, msg.piece_index, 1)
        elif isinstance(msg, Request):
            print(f'! ***** I never get requests... Why? ***** !')
            response: Piece = utils.read_piece(msg, self.torrent_info)
            if not await self.send_msg(response):
                msg = Terminate(f'Could not send Interested')
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
            async with asyncio.timeout(self.timeouts.Handshake):
                self.reader, self.writer = await asyncio.open_connection(self.peer_info.ip, self.peer_info.port)
                if not await self.send_msg(Handshake(self.torrent_info.info_hash, self.torrent_info.self_id)):
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
        self.flags = Flags()
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except (Exception,):
            pass

import asyncio
import math
import time
from asyncio import Transport, Event

import bencdec
from file_handling.file_handler import FileHandler
from messages import Message, Handshake, Interested, NotInterested, Bitfield, Have, \
    Request, Unchoke, Choke, Piece, Unknown, Keepalive, Cancel
from messages.extended import Extended
from misc import utils
from peer.flags import Flags
from peer.timeouts import Timeouts
from torrent.torrent_info import TorrentInfo


class TcpPeerProtocol(asyncio.Protocol):
    """
    Protocol class to implement tcp peer communication
    Handshake and Bitfield messages should be sent manually by calling .send() method
    right after a connection is established
    """

    def __init__(self, torrent_info: TorrentInfo, file_handler: FileHandler):
        self._handshake_event: Event = asyncio.Event()
        self._unchoke_received: Event = asyncio.Event()
        self._requests: list[Request] = []

        self._transport: Transport | None = None
        self._flags = Flags()
        self._torrent_info: TorrentInfo = torrent_info
        self._file_handler = file_handler
        self._last_tx_time = 0.0
        self._bitfield: Bitfield = Bitfield(bytes(math.ceil(len(self._torrent_info.pieces_info) / 8)))
        self._buffer: bytearray = bytearray()

    def send_keepalive_if_necessary(self):
        if time.time() - self._last_tx_time >= Timeouts.Keep_alive:
            self.send(Keepalive())

    def can_perform_request(self) -> bool:
        """
        Checks if it is ok to send a request to the peer
        """
        return (
                self._flags.am_interested
                and not self._flags.am_choked
                and self._handshake_event.is_set()
                and len(self._requests) < 8
                and self.is_ok()
        )

    def requests(self):
        return len(self._requests)

    def _find_matching_request(self, piece: Piece) -> Request | None:
        for req in self._requests:
            if piece.index == req.index and piece.begin == req.begin and len(piece.block) == req.data_length:
                return req
        return None

    def get_flags(self):
        return self._flags

    def send(self, msg: Message):
        if not self.is_ok():
            return
        if isinstance(msg, Interested):
            self._flags.am_interested = True
        elif isinstance(msg, NotInterested):
            self._flags.am_interested = False
        if isinstance(msg, Choke):
            if self._flags.am_choking:
                return
            self._flags.am_choking = True
        elif isinstance(msg, Unchoke):
            if not self._flags.am_choking:
                return
            self._flags.am_choking = False
        elif isinstance(msg, Request):
            self._requests.append(msg)

        self._transport.write(msg.to_bytes())
        self._last_tx_time = time.time()

    async def wait_for_response(self, request: Request, timeout: float) -> bool:
        try:
            async with asyncio.timeout(timeout):
                await request.completed.wait()
        except (Exception,):
            request.mark_as_not_complete()
            self.send(Cancel(request.index, request.begin, request.data_length))
        finally:
            if request in self._requests:
                self._requests.remove(request)
        return request.completed.is_set()

    def connection_made(self, transport: Transport):
        self._transport = transport

    def connection_lost(self, exc):
        self.close_transport()

    def _consume_handshake(self):
        if len(self._buffer) < 68:
            return None

        p_strlen = self._buffer[0]
        del self._buffer[0]
        pstr = self._buffer[:p_strlen]
        del self._buffer[:p_strlen]
        reserved = self._buffer[:8]
        del self._buffer[:8]
        info_hash = self._buffer[:20]
        del self._buffer[:20]
        peer_id = self._buffer[:20]
        del self._buffer[:20]
        self._handshake_event.set()
        return Handshake(info_hash, peer_id, pstr, reserved)

    def _consume_buffer(self) -> Message | None:
        if not self._handshake_event.is_set():
            return self._consume_handshake()
        msg = utils.buffer_to_msg(self._buffer)
        if not msg:
            return None
        if isinstance(msg, Unchoke):
            self._unchoke_received.set()
            self._flags.am_choked = False
            self.send(Unchoke())
        elif isinstance(msg, Choke):
            self._unchoke_received.clear()
            self._flags.am_choked = True
            self.send(Choke())
        elif isinstance(msg, Interested):
            self._flags.am_interesting = True
        elif isinstance(msg, NotInterested):
            self._flags.am_interesting = False  # lol
        elif isinstance(msg, Bitfield):
            if self._bitfield.message_length != msg.message_length:
                self.close_transport()
            else:
                self._bitfield = Bitfield(msg.data)
                self.send(Interested())
        elif isinstance(msg, Have):
            self._bitfield.set_bit_value(msg.piece_index, True)
        elif isinstance(msg, Request):
            response: Piece = self._file_handler.read_piece(msg.index, msg.begin, msg.data_length)
            self.send(response)
        elif isinstance(msg, Unknown):
            self.close_transport()
        elif isinstance(msg, Piece):
            request = self._find_matching_request(msg)
            if request:
                self._file_handler.write_piece(msg.index, msg.begin, msg.block)
                request.mark_as_complete()
        elif isinstance(msg, Extended):
            self.extended_dict = bencdec.decode(msg.data)

        bytes_to_remove_from_buffer = msg.message_length + 4
        del self._buffer[0:bytes_to_remove_from_buffer]
        return msg

    def has_piece(self, index: int):
        return self._bitfield.get_bit_value(index)

    def is_ok(self):
        return not self._transport.is_closing()

    async def wait_for_unchoke(self):
        await self._unchoke_received.wait()

    async def wait_for_handshake(self):
        await self._handshake_event.wait()

    def close_transport(self):
        self._transport.close()

    def data_received(self, data: bytes):
        self._buffer += data
        while self._consume_buffer():
            pass

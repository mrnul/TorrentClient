import asyncio
import datetime
import time
from asyncio import Transport

import bencdec
from file_handling.file_handler import FileHandler
from messages import Message, Handshake, Interested, NotInterested, Bitfield, Have, \
    Request, Unchoke, Choke, Piece, Unknown, Keepalive, Cancel
from messages.extended.extended import Extended
from misc import utils
from peer.score import Score
from peer.status_events import StatusEvents
from peer.configuration import Timeouts
from piece_handling.active_request import ActiveRequest


class TcpPeerProtocol(asyncio.Protocol):
    """
    Protocol class to implement tcp peer communication
    Handshake and Bitfield messages should be sent manually by calling .send() method
    right after a connection is established
    """

    def __init__(self, bitfield_len: int, file_handler: FileHandler, name: str | None = None):
        self._score: Score = Score()
        self._grabbed_active_requests: set[ActiveRequest] = set()
        self._transport: Transport | None = None
        self._status = StatusEvents()
        self._ready_for_requests: asyncio.Event = asyncio.Event()
        self._name = name
        self._file_handler = file_handler
        self._last_tx_time = 0.0
        self._bitfield: Bitfield = Bitfield(bytes(bitfield_len))
        self._buffer: bytearray = bytearray()
        self._dead: asyncio.Event = asyncio.Event()

    def __repr__(self):
        return self._name if self._name else "<Empty>"

    def get_score_value(self) -> float:
        return self._score.calculate()

    def send_keepalive_if_necessary(self):
        if time.time() - self._last_tx_time >= Timeouts.Keepalive:
            self.send(Keepalive())

    def _update_ready_for_requests(self):
        """
        Checks if it is ok to send a request to the peer
        """
        if self._status.ok_for_request() and self.active_request_count() < 8 and self.alive():
            self._ready_for_requests.set()
        else:
            self._ready_for_requests.clear()

    def active_request_count(self):
        return len(self._grabbed_active_requests)

    def _find_matching_request(self, piece: Piece) -> ActiveRequest | None:
        for req in self._grabbed_active_requests:
            if piece.index == req.index and piece.begin == req.begin and len(piece.block) == req.data_length:
                return req
        return None

    async def _wait_for_response(self, active_request: ActiveRequest, timeout: float) -> bool:
        try:
            async with asyncio.timeout(timeout):
                await active_request.completed.wait()
        except Exception as e:
            active_request.completed.clear()
            active_request.put_request_back()
            self.send(
                Cancel(
                    active_request.request.index,
                    active_request.request.begin,
                    active_request.request.data_length
                )
            )
            print(f"{self} - Exception: {type(e).__name__} - {e} - {datetime.datetime.now()}")
        self._grabbed_active_requests.discard(active_request)
        self._update_ready_for_requests()
        self._score.update(active_request.completed.is_set())
        active_request.request_processed()
        return active_request.completed.is_set()

    def perform_request(self, active_request: ActiveRequest, timeout: float):
        """
        Sends a request, creates a task that waits for the response
        ActiveRequest object is properly updated / handled
        """
        if self.send(active_request.request):
            self._grabbed_active_requests.add(active_request)
            self._update_ready_for_requests()
        _ = asyncio.create_task(self._wait_for_response(active_request, timeout))

    def send(self, msg: Message) -> bool:
        """
        Sends a message to the peer
        (one should use perform_request to send requests)
        Return True on success False otherwise
        """
        if not self.alive():
            return False
        if isinstance(msg, Interested):
            self._status.am_interested.set()
        elif isinstance(msg, NotInterested):
            self._status.am_interested.clear()
        if isinstance(msg, Choke):
            self._status.am_not_choking.clear()
        elif isinstance(msg, Unchoke):
            self._status.am_not_choking.set()

        self._transport.write(msg.to_bytes())
        self._last_tx_time = time.time()
        self._update_ready_for_requests()
        # print(f"{self} - Send - {msg} - {datetime.datetime.now()}")
        return True

    def connection_made(self, transport: Transport):
        self._transport = transport

    def connection_lost(self, exc):
        self._dead.set()
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
        self._status.handshake.set()
        return Handshake(info_hash, peer_id, pstr, reserved)

    def _consume_buffer(self) -> Message | None:
        if not self._status.handshake.is_set():
            return self._consume_handshake()
        msg = utils.buffer_to_msg(self._buffer)
        if not msg:
            return None
        if isinstance(msg, Unchoke):
            self._status.am_not_choked.set()
            self.send(Unchoke())
        elif isinstance(msg, Choke):
            self._status.am_not_choked.clear()
            self.send(Choke())
        elif isinstance(msg, Interested):
            self._status.am_interesting.set()
        elif isinstance(msg, NotInterested):
            self._status.am_interesting.clear()  # lol
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
                request.completed.set()
        elif isinstance(msg, Extended):
            self.extended_dict = bencdec.decode(msg.raw_data)

        # +4 for the first 4 bytes which hold the message length
        bytes_to_remove_from_buffer = msg.message_length + 4
        del self._buffer[0:bytes_to_remove_from_buffer]
        return msg

    async def punishment(self, duration: float = -1.0):
        if duration < 0.0:
            duration = self._score.get_punishment_duration()
        await asyncio.sleep(duration)

    def has_piece(self, index: int):
        return self._bitfield.get_bit_value(index)

    def alive(self):
        return not self._transport.is_closing()

    async def wait_till_dead(self):
        await self._dead.wait()

    async def wait_till_ready_to_perform_requests(self):
        await self.punishment()
        await self._ready_for_requests.wait()

    async def wait_for_handshake(self):
        await self._status.handshake.wait()

    def close_transport(self):
        self._transport.close()

    def data_received(self, data: bytes):
        self._buffer += data
        while m := self._consume_buffer():
            self._update_ready_for_requests()
            # print(f"{self} - Recv - {m} - {datetime.datetime.now()}")

import asyncio
import datetime
import time
from asyncio import CancelledError

import bencdec
from file_handling.file_handler import FileHandler
from messages import Message, Bitfield, Interested, NotInterested, Choke, Unchoke, Piece, Have, Request, Unknown, \
    Handshake, Cancel, Keepalive
from messages.extended.extended import Extended
from misc import utils
from peer.configuration import Timeouts, Limits, Punishments
from peer.peer_info import PeerInfo
from peer.score import Score
from peer.status_events import StatusFlags
from piece_handling.active_piece import ActivePiece
from piece_handling.active_request import ActiveRequest


class PeerBase:
    """
    Class that acts as a base class and provides the core functionality for peer communication.
    This is connection agnostic meaning that it does not know how the data are RXed / TXed
    So the following methods must be implemented by those who inherit this class (check TcpPeerStream class):
    - close
    - alive
    - create_tcp_connection
    - send_bytes
    """

    def __init__(self, peer_info: PeerInfo, bitfield_len: int, file_handler: FileHandler):
        self._score: Score = Score()
        self._grabbed_active_requests: set[ActiveRequest] = set()
        self._status = StatusFlags()
        self._file_handler = file_handler
        self._last_tx_time = 0.0
        self._bitfield: Bitfield = Bitfield(bytes(bitfield_len))
        self._peer_id_str: str = peer_info.peer_id_tracker.decode(encoding='ascii', errors='ignore')
        self._peer_info: PeerInfo = peer_info
        self._self_report_name: bytes = bytes()
        self._extended_dict: dict = dict()
        self._ready_for_requests_or_dead: asyncio.Event = asyncio.Event()
        self._dead: asyncio.Event = asyncio.Event()
        self._handshaked: asyncio.Event = asyncio.Event()

    def __repr__(self):
        return f"{self._peer_info.ip} : {self._peer_info.port} | {self._self_report_name.decode(errors='ignore')}"

    def __eq__(self, other) -> bool:
        """
        We are using sets to store peers, this ensures uniqueness
        """
        if not isinstance(other, PeerBase):
            return False
        return self._peer_info == other._peer_info

    def __lt__(self, other) -> bool:
        """
        Used for sorting peers based on avg duration
        """
        return self.get_avg_duration() < other.get_avg_duration()

    def __hash__(self) -> int:
        """
        We are using sets to store peers, this ensures uniqueness
        """
        return hash(self._peer_info)

    def printer(self, msg: str):
        import inspect
        caller_name = inspect.stack()[1][3]
        print(f"{self} - {caller_name}: {msg}")

    def handle_msg(self, msg: Message) -> bool:
        """
        Function that handles incoming msg
        Returns True if message was handled successfully
        """
        if not msg:
            return True
        if isinstance(msg, Unchoke):
            self._status.am_choked = False
            self.send(Unchoke())
        elif isinstance(msg, Choke):
            self._status.am_choked = True
            self.send(Choke())
        elif isinstance(msg, Interested):
            self._status.am_interesting = True
        elif isinstance(msg, NotInterested):
            self._status.am_interesting = False  # lol
        elif isinstance(msg, Bitfield):
            if self._bitfield.message_length != msg.message_length:
                self.close_connection()
                self._update_events()
                return False
            else:
                self._bitfield = Bitfield(msg.data)
                self.send(Interested())
        elif isinstance(msg, Have):
            self._bitfield.set_bit_value(msg.piece_index, True)
        elif isinstance(msg, Request):
            response: Piece = self._file_handler.read_piece(msg.index, msg.begin, msg.data_length)
            self.send(response)
        elif isinstance(msg, Unknown):
            self.close_connection()
            self._update_events()
            return False
        elif isinstance(msg, Piece):
            request = self._find_matching_request(msg)
            if request:
                self._file_handler.write_piece(msg.index, msg.begin, msg.block)
                request.completed.set()
        elif isinstance(msg, Extended):
            self._extended_dict = bencdec.decode(msg.raw_data)
        elif isinstance(msg, Handshake):
            self._status.handshake = True
            self._self_report_name = msg.peer_id
        self._update_events()
        return True

    def _find_matching_request(self, piece: Piece) -> ActiveRequest | None:
        """
        When a piece is received this functions finds the relevant active_request from self._grabbed_active_requests
        """
        for req in self._grabbed_active_requests:
            if piece.index == req.index and piece.begin == req.begin and len(piece.block) == req.data_length:
                return req
        return None

    def _update_events(self):
        """
        Sets or clears the appropriate events
        """
        if not self.alive():
            self._ready_for_requests_or_dead.set()
            self._dead.set()
        elif self._status.ok_for_request() and self.active_request_count() < Limits.MaxActiveRequests:
            self._ready_for_requests_or_dead.set()
        else:
            self._ready_for_requests_or_dead.clear()

        if self._status.handshake:
            self._handshaked.set()

    async def _wait_for_response(self, active_request: ActiveRequest, timeout: float) -> bool:
        """
        Waits for active_request to be responded
        """
        try:
            async with asyncio.timeout(timeout):
                await active_request.completed.wait()
            active_request.on_success()
        except Exception as e:
            active_request.on_failure()
            self.send(
                Cancel(
                    active_request.request.index,
                    active_request.request.begin,
                    active_request.request.data_length
                )
            )
            self.printer(f"{type(e).__name__} - {e} - {datetime.datetime.now()}")
        self._grabbed_active_requests.discard(active_request)
        self._update_events()
        self._score.update(active_request.completed.is_set(), active_request.duration())
        return active_request.completed.is_set()

    async def _keep_alive(self):
        self.printer("started")
        while True:
            non_tx_time = time.time() - self._last_tx_time
            if non_tx_time >= Timeouts.Keepalive:
                self.send(Keepalive())
                non_tx_time = 0
            time_to_sleep = Timeouts.Keepalive - non_tx_time
            try:
                await asyncio.sleep(time_to_sleep)
            except CancelledError:
                break
        self.printer("stopped")

    def get_success_rate(self) -> float:
        return self._score.success_rate()

    def get_avg_duration(self) -> float:
        return self._score.avg_duration()

    async def run_till_dead(self, handshake: Handshake):
        """
        Initiates a peer connection, sends bitfield and performs handshake and waits until connection is dead
        """
        # try to create a connection
        if not await self.create_tcp_connection():
            self._update_events()
            return

        # send handshake and bitfield
        if not self.send(handshake):
            self._update_events()
            return
        if not self.send(self._bitfield):
            self._update_events()
            return

        # wait for handshake and terminate if timeout occurs
        if not await utils.run_with_timeout(self.wait_for_handshake(), Timeouts.Handshake):
            await self.close_connection()
            self._update_events()

        keep_alive_task = asyncio.create_task(self._keep_alive())

        await self._dead.wait()
        keep_alive_task.cancel()

    def grab_request(self, active_pieces: list[ActivePiece]) -> ActiveRequest | None:
        """
        Given the list of active pieces, grabs a request that can be served by this peer.
        Once the request is completed / failed, on_success / on_failure must be called on the request
        Returns an ActiveRequest or None
        """
        for active_piece in active_pieces:
            if not self.has_piece(active_piece.piece_info.index):
                continue
            if not (active_request := ActiveRequest.from_active_piece(active_piece)):
                continue
            return active_request
        return None

    def perform_request(self, active_request: ActiveRequest, timeout: float) -> bool:
        """
        Sends a request, creates a task that waits for the response
        ActiveRequest object is properly updated / handled
        """
        if not self.check_if_ready_now():
            active_request.on_failure()
            return False
        if result := self.send(active_request.request):
            self._grabbed_active_requests.add(active_request)
        self._update_events()
        asyncio.create_task(self._wait_for_response(active_request, timeout))
        return result

    def grab_and_perform_a_request(self, active_pieces: list[ActivePiece], timeout: float) -> bool:
        """
        Given the active pieces, grabs an active request (if available) and performs it.
        Handles both success and failure.
        Return true if a request was sent, false otherwise
        """
        active_request: ActiveRequest = self.grab_request(active_pieces)
        if not active_request:
            return False
        return self.perform_request(active_request, timeout)

    def send(self, msg: Message) -> bool:
        if not self.alive():
            return False
        if isinstance(msg, Interested):
            self._status.am_interested = True
        elif isinstance(msg, NotInterested):
            self._status.am_interested = False
        if isinstance(msg, Choke):
            self._status.am_choking = True
        elif isinstance(msg, Unchoke):
            self._status.am_choked = False
        self._last_tx_time = time.time()
        self._update_events()
        return self.send_bytes(msg.to_bytes())

    def has_piece(self, index: int) -> bool:
        return self._bitfield.get_bit_value(index) != 0

    async def wait_till_ready_or_dead(self, delay: float | None = None):
        if delay:
            await asyncio.sleep(delay)
        error_rate: float = 1.0 - self._score.success_rate()
        punishment_duration: float = error_rate * Punishments.Request
        if punishment_duration > Limits.MinDuration:
            self.printer(f"punishment: {punishment_duration} | {self._score.success_rate()}")
            await asyncio.sleep(punishment_duration)
        await self._ready_for_requests_or_dead.wait()
        return self

    def check_if_ready_now(self) -> bool:
        self._update_events()
        return self._ready_for_requests_or_dead.is_set() and self.alive()

    async def wait_for_handshake(self):
        await self._handshaked.wait()

    def active_request_count(self) -> int:
        return len(self._grabbed_active_requests)

    async def close_connection(self):
        """
        This method is used to close connection
        """
        raise NotImplementedError()

    def alive(self) -> bool:
        """
        This method checks if connection is "alive"
        """
        raise NotImplementedError()

    async def create_tcp_connection(self) -> bool:
        """
        Method to actually create the connection.
        This method must return True on success and False otherwise
        """
        raise NotImplementedError()

    def send_bytes(self, data: bytes) -> bool:
        """
        Method that transmits raw data.
        This method must return True on success and False otherwise
        """
        raise NotImplementedError()
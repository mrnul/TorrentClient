import asyncio
import datetime
import math
import time
from asyncio import Transport, Task

from file_handling.file_handler import FileHandler
from messages import Message, Handshake, Interested, NotInterested, Bitfield, Have, \
    Request, Unchoke, Choke, Piece, Unknown, Keepalive, Cancel
from messages.extended import ExtendedHandshake, ExtendedMetadataPieceRequest, ExtendedMetadataPieceResponse, \
    ExtendedMetadataPieceReject
from misc import utils
from peer.status_events import StatusEvents
from peer.timeouts import Timeouts
from piece_handling.active_request import ActiveRequest
from torrent.torrent_info import TorrentInfo


class TcpPeerProtocol(asyncio.Protocol):
    """
    Protocol class to implement tcp peer communication
    Handshake and Bitfield messages should be sent manually by calling .send() method
    right after a connection is established
    """

    def __init__(self, torrent_info: TorrentInfo, file_handler: FileHandler, name: str | None = None):
        self._active_requests: set[ActiveRequest] = set()
        self._transport: Transport | None = None
        self._status = StatusEvents()
        self._name = name
        self._torrent_info: TorrentInfo = torrent_info
        self._file_handler = file_handler
        self._last_tx_time = 0.0
        self._bitfield: Bitfield = Bitfield(bytes(math.ceil(len(self._torrent_info.metadata.pieces_info) / 8)))
        self._buffer: bytearray = bytearray()

    def __repr__(self):
        return self._name if self._name else "<Empty>"

    def send_keepalive_if_necessary(self):
        if time.time() - self._last_tx_time >= Timeouts.Keep_alive:
            self.send(Keepalive())

    def can_perform_request(self) -> bool:
        """
        Checks if it is ok to send a request to the peer
        """
        return (
                self._status.ok_for_request()
                and len(self._active_requests) < 8
                and self.not_closing()
        )

    def request_count(self):
        return len(self._active_requests)

    def _find_matching_request(self, piece: Piece) -> ActiveRequest | None:
        for req in self._active_requests:
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
            if isinstance(e, TimeoutError):
                self.send(
                    Cancel(
                        active_request.request.index,
                        active_request.request.begin,
                        active_request.request.data_length
                    )
                )
            else:
                print(f"Exception: {e} - {self} - {datetime.datetime.now()}")
        finally:
            self._active_requests.discard(active_request)
            active_request.request_processed()
            return active_request.completed.is_set()

    def perform_request(self, active_request: ActiveRequest, timeout: float) -> Task:
        """
        Sends a request, creates a task that waits for the response
        Returns the task to be awaited
        The task is created whether the request has been sent or not and must be awaited
        The result of the task is True if request was responded and False otherwise
        Request object is properly updated / handled in either case
        """
        if self.send(active_request.request):
            self._active_requests.add(active_request)
        return asyncio.create_task(self._wait_for_response(active_request, timeout))

    def send(self, msg: Message) -> bool:
        """
        Sends a message to the peer
        Request messages are also added in self._requests set (one should use perform_request to send requests)
        Return True on success False otherwise
        """
        if not self.not_closing():
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
        return True

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
        elif isinstance(msg, ExtendedHandshake):
            print(f"Recv: {self} - {msg}")
        elif isinstance(msg, ExtendedMetadataPieceRequest):
            print(f"Recv: {self} - {msg}")
        elif isinstance(msg, ExtendedMetadataPieceResponse):
            print(f"Recv: {self} - {msg}")
        elif isinstance(msg, ExtendedMetadataPieceReject):
            print(f"Recv: {self} - {msg}")

        # +4 for the first 4 bytes which hold the message length
        bytes_to_remove_from_buffer = msg.message_length + 4
        del self._buffer[0:bytes_to_remove_from_buffer]
        return msg

    def has_piece(self, index: int):
        return self._bitfield.get_bit_value(index)

    def not_closing(self):
        return not self._transport.is_closing()

    async def wait_for_unchoke(self):
        await self._status.am_not_choked.wait()

    async def wait_for_handshake(self):
        await self._status.handshake.wait()

    def close_transport(self):
        self._transport.close()

    def data_received(self, data: bytes):
        self._buffer += data
        while self._consume_buffer():
            pass

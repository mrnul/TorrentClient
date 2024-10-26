import asyncio

from file_handling.file_handler import FileHandler
from messages import Bitfield, Handshake, Message
from misc import utils
from peer.configuration import Timeouts
from peer.peer_info import PeerInfo
from peer.tcp_peer_protocol import TcpPeerProtocol
from piece_handling.active_piece import ActivePiece
from piece_handling.active_request import ActiveRequest


class Peer:
    """
    Class that handles connection with a peer.
    """

    def __init__(self, peer_info: PeerInfo):
        self.peer_id_str: str = peer_info.peer_id_tracker.decode(encoding='ascii', errors='ignore')
        self.peer_info = peer_info
        self._protocol: TcpPeerProtocol | None = None
        self._protocol_event: asyncio.Event = asyncio.Event()

    def __repr__(self):
        return f"{self.peer_info.ip}:{self.peer_info.port}"

    def __eq__(self, other) -> bool:
        """
        We are using sets to store peers, this ensures uniqueness
        """
        if not isinstance(other, Peer):
            return False
        return self.peer_info == other.peer_info

    def __lt__(self, other) -> bool:
        """
        Used for sorting peers based on score
        """
        return self.get_score() < other.get_score()

    def __hash__(self) -> int:
        """
        We are using sets to store peers, this ensures uniqueness
        """
        return hash(self.peer_info)

    def get_active_request_count(self) -> int:
        """
        Gets the number of requests that are sent and not yet responded
        """
        if not self._protocol:
            return 0
        return self._protocol.active_request_count()

    async def _create_tcp_connection(self, bitfield_len: int, file_handler: FileHandler):
        """
        Creates the protocol, sets the protocol ready event if successful
        """
        try:
            _, self._protocol = await asyncio.get_running_loop().create_connection(
                protocol_factory=lambda: TcpPeerProtocol(
                    bitfield_len=bitfield_len,
                    file_handler=file_handler,
                    name=f"{self}"
                ),
                host=self.peer_info.ip,
                port=self.peer_info.port,
            )
        except Exception as e:
            # print(f"{self} - {e}")
            pass
        self._protocol_event.set()
        return self._protocol

    async def run_till_dead(self, handshake: Handshake, bitfield: Bitfield, file_handler: FileHandler):
        """
        Initiates a peer connection and waits until connection is dead
        Sends bitfield and performs handshake
        """
        # try to create a connection using TcpPeerProtocol
        if not await self._create_tcp_connection(len(bitfield.data), file_handler):
            return

        # send handshake and bitfield
        self._protocol.send(handshake)
        self._protocol.send(bitfield)

        # wait for handshake and terminate if timeout occurs
        if not await utils.run_with_timeout(self._protocol.wait_for_handshake(), Timeouts.Handshake):
            self._protocol.close_transport()

        await self._protocol.wait_till_dead()


    async def ready_for_requests(self, penalty: float | None = None):
        """
        Awaits for peer to be ready to accept piece requests.
        Returns self
        """
        if penalty is not None:
            await asyncio.sleep(penalty)
        await self._protocol_event.wait()
        if self._protocol:
            await self._protocol.wait_till_ready()
        return self

    def send(self, msg: Message) -> bool:
        """
        Sends message to peer.
        Returns true on success, false otherwise
        """
        if not self._protocol:
            return False
        return self._protocol.send(msg)

    def has_piece(self, index: int) -> bool:
        """
        Returns true if peer has this piece, false otherwise
        """
        if not self._protocol:
            return False
        return self._protocol.has_piece(index)

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
        Performs the active_request handling both success and failure.
        Return true if request was sent, false otherwise
        """
        if not self._protocol:
            active_request.on_failure()
            return False
        return self._protocol.perform_request(active_request, timeout)


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

    def alive(self) -> bool:
        """
        Returns true if transport is NOT closing, false otherwise
        """
        if not self._protocol:
            return False
        return self._protocol.alive()

    def get_score(self) -> float:
        """
        Calculates the percentage of success requests
        """
        if not self._protocol:
            return -1.0
        return self._protocol.get_score_value()

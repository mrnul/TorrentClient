import asyncio

from file_handling.file_handler import FileHandler
from messages import Bitfield, Message, Handshake
from misc import utils
from peer.peer_info import PeerInfo
from peer.tcp_peer_protocol import TcpPeerProtocol
from peer.timeouts import Timeouts
from piece_handling.active_piece import ActivePiece
from piece_handling.active_request import ActiveRequest
from torrent.torrent_info import TorrentInfo


class Peer:
    """
    Class that handles connection with a peer.
    """

    def __init__(self, peer_info: PeerInfo, torrent_info: TorrentInfo, active_pieces: list[ActivePiece]):
        self.peer_id_str: str = peer_info.peer_id_tracker.decode(encoding='ascii', errors='ignore')
        self.peer_info = peer_info
        self.active_pieces = active_pieces
        self.torrent_info = torrent_info
        self.protocol: TcpPeerProtocol | None = None

    def __repr__(self):
        return f"{self.peer_info.ip}:{self.peer_info.port}"

    def __eq__(self, other) -> bool:
        if not isinstance(other, Peer):
            return False
        return self.peer_info == other.peer_info

    def __hash__(self) -> int:
        return hash(self.peer_info)

    def requests(self) -> int:
        """
        Gets the number of requests that are sent and not yet responded
        """
        if not self.protocol:
            return 0
        return self.protocol.active_request_count()

    def _grab_request(self) -> ActiveRequest | None:
        for active_piece in self.active_pieces:
            if not self.protocol.has_piece(active_piece.piece_info.index):
                continue
            if not (active_request := ActiveRequest.from_active_piece(active_piece)):
                continue
            return active_request
        return None

    def send(self, msg: Message):
        if self.protocol:
            self.protocol.send(msg)

    async def _create_tcp_connection(self, bitfield_len: int, file_handler: FileHandler):
        try:
            _, self.protocol = await asyncio.get_running_loop().create_connection(
                protocol_factory=lambda: TcpPeerProtocol(
                    bitfield_len=bitfield_len,
                    file_handler=file_handler,
                    name=f"{self}"
                ),
                host=self.peer_info.ip,
                port=self.peer_info.port,
            )
        except Exception as e:
            print(f"{self} - {e}")
        return self.protocol

    async def run(self, handshake: Handshake, bitfield: Bitfield, file_handler: FileHandler):
        """
        Handles all peer communication
        """
        # try to create a connection using TcpPeerProtocol
        if not await self._create_tcp_connection(len(bitfield.data), file_handler):
            return

        # send handshake and bitfield
        self.protocol.send(handshake)
        self.protocol.send(bitfield)

        # wait for handshake and terminate if timeout occurs
        if not await utils.run_with_timeout(self.protocol.wait_for_handshake(), Timeouts.Handshake):
            self.protocol.close_transport()

        # while transport is open keep communicating
        while self.protocol.alive():
            # check whether a Keepalive msg should be sent
            self.protocol.send_keepalive_if_necessary()

            # wait for peer readiness
            if not await utils.run_with_timeout(self.protocol.wait_till_ready_to_perform_requests(), Timeouts.Ready):
                continue

            # now that we can make requests grab a request along with the active piece
            active_request: ActiveRequest = self._grab_request()
            if not active_request:
                await asyncio.sleep(Timeouts.Punish_request)
                continue
            self.protocol.perform_request(active_request, Timeouts.Request)

        self.protocol = None
        print(f'{self} - Goodbye')

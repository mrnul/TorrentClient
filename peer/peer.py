import asyncio
from asyncio import Task

from file_handling.file_handler import FileHandler
from messages import Bitfield, Message, Handshake, Request
from misc import utils
from peer.peer_info import PeerInfo
from peer.tcp_peer_protocol import TcpPeerProtocol
from peer.timeouts import Timeouts
from piece_handling.active_piece import ActivePiece
from torrent.torrent_info import TorrentInfo


class Peer:
    """
    Class that handles connection with a peer.
    """

    def __init__(self, peer_info: PeerInfo, torrent_info: TorrentInfo,
                 file_handler: FileHandler, active_pieces: list[ActivePiece]):
        self.peer_id_str: str = peer_info.peer_id_tracker.decode(encoding='ascii', errors='ignore')
        self.peer_info = peer_info
        self.active_pieces = active_pieces
        self.torrent_info = torrent_info
        self.file_handler = file_handler
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
        return self.protocol.request_count()

    def am_interesting(self) -> bool:
        if not self.protocol:
            return False
        return self.protocol.get_flags().am_interesting

    def _grab_request(self) -> Request | None:
        if not self.protocol.can_perform_request():
            return None
        for active_piece in self.active_pieces:
            if not self.protocol.has_piece(active_piece.piece_info.index):
                continue
            if not (request := active_piece.get_request()):
                continue
            return request
        return None

    def send(self, msg: Message):
        if self.protocol:
            self.protocol.send(msg)

    async def _create_tcp_connection(self):
        try:
            _, self.protocol = await asyncio.get_running_loop().create_connection(
                protocol_factory=lambda: TcpPeerProtocol(
                    self.torrent_info,
                    self.file_handler,
                    name=f"{self}"
                ),
                host=self.peer_info.ip,
                port=self.peer_info.port,
            )
        except Exception as e:
            print(f"{self} - {e}")
        return self.protocol

    async def run(self, bitfield: Bitfield):
        """
        Handles all peer communication
        """
        # try to create a connection using TcpPeerProtocol
        if not await self._create_tcp_connection():
            return

        # send handshake and bitfield
        reserved = bytearray(int(0).to_bytes(8))
        reserved[5] = 0x10  # extended message protocol
        self.protocol.send(Handshake(self.torrent_info.info_hash, self.torrent_info.self_id, reserved=reserved))
        self.protocol.send(bitfield)

        # wait for handshake and terminate if timeout occurs
        if not await utils.run_with_timeout(self.protocol.wait_for_handshake(), Timeouts.Handshake):
            self.protocol.close_transport()

        response_tasks: set[Task] = set()
        # while transport is open keep communicating
        while self.protocol.is_ok():
            # check whether a Keepalive msg should be sent
            self.protocol.send_keepalive_if_necessary()

            # we can send requests only if unchoke is received
            if not await utils.run_with_timeout(self.protocol.wait_for_unchoke(), Timeouts.Unchoke):
                continue

            # now that we can make requests grab a request along with the active piece
            request = self._grab_request()
            if not request:
                if not response_tasks:
                    # at this point no new request and nothing to wait for
                    await asyncio.sleep(Timeouts.Punish_queue)
                else:
                    # at this point no new request, but we are waiting for some responses
                    done, response_tasks = await asyncio.wait(response_tasks, return_when=asyncio.FIRST_COMPLETED)
                    if any(not completed.result() for completed in done):
                        # if there is at least one request that was not fulfilled then punish by sleeping
                        await asyncio.sleep(Timeouts.Punish_request)
                continue

            # at this point we have grabbed a request and we should send it
            self.protocol.send(request)
            # create the tasks that will await for the response
            response_tasks.add(
                asyncio.create_task(self.protocol.wait_for_response(request, Timeouts.Request))
            )

        self.protocol = None
        print(f'{self} - Goodbye')

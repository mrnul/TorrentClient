import asyncio

from file_handling.file_handler import FileHandler
from messages import Request, Bitfield, Message, Handshake
from misc import utils
from peer.peer_info import PeerInfo
from peer.tcp_peer_protocol import TcpPeerProtocol
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

    def _grab_active_piece_and_request(self) -> tuple[ActivePiece | None, Request | None]:
        if not self.protocol.can_perform_request():
            return None, None
        for active_piece in self.active_pieces:
            if not self.protocol.has_piece(active_piece.piece_info.index):
                continue
            if not (request := active_piece.get_request()):
                continue
            return active_piece, request
        return None, None

    def send(self, msg: Message):
        if self.protocol:
            self.protocol.send(msg)

    async def _create_tcp_connection(self):
        try:
            _, self.protocol = await asyncio.get_running_loop().create_connection(
                protocol_factory=lambda: TcpPeerProtocol(
                    self.torrent_info,
                    self.file_handler,
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
        self.protocol.send(Handshake(self.torrent_info.info_hash, self.torrent_info.self_id))
        self.protocol.send(bitfield)

        # wait for handshake and terminate if timeout occurs
        if not await utils.run_with_timeout(self.protocol.wait_for_handshake(), 10.0):
            self.protocol.close_transport()

        # while transport is open keep communicating
        while self.protocol.is_ok():
            # check whether a Keepalive msg should be sent
            self.protocol.send_keepalive_if_necessary()

            # we can send requests only if unchoke is received
            if not await utils.run_with_timeout(self.protocol.wait_for_unchoke(), 10.0):
                continue

            # now that we can make requests grab a request along with the active piece
            active_piece, request = self._grab_active_piece_and_request()
            if not active_piece or not request:
                # now there is no request that this peer can serve
                # "punish" this peer by sleeping for a few seconds
                await asyncio.sleep(1.0)
                continue

            # at this point we have grabbed a request and we should send it
            self.protocol.send(request)

            # wait till request is responded
            if await utils.run_with_timeout(self.protocol.wait_for_response(), 10.0):
                # if we have a valid response update the queue inside active piece
                active_piece.request_done()
            else:
                # request timed-out
                # send a cancel message for the previously sent request
                self.protocol.cancel_active_request()
                # put request back in the queue
                active_piece.put_request_back(request)
                print(f"{self} - Request timed out")
                # "punish" this peer by sleeping for a few seconds
                await asyncio.sleep(10.0)
        await self.protocol.wait_for_connection_lost()
        print(f'{self} - Goodbye')

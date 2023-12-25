import asyncio

from messages import Piece
from misc import utils
from peer import Peer
from peer.peer_info import PeerInfo
from piece_handler.active_piece import ActivePiece
from torrent.torrent_info import TorrentInfo
from tracker.tracker import Tracker


class Torrent:
    __MAX_ACTIVE_PIECES__ = 50

    def disk_writer(self, piece: Piece):
        f1, b1 = utils.get_file_and_byte_from_byte_in_torrent(piece.index, self.torrent_info.piece_size,
                                                              0,
                                                              self.torrent_info.torrent_files)

        f2, b2 = utils.get_file_and_byte_from_byte_in_torrent(piece.index, self.torrent_info.piece_size,
                                                              len(piece.block) - 1,
                                                              self.torrent_info.torrent_files)
        if f1 == f2:
            f1.file.seek(b1)
            f1.file.write(piece.block)
        else:
            for i, byte_value in enumerate(piece.block):
                f, b = utils.get_file_and_byte_from_byte_in_torrent(piece.index, self.torrent_info.piece_size,
                                                                    i,
                                                                    self.torrent_info.torrent_files)
                f.file.seek(b)
                f.file.write(int(byte_value).to_bytes(1))

    def __init__(self, torrent_info: TorrentInfo):
        self.torrent_info = torrent_info
        self.peers: set[Peer] = set()
        self.active_pieces: tuple[ActivePiece, ...] = tuple(ActivePiece() for _ in range(self.__MAX_ACTIVE_PIECES__))
        self.total_pieces_count: int = len(self.torrent_info.pieces_info)
        self.pending_pieces_indexes: list[int] = [i for i in range(self.total_pieces_count)]
        self.completed_pieces_indexes: list[int] = []

    def refresh_peers(self):
        peer_info: set[PeerInfo] = set()
        for tracker in self.torrent_info.trackers:
            peer_info |= Tracker(tracker).request_peers(self.torrent_info)

        new_peers: set[Peer] = set()
        for p_i in peer_info:
            peer = Peer(p_i, self.torrent_info)
            if peer not in self.peers:
                self.peers.add(peer)
                new_peers.add(peer)
        return new_peers

    def _choose_pending_piece(self) -> int | None:
        try:
            return self.pending_pieces_indexes.pop(0)
        except IndexError:
            return None

    def _update_active_piece(self, active_piece: ActivePiece) -> bool:
        piece_index = self._choose_pending_piece()
        if piece_index is None:
            active_piece.set(None)
            return False

        active_piece.set(self.torrent_info.pieces_info[piece_index])
        print(f'Active piece: {active_piece.piece_info.index}')
        return True

    def _initialize_active_pieces(self):
        for active_piece in self.active_pieces:
            self._update_active_piece(active_piece)

    async def download(self):
        # initialize ActivePiece structures
        self._initialize_active_pieces()

        # create peer tasks to connect, handshake, and perform requests
        tasks = [asyncio.create_task(peer.run(self.active_pieces)) for peer in self.refresh_peers()]

        # build tasks that will join on active piece queues
        pending = [asyncio.create_task(ap.join_queue()) for ap in self.active_pieces]

        # loop as long as there are pieces that are not completed
        while len(self.completed_pieces_indexes) != self.total_pieces_count:
            # wait for at least one queue to join
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for done_piece in done:
                # get the ActivePiece object
                result: ActivePiece = done_piece.result()
                if result.piece_info is None:
                    continue
                if result.is_hash_ok():
                    # put piece in completed list
                    self.completed_pieces_indexes.append(result.piece_info.index)
                    self.disk_writer(Piece(result.piece_info.index, 0, result.data))
                else:
                    self.pending_pieces_indexes.append(result.piece_info.index)
                # update object to a new piece (if any)
                if self._update_active_piece(result):
                    # create a new pending task that will join on the newly updated queue
                    pending.add(asyncio.create_task(result.join_queue()))

            print(f'Progress {len(self.completed_pieces_indexes)} / {self.total_pieces_count}\r\n')

        await asyncio.gather(*[peer.close() for peer in self.peers])
        await asyncio.gather(*tasks)
        print("Goodbye!")

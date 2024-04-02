import asyncio
from asyncio import Task

from file_handling.file_handler import FileHandler
from messages import Have, Bitfield
from peer import Peer
from piece_handling.active_piece import ActivePiece
from piece_handling.piece_info import PieceInfo
from torrent.torrent_info import TorrentInfo
from tracker import Tracker


class Torrent:
    """
    A class that represent a torrent and handles download/upload sessions
    """
    __PROGRESS_TIMEOUT__ = 10.0

    def __init__(self, torrent_info: TorrentInfo, max_active_pieces: int = 0):
        self.torrent_info = torrent_info
        self.file_handler = FileHandler(self.torrent_info)
        self.peers: set[Peer] = set()
        self.peer_tasks: set[Task] = set()
        self.tracker_tasks: set[Task] = set()
        self.piece_tasks: set[Task] = set()
        self.piece_count: int = len(self.torrent_info.pieces_info)
        self.pending_pieces: list[int] = list(set(range(self.piece_count)) - set(self.file_handler.completed_pieces))
        self.bitfield: Bitfield = Bitfield.from_completed_pieces(self.file_handler.completed_pieces, self.piece_count)
        self.max_active_pieces: int = max_active_pieces if max_active_pieces else len(self.pending_pieces)
        self.active_pieces: list[ActivePiece] = []

    async def _tracker_job(self, tracker: str):
        """
        Tracker jobs run in the background to periodically perform requests, get peer lists and create peer tasks
        """
        while True:
            peers, interval = await Tracker(tracker, self.torrent_info).request_peers()
            print(f"{tracker} ({len(peers)}, {interval})")
            for p_i in peers:
                peer = Peer(p_i, self.torrent_info, self.file_handler, self.active_pieces)
                if peer not in self.peers:
                    self.peers.add(peer)
                    self.peer_tasks.add(
                        asyncio.create_task(
                            peer.run(self.bitfield),
                            name=f'Peer {peer.peer_info.ip}'
                        )
                    )
            if interval < 10:
                interval = 10
            await asyncio.sleep(interval)

    def _begin_trackers(self):
        for tracker in self.torrent_info.trackers:
            self.tracker_tasks.add(asyncio.create_task(self._tracker_job(tracker), name=f'Tracker {tracker}'))

    def _choose_pending_piece(self) -> int | None:
        """
        Strategy to choose which piece should be downloaded

        For now just get the first piece
        """
        try:
            return self.pending_pieces.pop(0)
        except IndexError:
            return None

    @staticmethod
    async def _cancel_tasks(tasks: set[Task]):
        """
        Method to cancel and await for tasks to complete
        """
        if not tasks:
            return
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    async def _cleanup_tasks(tasks: set[Task]):
        """
        Method to check and remove from set tasks that are done
        """
        done_tasks = [task for task in tasks if task.done()]
        for done_task in done_tasks:
            tasks.remove(done_task)

    def _handle_completed_piece(self, piece: ActivePiece):
        """
        Marks piece as complete
        Notifies other peers with Have message
        Removes related active piece from list
        """
        self.file_handler.completed_pieces.append(piece.piece_info.index)
        self.bitfield.set_bit_value(piece.piece_info.index, True)
        print(f'Piece done: {piece.piece_info.index}')
        for peer in self.peers:
            peer.enqueue_msg(Have(piece.piece_info.index))
        self.active_pieces.remove(piece)

    def _handle_hash_error(self, piece: ActivePiece):
        """
        An active piece can be completed but with wrong hash value
        Put that piece back in pending pieces list in order to be downloaded again at some point
        """
        print(f'Hash error: {piece.piece_info.index}')
        self.pending_pieces.append(piece.piece_info.index)

    def _update_active_pieces(self):
        """
        Ensures that active piece list has at most max_active_pieces elements
        Creates new actives pieces if necessary and their appropriate piece_tasks to await on request queue
        """
        active_pieces_count = len(self.active_pieces)
        if active_pieces_count >= self.max_active_pieces:
            print("Will not update active pieces")
            return
        pieces_to_create = min(self.max_active_pieces - active_pieces_count, len(self.pending_pieces))
        print(f"Creating {pieces_to_create} new active pieces")
        for _ in range(pieces_to_create):
            piece_index = self._choose_pending_piece()
            if piece_index is None:
                continue
            piece_info = self.torrent_info.pieces_info[piece_index]
            new_active_piece = ActivePiece(piece_index)
            new_active_piece.set(piece_info)
            self.active_pieces.append(new_active_piece)
            print(f"New active piece added: {new_active_piece}")
            self.piece_tasks.add(
                asyncio.create_task(new_active_piece.join_queue(), name=f"ActivePiece {new_active_piece.uid}")
            )

    async def download(self):
        """
        Initializes active pieces, begins trackers and runs until all pieces are completed
        """
        print(f'Loaded: {len(self.file_handler.completed_pieces)} / {self.piece_count}')
        # initialize ActivePiece structures
        self._update_active_pieces()
        self._begin_trackers()

        # loop as long as there are pieces that are not completed
        while len(self.file_handler.completed_pieces) != self.piece_count:
            try:
                # wait for at least one queue to join
                done, self.piece_tasks = await asyncio.wait(
                    self.piece_tasks,
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=self.__PROGRESS_TIMEOUT__
                )
                for done_piece in done:
                    result: ActivePiece = done_piece.result()
                    piece_info: PieceInfo = result.piece_info

                    data = self.file_handler.read_piece(piece_info.index, 0, piece_info.length).block
                    if result.is_hash_ok(data):
                        self._handle_completed_piece(result)
                    else:
                        self._handle_hash_error(result)
                    self._update_active_pieces()
                    print(f"Active pieces count: {len(self.active_pieces)}")
            except TimeoutError:
                pass
            await self._cleanup_tasks(self.peer_tasks)

            print(f'Progress {len(self.file_handler.completed_pieces)} / {self.piece_count} | '
                  f'{len(self.peer_tasks)} connected peers\r\n')
        print(f'Torrent {self.torrent_info.torrent_file} downloaded!')

    async def terminate(self):
        """
        Performs cleanup

        I don't think it works properly
        """
        await self._cancel_tasks(self.tracker_tasks)
        await asyncio.gather(*[peer.close() for peer in self.peers])
        await asyncio.gather(*self.peer_tasks)
        await self._cancel_tasks(self.piece_tasks)
        await self._cleanup_tasks(self.tracker_tasks)
        await self._cleanup_tasks(self.peer_tasks)
        await self._cleanup_tasks(self.piece_tasks)
        self.peers.clear()
        print(f'Torrent {self.torrent_info.torrent_file} terminated!')

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

    def __init__(self, torrent_info: TorrentInfo):
        self.torrent_info = torrent_info
        self.file_handler = FileHandler(self.torrent_info)
        self.peers: set[Peer] = set()
        self.peer_tasks: set[Task] = set()
        self.tracker_tasks: set[Task] = set()
        self.piece_tasks: set[Task] = set()
        self.piece_count: int = len(self.torrent_info.pieces_info)
        self.pending_pieces: list[int] = list(set(range(self.piece_count)) - set(self.file_handler.completed_pieces))
        self.bitfield: Bitfield = Bitfield.from_completed_pieces(self.file_handler.completed_pieces, self.piece_count)
        self.active_pieces: tuple[ActivePiece, ...] = tuple(ActivePiece(i) for i in range(len(self.pending_pieces)))

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

    def _update_active_piece(self, active_piece: ActivePiece) -> bool:
        """
        Each time a piece is done (that is, no requests remain in queue) we should update it to a new pending piece
        """
        piece_index = self._choose_pending_piece()
        if piece_index is None:
            active_piece.set(None)
            return False
        active_piece.set(self.torrent_info.pieces_info[piece_index])
        print(f'New active piece: {piece_index}')
        return True

    def _initialize_active_pieces(self):
        for active_piece in self.active_pieces:
            self._update_active_piece(active_piece)

    @staticmethod
    async def _cancel_tasks(tasks: set[Task]):
        if not tasks:
            return
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    async def _cleanup_tasks(tasks: set[Task]):
        done_tasks = [task for task in tasks if task.done() or task.cancelled()]
        for done_task in done_tasks:
            tasks.remove(done_task)

    def _cleanup_tracker_tasks(self):
        done_tasks = [task for task in self.tracker_tasks if task.done() or task.cancelled()]
        for done_task in done_tasks:
            self.tracker_tasks.remove(done_task)

    def _cleanup_peer_tasks(self):
        done_tasks = [task for task in self.peer_tasks if task.done() or task.cancelled()]
        for done_task in done_tasks:
            self.peer_tasks.remove(done_task)

    async def download(self):
        """
        Initializes active pieces, begins trackers and runs until all pieces are completed
        """
        print(f'Loaded: {len(self.file_handler.completed_pieces)} / {self.piece_count}')
        # initialize ActivePiece structures
        self._initialize_active_pieces()
        self._begin_trackers()

        # build tasks that will join on active piece queues
        self.piece_tasks = set(asyncio.create_task(ap.join_queue(), name=f"ActivePiece {ap.uid}")
                               for ap in self.active_pieces)
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
                    # get the ActivePiece object
                    result: ActivePiece = done_piece.result()
                    piece_info: PieceInfo = result.piece_info
                    if result.piece_info is None:
                        continue

                    data = self.file_handler.read_piece(piece_info.index, 0, piece_info.length).block
                    if result.is_hash_ok(data):
                        # put piece in completed list
                        self.file_handler.completed_pieces.append(piece_info.index)
                        self.bitfield.set_bit_value(piece_info.index, True)
                        print(f'Piece done: {piece_info.index}')
                        for peer in self.peers:
                            peer.enqueue_msg(Have(piece_info.index))
                    else:
                        self.pending_pieces.append(piece_info.index)
                        print(f'Hash error: {piece_info.index}')
                    # update object to a new piece (if any)
                    if self._update_active_piece(result):
                        # create a new pending task that will join on the newly updated queue
                        self.piece_tasks.add(
                            asyncio.create_task(result.join_queue(), name=f"ActivePiece {result.uid}")
                        )
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

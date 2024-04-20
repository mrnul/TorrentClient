import asyncio
from asyncio import Task

from file_handling.file_handler import FileHandler
from messages import Have, Bitfield
from peer import Peer
from peer.timeouts import Timeouts
from piece_handling.active_piece import ActivePiece
from piece_handling.piece_info import PieceInfo
from torrent.torrent_info import TorrentInfo
from tracker import Tracker


class Torrent:
    """
    A class that represent a torrent and handles download/upload sessions
    """
    def __init__(self, torrent_info: TorrentInfo):
        self.torrent_info = torrent_info
        self.file_handler = FileHandler(self.torrent_info)
        self.peers: set[Peer] = set()
        self.peer_tasks: set[Task] = set()
        self.tracker_tasks: set[Task] = set()
        self.piece_count: int = len(self.torrent_info.pieces_info)
        self.completed_pieces: list[int] = self.file_handler.get_completed_pieces()
        self.pending_pieces: list[int] = list(set(range(self.piece_count)) - set(self.completed_pieces))
        self.bitfield: Bitfield = Bitfield.from_completed_pieces(self.completed_pieces, self.piece_count)
        self.max_active_pieces: int = (
            self.torrent_info.max_active_pieces
            if self.torrent_info.max_active_pieces
            else len(self.pending_pieces)
        )
        self.active_pieces: list[ActivePiece] = []
        self._stop = False

    async def _tracker_job(self, tracker: str):
        """
        Tracker jobs run in the background to periodically perform requests, get peer lists and create peer tasks
        """
        while True:
            peers, interval = await Tracker(tracker, self.torrent_info).request_peers()
            for p_i in peers:
                peer = Peer(p_i, self.torrent_info, self.file_handler, self.active_pieces)
                if peer in self.peers:
                    continue
                self.peers.add(peer)
                self.peer_tasks.add(
                    asyncio.create_task(
                        peer.run(self.bitfield),
                        name=f'Peer {peer.peer_info.ip}'
                    )
                )
            if interval < 60:
                interval = 60
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
        self.completed_pieces.append(piece.piece_info.index)
        self.bitfield.set_bit_value(piece.piece_info.index, True)
        print(f'Piece done: {piece.piece_info.index}')
        for peer in self.peers:
            peer.send(Have(piece.piece_info.index))
        self.active_pieces.remove(piece)

    def _handle_hash_error(self, piece: ActivePiece):
        """
        An active piece can be completed but with wrong hash value
        Put that piece back in pending pieces list in order to be downloaded again at some point
        """
        print(f'Hash error: {piece.piece_info.index}')
        self.pending_pieces.append(piece.piece_info.index)

    def _update_active_pieces_and_get_piece_tasks(self) -> set[Task]:
        """
        Ensures that active piece list has at most max_active_pieces elements
        Creates new actives pieces if necessary and their appropriate piece_tasks to await on request queue
        """
        new_piece_tasks = set()
        active_pieces_count = len(self.active_pieces)
        if active_pieces_count >= self.max_active_pieces:
            return new_piece_tasks
        pieces_to_create = min(self.max_active_pieces - active_pieces_count, len(self.pending_pieces))
        for _ in range(pieces_to_create):
            piece_index = self._choose_pending_piece()
            if piece_index is None:
                continue
            piece_info = self.torrent_info.pieces_info[piece_index]
            new_active_piece = ActivePiece(piece_index, piece_info, self.torrent_info.max_request_length)
            self.active_pieces.append(new_active_piece)
            new_piece_tasks.add(
                asyncio.create_task(new_active_piece.join_queue(), name=f"ActivePiece {new_active_piece.uid}")
            )
        return new_piece_tasks

    async def download(self):
        """
        Begins trackers, creates and awaits on piece_tasks if any, enters simple seed mode if all pieces are complete
        """
        print(f'Loaded: {len(self.completed_pieces)} / {self.piece_count}')
        self._begin_trackers()

        # loop "forever"
        piece_tasks: set[Task] = set()
        while not self._stop:
            # create and get new piece_tasks if necessary
            piece_tasks |= self._update_active_pieces_and_get_piece_tasks()
            if not piece_tasks:
                # simple seed mode since all pieces are received
                print(f"{self.torrent_info.torrent_file} - Seeding...")
                await asyncio.sleep(Timeouts.Progress)
            else:
                # wait for at least one queue to join
                print(f"Active pieces count: {len(self.active_pieces)}")
                done, piece_tasks = await asyncio.wait(
                    piece_tasks,
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=Timeouts.Progress
                )
                # for each completed piece read written data and check hash value
                for done_piece in done:
                    result: ActivePiece = done_piece.result()
                    piece_info: PieceInfo = result.piece_info
                    data = self.file_handler.read_piece(piece_info.index, 0, piece_info.length).block
                    if result.is_hash_ok(data):
                        self._handle_completed_piece(result)
                    else:
                        self._handle_hash_error(result)
            # we can remove done peer tasks from the set
            await self._cleanup_tasks(self.peer_tasks)

            print(
                f'Progress {len(self.completed_pieces)} / {self.piece_count} | '
                f'{len(self.peer_tasks)} running peers | '
                f'{sum(1 for peer in self.peers if peer.requests() > 0)} active peers\r\n'
            )

    async def terminate(self):
        """
        Performs cleanup

        I don't think it works properly
        """

        await self._cancel_tasks(self.tracker_tasks)
        await self._cancel_tasks(self.peer_tasks)
        print(f'Torrent {self.torrent_info.torrent_file} terminated!')

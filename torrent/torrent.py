import asyncio
import random
from asyncio import Task

from file_handling.file_handler import FileHandler
from messages import Have, Bitfield
from peer import Peer
from peer.configuration import Timeouts
from piece_handling.active_piece import ActivePiece
from piece_handling.active_request import ActiveRequest
from piece_handling.piece_info import PieceInfo
from torrent.torrent_info import TorrentInfo
from tracker import Tracker


class Torrent:
    """
    A class that represent a torrent and handles download/upload sessions
    """

    def __init__(self, torrent_info: TorrentInfo):
        self.torrent_info = torrent_info
        self.file_handler = FileHandler(self.torrent_info.metadata)
        self.peers: set[Peer] = set()
        self.peer_tasks: set[Task] = set()
        self.peer_readiness_tasks: set[Task] = set()
        self.trackers: set[Tracker] = set()
        self.tracker_tasks: set[Task] = set()
        self.bitfield: Bitfield = Bitfield()
        self.max_active_pieces: int = 0
        self.active_pieces: list[ActivePiece] = []
        self.piece_tasks: set[Task] = set()
        self._stop: asyncio.Event = asyncio.Event()

    def _begin_trackers(self):
        for tracker in self.torrent_info.trackers:
            t = Tracker(tracker, self.torrent_info)
            tracker_task = asyncio.create_task(
                t.tracker_main_job(
                    self.peers,
                    self.peer_tasks,
                    self.peer_readiness_tasks,
                    self.bitfield,
                    self.file_handler,
                    self.active_pieces
                ), name=f'Tracker {tracker}')
            self.tracker_tasks.add(tracker_task)
            tracker_task.add_done_callback(self.tracker_tasks.discard)
            self.trackers.add(t)

    def _choose_pending_piece(self) -> int | None:
        """
        Strategy to choose which piece should be downloaded

        For now just get a random piece
        """
        try:
            piece = random.choice(self.file_handler.pending_pieces)
            self.file_handler.pending_pieces.remove(piece)
            return piece
        except IndexError:
            return None

    def _handle_completed_piece(self, piece: ActivePiece):
        """
        Marks piece as complete
        Notifies other peers with Have message
        Removes related active piece from list
        """
        self.file_handler.completed_pieces.append(piece.piece_info.index)
        self.bitfield.set_bit_value(piece.piece_info.index, True)
        print(
            f'Piece done: {piece.piece_info.index} || '
            f'Progress: {len(self.file_handler.completed_pieces)} / {self.torrent_info.metadata.piece_count}'
        )
        for peer in self.peers:
            if peer.protocol_ready.is_set():
                peer.protocol.send(Have(piece.piece_info.index))
        self.active_pieces.remove(piece)

    def _handle_hash_error(self, piece: ActivePiece):
        """
        An active piece can be completed but with wrong hash value
        Put that piece back in pending pieces list in order to be downloaded again at some point
        """
        print(f'Hash error: {piece.piece_info.index}')
        self.active_pieces.remove(piece)
        self.file_handler.pending_pieces.append(piece.piece_info.index)

    def _update_active_pieces_and_piece_tasks(self):
        """
        Ensures that active piece list has at most max_active_pieces elements
        Creates new actives pieces if necessary and their appropriate piece_tasks
        Uses piece_done_callback to handle completed pieces
        """
        def piece_done_callback(piece_task: Task):
            result: ActivePiece = piece_task.result()
            info: PieceInfo = result.piece_info
            data = self.file_handler.read_piece(info.index, 0, info.length).block
            if result.is_hash_ok(data):
                self._handle_completed_piece(result)
            else:
                self._handle_hash_error(result)
            self.piece_tasks.discard(piece_task)

        active_pieces_count = len(self.active_pieces)
        if active_pieces_count >= self.max_active_pieces:
            return
        pieces_to_create = min(self.max_active_pieces - active_pieces_count, len(self.file_handler.pending_pieces))
        for _ in range(pieces_to_create):
            piece_index = self._choose_pending_piece()
            if piece_index is None:
                continue
            piece_info = self.torrent_info.metadata.pieces_info[piece_index]
            new_active_piece = ActivePiece(piece_info, self.torrent_info.max_request_length)
            self.active_pieces.append(new_active_piece)
            new_piece_task = asyncio.create_task(
                    new_active_piece.join_queue(), name=f"ActivePiece {new_active_piece.piece_info.index}"
                )
            self.piece_tasks.add(new_piece_task)
            new_piece_task.add_done_callback(piece_done_callback)

    def _on_metadata_completion(self):
        print("Handling files...")
        self.file_handler.on_metadata_completion()
        print("Files OK")
        self.bitfield.update_from_completed_pieces(
            self.file_handler.completed_pieces, self.torrent_info.metadata.piece_count
        )
        self.max_active_pieces: int = (
            self.torrent_info.max_active_pieces
            if self.torrent_info.max_active_pieces
            else len(self.file_handler.pending_pieces)
        )

    async def start(self):
        """
        Begins trackers, creates and awaits on piece_tasks if any, enters simple seed mode if all pieces are complete
        """
        self._begin_trackers()

        print(f'Waiting for metadata')
        # await metadata completion

        print(f'Metadata OK')
        self._on_metadata_completion()
        print(f'Loaded: {len(self.file_handler.completed_pieces)} / {self.torrent_info.metadata.piece_count}')

        while not self._stop.is_set():
            if not self.peer_readiness_tasks:
                print("No peer readiness tasks...")
                await asyncio.sleep(1.0)
                continue

            self._update_active_pieces_and_piece_tasks()

            if not self.piece_tasks:
                print("No piece tasks...")
                await asyncio.sleep(1.0)
                continue

            ready, self.peer_readiness_tasks = await asyncio.wait(
                self.peer_readiness_tasks,
                return_when=asyncio.FIRST_COMPLETED,
                timeout=Timeouts.Progress
            )

            ready_peers: list[Peer] = [r.result() for r in ready]
            ready_peers.sort(reverse=True)

            print([peer.protocol.get_score_value() for peer in ready_peers])
            for peer in ready_peers:
                if not peer.protocol.alive():
                    continue
                for active_piece in self.active_pieces:
                    if not peer.protocol.has_piece(active_piece.piece_info.index):
                        continue
                    if not (active_request := ActiveRequest.from_active_piece(active_piece)):
                        continue
                    peer.protocol.perform_request(active_request, Timeouts.Request)
                    break
                if peer.protocol.alive():
                    self.peer_readiness_tasks.add(asyncio.create_task(peer.wait_till_ready_for_requests()))

    def stop(self):
        self._stop.set()

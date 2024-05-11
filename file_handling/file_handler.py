import os

from file_handling.file import File
from messages import Piece
from misc import utils
from torrent.metadata import Metadata


class FileHandler:
    """
    Class to handle files in torrent
    """
    def __init__(self, metadata: Metadata):
        self.metadata = metadata
        self.files: tuple[File, ...] = tuple()
        self.completed_pieces: list[int] = []
        self.pending_pieces: list[int] = []

    def on_metadata_completion(self):
        """
        Ensures that directories and files in torrent are created and have the correct length
        """
        files: list[File] = []
        for file in self.metadata.files_info:
            os.makedirs(os.path.dirname(file.path), exist_ok=True)
            if not os.path.exists(file.path):
                open(file.path, "x").close()
            f = open(file.path, "rb+")
            if os.path.getsize(file.path) != file.size:
                f.truncate(file.size)
                f.flush()
            f.seek(0)
            files.append(File(f, file))
        self.files = tuple(files)
        self._calculate_pending_and_completed_pieces()

    def _calculate_pending_and_completed_pieces(self):
        """
        Update the lists of pending and completed pieces
        """
        self.completed_pieces: list[int] = []
        try:
            file_index = 0
            for piece_info in self.metadata.pieces_info:
                bytes_left = piece_info.length
                data = b''
                while bytes_left:
                    tmp_data = self.files[file_index].io.read(bytes_left)
                    data += tmp_data
                    bytes_read = len(tmp_data)
                    if bytes_read != bytes_left:
                        file_index += 1
                    bytes_left -= bytes_read
                if utils.calculate_hash(data) == piece_info.hash_value:
                    self.completed_pieces.append(piece_info.index)
        except (Exception,):
            pass
        for file in self.files:
            file.io.seek(0)
        self.pending_pieces = list(set(range(self.metadata.piece_count)) - set(self.completed_pieces))

    def write_piece(self, index: int, begin: int, data: bytes) -> bool:
        """
        Writes a piece to the appropriate torrent files
        """
        file_index, offset = self._byte_in_torrent_to_file_and_offset(
            index * self.metadata.piece_size + begin
        )
        if file_index is None or offset is None:
            return False

        bytes_left = len(data)
        start_byte = 0
        while bytes_left and file_index < len(self.files):
            self.files[file_index].io.seek(offset)

            bytes_to_write = min(bytes_left, self.files[file_index].info.size - offset)
            end_byte = start_byte + bytes_to_write

            written = self.files[file_index].io.write(data[start_byte:end_byte])
            if bytes_to_write != written:
                return False

            bytes_left -= written
            start_byte = end_byte
            file_index += 1
            offset = 0
        return True

    def _byte_in_torrent_to_file_and_offset(self, byte_in_torrent: int) -> tuple[int | None, int | None]:
        """
        It figures out which file and offset correspond to a byte in torrent
        """
        for i, file in enumerate(self.files):
            if file.info.start_byte_in_torrent <= byte_in_torrent <= file.info.end_byte_in_torrent:
                return i, byte_in_torrent - file.info.start_byte_in_torrent
        return None, None

    def read_piece(self, index: int, begin: int, length: int) -> Piece | None:
        """
        Reads the appropriate piece that can be used as a response to a request
        """
        file_index, offset = self._byte_in_torrent_to_file_and_offset(
            index * self.metadata.piece_size + begin
        )
        if file_index is None or offset is None:
            return None

        result: bytearray = bytearray()
        bytes_left = length
        while bytes_left and file_index < len(self.files):
            self.files[file_index].io.seek(offset)

            bytes_to_read = min(bytes_left, self.files[file_index].info.size - offset)
            bytes_read = self.files[file_index].io.read(bytes_to_read)
            if bytes_to_read != len(bytes_read):
                return None

            result.extend(bytes_read)

            bytes_left -= len(bytes_read)
            file_index += 1
            offset = 0
        return Piece(index, begin, bytes(result))

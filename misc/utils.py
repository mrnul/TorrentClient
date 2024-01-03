import hashlib
import os

import bencdec
from messages import Message, Choke, Unchoke, Interested, Notinterested, Have, Bitfield, Request, Piece, Cancel, \
    Unknown, Handshake, Terminate
from messages.ids import IDs
from piece_handling.piece_info import PieceInfo
from torrent.constants import *
from torrent.file import File
from torrent.torrent_info import TorrentInfo


def calculate_hash(data: bytes) -> bytes:
    return hashlib.sha1(data).digest()


def get_info_sha1_hash(decoded_torrent_data: dict) -> bytes:
    """
    Takes torrent dictionary as input and returns the sha1 hash bytes
    """
    info_encoded_data = bencdec.encode(decoded_torrent_data[INFO])
    return calculate_hash(info_encoded_data)


def load_torrent_file(file: str) -> dict:
    with open(file, mode='rb') as f:
        return bencdec.decode(f.read())


def load_torrent_pieces(torrent_decoded_data: dict, total_size: int) -> tuple[PieceInfo, ...]:
    remaining_size: int = total_size
    piece_info_list: list[PieceInfo] = []
    piece_length: int = torrent_decoded_data[INFO][PIECE_LENGTH]
    for p, i in enumerate(torrent_decoded_data[INFO][PIECES].hex(' ', 20).split(' ')):
        piece_info_list.append(
            PieceInfo(bytes.fromhex(i), p,
                      min(piece_length, remaining_size))
        )
        remaining_size -= piece_length
    return tuple(piece_info_list)


def get_trackers(torrent_decoded_data: dict) -> set[str]:
    trackers: set[str] = set()
    if ANNOUNCE in torrent_decoded_data:
        trackers |= {torrent_decoded_data[ANNOUNCE].decode()}
    if ANNOUNCE_LIST in torrent_decoded_data:
        trackers |= {tracker[0].decode() for tracker in torrent_decoded_data[ANNOUNCE_LIST]}
    return trackers


def ensure_and_get_torrent_files(torrent_decoded_data: dict) -> tuple[File, ...]:
    illegal_path_chars = '/|\\:?*<>\"'
    files: list[File] = []
    root_dir = f'./{torrent_decoded_data[INFO][NAME].decode()}'
    if len(root_dir) == 0:
        root_dir = '.'
    for file in torrent_decoded_data[INFO][FILES]:
        path = '/'.join([p.decode() for p in file[PATH]])
        path = ''.join(map(lambda x: '_' if x in illegal_path_chars else x, path))
        path = f"{root_dir}/{path}"
        size = int(file[LENGTH])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            open(path, 'x').close()
        f = open(path, "rb+")
        if os.path.getsize(path) != size:
            f.truncate(size)
            f.flush()
        f.seek(0)
        files.append(File(f, size))
    return tuple(files)


def get_completed_pieces(torrent_info: TorrentInfo) -> list[int]:
    result = []
    try:
        file_index = 0
        for piece_info in torrent_info.pieces_info:
            bytes_left = piece_info.length
            data = b''
            while bytes_left:
                tmp_data = torrent_info.torrent_files[file_index].file.read(bytes_left)
                data += tmp_data
                bytes_read = len(tmp_data)
                if bytes_read != bytes_left:
                    file_index += 1
                bytes_left -= bytes_read
            if calculate_hash(data) == piece_info.hash_value:
                result.append(piece_info.index)
    except (Exception,):
        pass
    for file in torrent_info.torrent_files:
        file.file.seek(0)
    return result


def get_torrent_total_size(files: tuple[File, ...]) -> int:
    return sum([file.size for file in files])


def get_byte_bit_pair(bit_num: int) -> tuple[int, int]:
    byte_index = bit_num // 8
    bit_num_in_byte = 7 - bit_num % 8
    return byte_index, bit_num_in_byte


def get_bit_value(bits: bytearray, bit_num: int) -> int:
    byte_index, bit_num_in_byte = get_byte_bit_pair(bit_num)
    if byte_index >= len(bits):
        return 0
    return (bits[byte_index] >> bit_num_in_byte) & 1


def set_bit_value(bits: bytearray, bit_num: int, new_value: int):
    byte_index, bit_num_in_byte = get_byte_bit_pair(bit_num)
    if byte_index >= len(bits):
        return
    if new_value:
        bits[byte_index] |= (1 << bit_num_in_byte)
    else:
        bits[byte_index] &= ~(1 << bit_num_in_byte)


def get_file_and_byte_from_byte_in_torrent(piece_index: int, piece_size: int, byte_num: int,
                                           file_list: tuple[File, ...]) -> tuple[File, int] | None:
    offset_byte = 0
    byte_num_in_torrent = piece_index * piece_size + byte_num
    for i, file in enumerate(file_list):
        if not isinstance(file, File):
            continue
        first_file_byte = offset_byte
        last_file_byte = offset_byte + file.size
        if byte_num_in_torrent in range(first_file_byte, last_file_byte):
            return file, byte_num_in_torrent - first_file_byte
        offset_byte += file.size
    return None


def bytes_to_msg(msg_id: int, data: bytes) -> Message:
    match msg_id:
        case IDs.choke.value:
            return Choke()
        case IDs.unchoke.value:
            return Unchoke()
        case IDs.interested.value:
            return Interested()
        case IDs.not_interested.value:
            return Notinterested()
        case IDs.have.value:
            return Have(piece_index=int.from_bytes(data))
        case IDs.bitfield.value:
            return Bitfield(bitfield=data)
        case IDs.request.value:
            return Request(index=int.from_bytes(data[0:4]),
                           begin=int.from_bytes(data[4:8]),
                           length=int.from_bytes(data[8:12]))
        case IDs.piece.value:
            return Piece(index=int.from_bytes(data[0:4]),
                         begin=int.from_bytes(data[4:8]),
                         block=data[8:])
        case IDs.cancel.value:
            return Cancel(index=int.from_bytes(data[0:4]),
                          begin=int.from_bytes(data[4:8]),
                          length=int.from_bytes(data[8:13]))
        case _:
            return Unknown(msg_id, data)


def bytes_to_handshake(data: bytearray) -> Handshake | Terminate | None:
    if len(data) < 68:
        return None
    pstrlen = int.from_bytes(data[0:1])
    if pstrlen != 19:
        return Terminate(f'Handshake pstrlen is {pstrlen} but expected 19')
    pstr = data[1:20]
    if pstr != b'BitTorrent protocol':
        return Terminate(f'Handshake protocol is {pstr} but expected "BitTorrent protocol"')
    reserved = data[21:29]
    info_hash = data[29:49]
    peer_id = data[49:69]
    return Handshake(info_hash=info_hash,
                     peer_id=peer_id,
                     reserved=reserved,
                     pstr=pstr)

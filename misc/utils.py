import hashlib
import os
from typing import Literal, OrderedDict

import requests

import bencdec
from messages import *
from messages.ids import IDs
from piece_info.piece_info import PieceInfo
from torrent.constants import *
from torrent.file import File


def get_info_sha1_hash(torrent_data: dict) -> bytes:
    """
    Takes info dictionary as input and returns the sha1 hash bytes
    """
    info_encoded_data = bencdec.encode(torrent_data[INFO])
    return hashlib.sha1(info_encoded_data).digest()


def get_message_from_bytes(data: bytes, byteorder: Literal['little', 'big'] = 'big') -> Message:
    msg_len = int.from_bytes(data[0: 4])
    if msg_len == 0:
        return Keepalive()

    msg_id = int.from_bytes(data[4:5])
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
            return Have(piece_index=int.from_bytes(data[5:5], byteorder=byteorder))
        case IDs.bitfield.value:
            return Bitfield(bitfield=data[5:])
        case IDs.request.value:
            return Request(index=int.from_bytes(data[5:9], byteorder=byteorder),
                           begin=int.from_bytes(data[9:13], byteorder=byteorder),
                           length=int.from_bytes(data[13:17], byteorder=byteorder))
        case IDs.piece.value:
            return Piece(index=int.from_bytes(data[5:9], byteorder=byteorder),
                         begin=int.from_bytes(data[9:13], byteorder=byteorder),
                         block=data[13:])
        case IDs.cancel.value:
            return Cancel(index=int.from_bytes(data[5:9], byteorder=byteorder),
                          begin=int.from_bytes(data[9:13], byteorder=byteorder),
                          length=int.from_bytes(data[13:17], byteorder=byteorder))
        case _:
            return Unknown(msg_len, msg_id, data[5:])


def get_peer_data_from_tracker(tracker: str, info_hash: bytes, self_id: bytes, port: int) -> dict:
    peer_data = dict()
    if not tracker.startswith('http'):  # will handle non http(s) some other time
        return peer_data
    r = requests.get(tracker, params={
        'info_hash': info_hash,
        'peer_id': self_id,
        'port': port
    })
    response = bencdec.decode(r.content)
    for p in response[PEERS]:
        if not isinstance(p, OrderedDict):
            continue
        peer_id: bytes = p[PEER_ID]
        if peer_id in peer_data:
            continue

        peer_data[peer_id] = {
            IP: p[IP].decode(),
            PORT: p[PORT],
            PEER_ID: peer_id
        }
    return peer_data


def get_peer_data_from_trackers(trackers: set[str], info_hash: bytes, self_id: bytes, port: int) -> dict:
    peers = dict()
    for tracker in trackers:
        peers |= get_peer_data_from_tracker(tracker, info_hash, self_id, port)
    return peers


def load_torrent_file(file: str) -> dict:
    with open(file, mode='rb') as f:
        return bencdec.decode(f.read())


def parse_torrent_pieces(torrent_decoded_data: dict, total_size: int) -> list[PieceInfo]:
    remaining_size: int = total_size
    piece_info_list: list[PieceInfo] = []
    piece_length: int = torrent_decoded_data[INFO][PIECE_LENGTH]
    for p, i in enumerate(torrent_decoded_data[INFO][PIECES].hex(' ', 20).split(' ')):
        piece_info_list.append(
            PieceInfo(bytes.fromhex(i), p,
                      min(piece_length, remaining_size))
        )
        remaining_size -= piece_length
    return piece_info_list


def get_trackers(torrent_decoded_data: dict) -> set[str]:
    trackers: set[str] = set()
    if ANNOUNCE in torrent_decoded_data:
        trackers |= {torrent_decoded_data[ANNOUNCE].decode()}
    if ANNOUNCE_LIST in torrent_decoded_data:
        trackers |= {tracker[0].decode() for tracker in torrent_decoded_data[ANNOUNCE_LIST]}
    return trackers


def get_torrent_files(torrent_decoded_data: dict) -> list[File]:
    files: list[File] = []
    root_dir = torrent_decoded_data[INFO][NAME].decode()
    if len(root_dir) == 0:
        root_dir = '.'
    for file in torrent_decoded_data[INFO][FILES]:
        path = f"{root_dir}/{'/'.join([p.decode() for p in file[PATH]])}"
        size = int(file[LENGTH])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        file_already_created = os.path.exists(path)
        f = open(path, "wb")
        if not file_already_created:
            f.write(int(0).to_bytes(1) * size)
        files.append(File(f, size))
    return files


def get_torrent_total_size(files: list[File]) -> int:
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
                                           file_list: list[File]) -> tuple[int, int]:
    offset_byte = 0
    byte_num_in_torrent = piece_index * piece_size + byte_num
    for i, file in enumerate(file_list):
        if not isinstance(file, File):
            continue
        first_file_byte = offset_byte
        last_file_byte = offset_byte + file.size
        if byte_num_in_torrent in range(first_file_byte, last_file_byte):
            return i, byte_num_in_torrent - first_file_byte
        offset_byte += file.size
    return -1, -1

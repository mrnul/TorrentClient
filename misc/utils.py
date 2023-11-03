import hashlib
import os
from typing import Literal, OrderedDict

import requests

import bencdec
from messages import *
from torrent.constants import *
from torrent.file_info import FileInfo
from piece_info.piece_info import PieceInfo


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


def create_files(files: list[FileInfo]) -> bool:
    for file in files:
        try:
            os.makedirs(os.path.dirname(file.path), exist_ok=True)
            with open(file.path, "wb") as f:
                f.write(b'0' * file.size)
        except BaseExceptionGroup:
            return False
    return True


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


def get_torrent_pieces(torrent_decoded_data: dict) -> list[PieceInfo]:
    return [PieceInfo(bytes.fromhex(i), p, torrent_decoded_data[INFO][PIECE_LENGTH])
            for p, i in
            enumerate(torrent_decoded_data[INFO][PIECES].hex(' ', 20).split(' '))]


def get_trackers(torrent_decoded_data: dict) -> set[str]:
    trackers: set[str] = set()
    if ANNOUNCE in torrent_decoded_data:
        trackers |= {torrent_decoded_data[ANNOUNCE].decode()}
    if ANNOUNCE_LIST in torrent_decoded_data:
        trackers |= {tracker[0].decode() for tracker in torrent_decoded_data[ANNOUNCE_LIST]}
    return trackers


def get_torrent_files(torrent_decoded_data: dict) -> list[FileInfo]:
    files: list[FileInfo] = []
    root_dir = torrent_decoded_data[INFO][NAME].decode()
    if len(root_dir) == 0:
        root_dir = '.'
    for file in torrent_decoded_data[INFO][FILES]:
        f = f"{root_dir}/{'/'.join([p.decode() for p in file[PATH]])}"
        size = int(file[LENGTH])
        files.append(FileInfo(f, size))
    return files

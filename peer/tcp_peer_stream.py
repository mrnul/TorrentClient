import asyncio
from asyncio import StreamReader, StreamWriter

from file_handling.file_handler import FileHandler
from messages import Keepalive, Handshake, Message
from misc import utils
from peer.peer_info import PeerInfo
from peer.peer_base import PeerBase


# noinspection PyBroadException
class TcpPeerStream(PeerBase):
    def __init__(self, peer_info: PeerInfo, bitfield_len: int, file_handler: FileHandler):
        super().__init__(peer_info, bitfield_len, file_handler)
        self._reader: StreamReader | None = None
        self._writer: StreamWriter | None = None

    async def open_connection(self) -> bool:
        try:
            self._reader, self._writer = await asyncio.open_connection(
                self._peer_info.ip, self._peer_info.port
            )
        except Exception:
            return False
        return True

    async def read_handshake(self) -> Message | None:
        try:
            pstrlen = int.from_bytes(await self._reader.readexactly(1), byteorder="big")
            pstr = await self._reader.readexactly(pstrlen)
            reserved = await self._reader.readexactly(8)
            info_hash = await self._reader.readexactly(20)
            peer_id = await self._reader.readexactly(20)
            return Handshake(info_hash, peer_id, pstr, reserved)
        except Exception:
            return None

    async def read_message(self):
        try:
            msg_len = int.from_bytes(await self._reader.readexactly(4), byteorder="big")
            if msg_len == 0:
                return Keepalive()
            msg_id = int.from_bytes(await self._reader.readexactly(1), byteorder="big")
            msg_bytes = await self._reader.readexactly(msg_len - 1)
            msg = utils.mem_view_to_msg(msg_id, memoryview(msg_bytes))
            return msg
        except Exception as e:
            return None

    async def close_connection(self):
        if not self._writer:
            return
        if self._writer.is_closing():
            return
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except Exception as e:
            print(f"{self} - close - {e}")

    def alive(self):
        if not self._writer:
            return False
        return not self._writer.is_closing()

    def send_bytes(self, data: bytes) -> bool:
        if not self._writer:
            return False
        self._writer.write(data)
        return True

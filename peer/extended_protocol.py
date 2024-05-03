from typing import Any

import bencdec
from messages.extended import Extended


class Metadata:
    def __init__(self):
        self.uid: int | None = None
        self.size: int | None = None
        self.data: bytearray | None = bytearray()

    def _parse_handshake(self, decoded_data: dict):
        metadata_size = decoded_data.get(b'metadata_size')
        if metadata_size:
            self.size = metadata_size
        m: dict[bytes, int] = decoded_data.get(b'm')
        if not m:
            return
        for key, value in m.items():
            if b'metadata' in key:
                self.uid = value

    def _parse_metadata_response(self, metadata_response: bytes):
        pass

    def update_from_msg(self, msg: Extended):
        if msg.ext_id == 0:
            self._parse_handshake(bencdec.decode(msg.data)[0])
        elif msg.ext_id == ExtendedProtocol.METADATA_ID:
            self._parse_metadata_response(msg.data)


class ExtendedProtocol:
    HANDSHAKE_ID = 0
    METADATA_ID = 2

    def __init__(self):
        self.metadata: Metadata = Metadata()
        self.raw: dict[str, Any] = {}

    def parse_msg(self, msg: Extended):
        self.raw = bencdec.decode(msg.data)[0]
        self.metadata.update_from_msg(msg)

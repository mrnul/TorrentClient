from messages.message import Message


class Handshake(Message):
    def __init__(self, info_hash: bytes, peer_id: bytes,
                 pstr: bytes = b'BitTorrent protocol',
                 reserved: bytes = int(0).to_bytes(8)):
        super().__init__(49 + len(pstr), None)
        self.pstr: bytes = pstr
        self.pstrlen: int = len(self.pstr)
        self.reserved: bytes = reserved
        self.info_hash: bytes = info_hash
        self.peer_id: bytes = peer_id

    def to_bytes(self) -> bytes:
        return self.pstrlen.to_bytes(1) + self.pstr + self.reserved + self.info_hash + self.peer_id

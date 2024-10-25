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

    def from_bytes(self, data: bytearray):
        if len(data) < 68:
            return None
        self.pstrlen = int.from_bytes(data[:1], byteorder="big")
        if self.pstrlen != 19:
            raise ValueError(f'Handshake pstrlen is {self.pstrlen} but expected 19')
        self.pstr = data[1:20]
        if self.pstr != b'BitTorrent protocol':
            raise ValueError(f'Handshake protocol is {self.pstr} but expected "BitTorrent protocol"')
        self.reserved = data[21:29]
        self.info_hash = data[29:49]
        self.peer_id = data[49:69]
        return Handshake(
            info_hash=self.info_hash,
            peer_id=self.peer_id,
            reserved=self.reserved,
            pstr=self.pstr
        )

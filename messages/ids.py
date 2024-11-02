from enum import Enum


class IDs(Enum):
    choke = 0
    unchoke = 1
    interested = 2
    not_interested = 3
    have = 4
    bitfield = 5
    request = 6
    piece = 7
    cancel = 8
    extended = 20


class ExtIDs(Enum):
    handshake = 0
    metadata = 2


class ExtMetadataIDs(Enum):
    request = 0
    data = 1
    reject = 2


ALL_IDs = [uid.value for uid in IDs] + [uid.value for uid in ExtIDs]

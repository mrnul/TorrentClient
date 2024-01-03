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


ALL_IDs = [uid.value for uid in IDs]

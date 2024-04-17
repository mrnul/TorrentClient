import asyncio
from asyncio import Event


class StatusEvents:
    """
    Flags that hold the Peer status initialized to default values
    """
    def __init__(self):
        self.am_not_choked: Event = asyncio.Event()
        self.am_not_choking: Event = asyncio.Event()
        self.am_interested: Event = asyncio.Event()
        self.handshake: Event = asyncio.Event()
        self.am_interesting: Event = asyncio.Event()  # lol

    def ok_for_request(self) -> bool:
        return self.am_interested.is_set() and self.am_not_choked.is_set() and self.handshake.is_set()

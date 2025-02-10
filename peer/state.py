from asyncio import Event


class State:
    """
    Flags that hold the Peer state initialized to default values
    """
    def __init__(self):
        self.am_not_choked: Event = Event()
        self.am_not_choking: Event = Event()
        self.am_interested: Event = Event()
        self.handshake: Event = Event()
        self.am_interesting: Event = Event()  # lol
        self.dead: Event = Event()
        self.ready_for_requests: Event = Event()
        self.ready_or_dead: Event = Event()

    def set_dead(self):
        self.ready_for_requests.clear()
        self.dead.set()
        self.ready_or_dead.set()

    def set_ready(self):
        self.dead.clear()
        self.ready_for_requests.set()
        self.ready_or_dead.set()

    def clear_ready(self):
        self.dead.clear()
        self.ready_or_dead.clear()
        self.ready_for_requests.clear()

    def ok_for_request(self) -> bool:
        return (
                self.am_interested.is_set() and
                self.am_not_choked.is_set() and
                self.handshake.is_set()
        )

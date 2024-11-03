class StatusFlags:
    """
    Flags that hold the Peer status initialized to default values
    """
    def __init__(self):
        self.am_choked: bool = True
        self.am_choking: bool = True
        self.am_interested: bool = False
        self.handshake: bool = False
        self.am_interesting: bool = False  # lol

    def ok_for_request(self) -> bool:
        return self.am_interested and (not self.am_choked) and self.handshake

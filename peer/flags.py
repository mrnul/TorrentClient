import dataclasses


@dataclasses.dataclass
class Flags:
    """
    Flags that hold the Peer status initialized to default values
    """
    am_choked: bool = True
    am_choking: bool = True
    am_interested: bool = False
    am_interesting: bool = False  # lol

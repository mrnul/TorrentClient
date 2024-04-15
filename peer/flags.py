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

    def __repr__(self):
        return (f"am_choked: {self.am_choked} | "
                f"am_choking: {self.am_choking} | "
                f"am_interested: {self.am_interested} | "
                f"am_interesting: {self.am_interesting} | ")

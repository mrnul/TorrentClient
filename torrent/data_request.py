class DataRequest:
    def __init__(self, index: int, begin: int, length: int):
        self.index: int = index
        self.begin: int = begin
        self.length: int = length
        self.done: bool = False
        self.time_sent: float = 0.0

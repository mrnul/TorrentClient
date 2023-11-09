class PieceInfo:
    def __init__(self, hash_value: bytes, index: int, length: int):
        self.hash_value: bytes = hash_value
        self.index: int = index
        self.length: int = length

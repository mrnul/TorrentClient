class Message:
    def __init__(self, length: int | None, uid: int | None):
        self.len = length
        self.id = uid

    def to_bytes(self) -> bytes:
        raise NotImplementedError(f"to_bytes not implemented for msg id {self.id}")
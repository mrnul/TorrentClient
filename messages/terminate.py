from messages import Message


class Terminate(Message):
    def __init__(self, reason: str):
        super().__init__(0, None)
        self.reason: str = reason

    def to_bytes(self) -> bytes:
        return b''

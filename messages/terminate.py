from messages.message import Message


class Terminate(Message):
    def __init__(self):
        super().__init__(None, None)

    def to_bytes(self) -> bytes:
        return b''

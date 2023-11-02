class Message:
    def __init__(self, length: int | None, uid: int | None):
        self.len = length
        self.id = uid

    def __str__(self) -> str:
        members = [(attr, getattr(self, attr)) for attr in dir(self)
                   if not callable(getattr(self, attr)) and not attr.startswith("__")]
        return f'{type(self).__name__} - {members}'

    def to_bytes(self) -> bytes:
        raise NotImplementedError(f"to_bytes not implemented for msg id {self.id}")

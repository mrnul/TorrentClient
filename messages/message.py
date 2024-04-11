class Message:
    """
    Base class for all messages
    """
    def __init__(self, message_length: int | None, uid: int | None):
        self.message_length = message_length
        self.id = uid

    def __str__(self) -> str:
        members = [(attr, getattr(self, attr)) for attr in dir(self)
                   if not callable(getattr(self, attr))
                   and isinstance(getattr(self, attr), (int, str, float))
                   and not attr.startswith("__")]
        return f'{type(self).__name__} - {members}'

    def to_bytes(self) -> bytes:
        raise NotImplementedError(f"to_bytes not implemented for msg id {self.id}")

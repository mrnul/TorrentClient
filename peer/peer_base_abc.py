from messages import Handshake, Message


class PeerBaseABC:
    def alive(self) -> bool:
        """
        Method that returns True if connection is alive and false otherwise
        """
        raise NotImplementedError()

    async def open_connection(self) -> bool:
        """
        Method that creates peer connection
        """
        raise NotImplementedError()

    async def close_connection(self) -> bool:
        """
        Method that closes the connection
        """
        raise NotImplementedError()

    def send_bytes(self, data: bytes) -> bool:
        """
        Method to send raw bytes to peer
        """
        raise NotImplementedError()

    async def read_handshake(self) -> Handshake | None:
        """
        Method that reads and returns the handshake message or None if an error occurs
        """
        raise NotImplementedError()

    async def read_message(self) -> Message | None:
        """
        Method that reads and returns a Message or None if an error occurs
        """
        raise NotImplementedError()
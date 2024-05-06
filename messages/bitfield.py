import math
import struct

from messages import Message
from messages.ids import IDs


class Bitfield(Message):
    def __init__(self, bitfield: bytes = bytes()):
        super().__init__(1 + len(bitfield), IDs.bitfield.value)
        self.data: bytearray = bytearray(bitfield)

    def to_bytes(self) -> bytes:
        return struct.pack('>IB', self.message_length, self.uid) + self.data

    def update(self, completed_pieces: list[int], piece_count: int):
        self.data = bytearray(math.ceil(piece_count / 8))
        self.message_length = 1 + len(self.data)
        for piece in completed_pieces:
            self.set_bit_value(piece, True)

    @staticmethod
    def _get_byte_bit_pair(bit_num: int) -> tuple[int, int]:
        byte_index = bit_num // 8
        bit_num_in_byte = 7 - bit_num % 8
        return byte_index, bit_num_in_byte

    def get_bit_value(self, bit_num: int) -> int:
        byte_index, bit_num_in_byte = self._get_byte_bit_pair(bit_num)
        if byte_index >= len(self.data):
            return 0
        return (self.data[byte_index] >> bit_num_in_byte) & 1

    def set_bit_value(self, bit_num: int, new_value: bool):
        byte_index, bit_num_in_byte = self._get_byte_bit_pair(bit_num)
        if byte_index >= len(self.data):
            return
        if new_value:
            self.data[byte_index] |= (1 << bit_num_in_byte)
        else:
            self.data[byte_index] &= ~(1 << bit_num_in_byte)

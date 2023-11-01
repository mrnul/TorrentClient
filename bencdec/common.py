from enum import Enum

LIST_START = b'l'[0]
DICT_START = b'd'[0]
INT_START = b'i'[0]
ELEMENT_END = b'e'[0]
STRING_DELIMITER = b':'[0]


class ElementType(Enum):
    STR = 0
    INT = 1
    LIST = 2
    DICT = 3
    END = 4

from typing import Any

from . import common
from .constants import *


def _get_element_type(element: Any) -> common.ElementType:
    """
    Returns the bencoded type of the element
    """
    if isinstance(element, list):
        return common.ElementType.LIST
    if isinstance(element, dict):
        return common.ElementType.DICT
    if isinstance(element, int):
        return common.ElementType.INT
    if isinstance(element, bytes):
        return common.ElementType.STR
    return type(element)


def _encode_list(element: list) -> bytes:
    """
    :return: bencoded bytes representing the list element
    """
    result = LIST_START.to_bytes()
    for item in element:
        result += _encode_element(item)
    result += ELEMENT_END.to_bytes()
    return result


def _encode_dict(element: dict[str, object]) -> bytes:
    """
    :return: bencoded bytes representing the dict element
    """
    result = DICT_START.to_bytes()
    for key in element:
        value = element[key]
        result += _encode_element(key)
        result += _encode_element(value)
    result += ELEMENT_END.to_bytes()
    return result


def _encode_int(element: int) -> bytes:
    """
    :return: bencoded bytes representing the int element
    """
    result = INT_START.to_bytes()
    result += str(element).encode()
    result += ELEMENT_END.to_bytes()
    return result


def _encode_bytes(element: bytes) -> bytes:
    """
    :return: bencoded bytes representing the bytes element
    """
    result = str(len(element)).encode()
    result += STRING_DELIMITER.to_bytes()
    result += element
    return result


def _encode_element(element: Any) -> bytes:
    """
    :return: bencoded bytes representing the element
    """
    result = bytes()
    element_type = _get_element_type(element)
    match element_type:
        case common.ElementType.LIST:
            result += _encode_list(element)
        case common.ElementType.DICT:
            result += _encode_dict(element)
        case common.ElementType.INT:
            result += _encode_int(element)
        case common.ElementType.STR:
            result += _encode_bytes(element)
        case _:
            raise TypeError(f"Unsupported type {element_type}")
    return result


def encode(data: Any) -> bytes:
    """
    :return: bencoded bytes representing the data
    """
    return _encode_element(data)

from collections import OrderedDict

from . import common


def _get_element_type_at_index(data: bytes, index: int) -> common.ElementType:
    """
    Returns the type of the element that starts at position <index> in data
    """
    if data[index] == common.LIST_START:
        return common.ElementType.LIST
    if data[index] == common.DICT_START:
        return common.ElementType.DICT
    if data[index] == common.INT_START:
        return common.ElementType.INT
    if data[index] == common.ELEMENT_END:
        return common.ElementType.END
    return common.ElementType.STR


def _decode_str(data: bytes, index: int = 0) -> tuple[str | bytes | None, int]:
    """
    Extract the string value that starts at <index> in data

    Will try to decode string, if decode fails
    it will return data as hex string in groups of 20
    separated by white spaces

    :return: (The decoded string | hex values as string, next index to be parsed)
    """
    num_end = data.find(common.STRING_DELIMITER, index)
    if num_end == -1:
        raise ValueError(f"Could not find string delimiter at {index}")
    try:
        length = int(data[index:num_end:])
    except ValueError:
        raise ValueError(f"Unexpected non int value for string length at {index}")
    start_index = num_end + 1
    end_index = start_index + length
    try:
        result = data[start_index:end_index].decode()
    except UnicodeDecodeError:
        result = data[start_index:end_index].hex(' ', 20)
    return result, end_index


def _decode_int(data: bytes, index: int = 0) -> tuple[int | None, int]:
    """
    Extract the int value that starts at <index> in data

    :return: (int value, next index to be parsed)
    """
    num_end = data.find(common.ELEMENT_END, index)
    if num_end == -1:
        raise ValueError(f"Could not find ending element for number at {index}")
    try:
        result = int(data[index + 1:num_end])
    except ValueError:
        raise ValueError(f"Unexpected non int value at {index + 1}")
    return result, num_end + 1


def _decode_list(data: bytes, index: int = 0) -> tuple[list, int]:
    """
    Extract list that starts at <index> in data

    :return: (list, next index to be parsed)
    """
    result = []
    i = index + 1
    while True:
        element, i = _get_element(data, i)
        if element is None:
            break
        result.append(element)
    return result, i + 1


def _decode_dict(data: bytes, index: int = 0) -> tuple[dict, int]:
    """
    Extract dict that starts at <index> in data

    :return: (dict, next index to be parsed)
    """
    result = OrderedDict()
    i = index + 1
    while True:
        element_type = _get_element_type_at_index(data, i)
        if element_type == common.ElementType.END:
            break
        if element_type != common.ElementType.STR:
            raise ValueError(f"Expected string key but found {element_type.name}")
        key, i = _decode_str(data, i)
        element, i = _get_element(data, i)
        if element is None:
            break
        result[key] = element
    return result, i + 1


def _get_element(data: bytes, index: int) -> tuple[list | dict | int | str | None, int]:
    """
    Extract element at <index> in data. Expects to find a list, dict, int or string

    If no known type is found an exception is raised

    :return: (element, next index to be parsed)
    """
    element_type = _get_element_type_at_index(data, index)
    match element_type:
        case common.ElementType.LIST:
            value, new_index = _decode_list(data, index)
        case common.ElementType.DICT:
            value, new_index = _decode_dict(data, index)
        case common.ElementType.INT:
            value, new_index = _decode_int(data, index)
        case common.ElementType.STR:
            value, new_index = _decode_str(data, index)
        case common.ElementType.END:
            value, new_index = None, index
        case _:
            raise ValueError(f"Unexpected element type found {element_type}")
    return value, new_index


def decode(data: bytes | str) -> dict | list | str | None:
    """
    Decodes bencoded data
    """
    if isinstance(data, str):
        data = data.encode()
    root_element_type = _get_element_type_at_index(data, 0)
    match root_element_type:
        case common.ElementType.LIST:
            return _decode_list(data)[0]
        case common.ElementType.DICT:
            return _decode_dict(data)[0]
        case common.ElementType.INT:
            return _decode_int(data)[0]
        case common.ElementType.STR:
            return _decode_str(data)[0]

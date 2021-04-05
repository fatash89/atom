from __future__ import annotations

import builtins
from enum import Enum
from typing import Optional

import numpy as np
import pyarrow as pa
from msgpack import packb, unpackb  # type: ignore
from typing_extensions import Literal

SerializationMethod = Literal["msgpack", "arrow", "none"]


class GenericSerializationMethod:
    """
    Class containing generic functions for serialization methods (no
    serialization). Parent class for all serialization method classes.
    """

    @classmethod
    def serialize(cls, data):
        return data

    @classmethod
    def deserialize(cls, data):
        return data


class Msgpack(GenericSerializationMethod):
    """
    Class containing msgpack serialization and deserialization functions.
    """

    @classmethod
    def serialize(cls, data):
        return packb(data, use_bin_type=True)

    @classmethod
    def deserialize(cls, data):
        return unpackb(data, raw=False)


class Arrow(GenericSerializationMethod):
    """
    Class containing Apache Arrow serialization and deserialization functions.
    """

    @classmethod
    def _type_check(cls, data):
        """
        Check that data is serializeable by pyarrow. Specifically check that
        data is a built-in Python type, numpy array, or a built-in container of
        those. Only lists, tuples, and dict container types are supported.
        Raises error if data is not serializeable by pyarrow. Note that pyarrow
        supports pickling of arbitary objects, but the intent of this function
        is to forbid pickling altogether in order to maximize interoperability
        with non-Python code.
        """
        if isinstance(data, dict):
            for item in data.items():
                cls._type_check(item)
        elif isinstance(data, list) or isinstance(data, tuple):
            for item in data:
                cls._type_check(item)
        else:
            if (
                not hasattr(builtins, type(data).__name__)
                and not isinstance(data, np.ndarray)
                or isinstance(data, type(lambda: ()))
                or isinstance(data, type)
            ):
                raise TypeError(
                    f"Data is type {type(data).__name__}, which is not serializeable by pyarrow without "
                    "pickling; Change data type or choose a different serialization method."
                )

    @classmethod
    def serialize(cls, data):
        """
        Serializes data with Apache Arrow if data is a built-in Python type.
        Raises error if data is not a built-in Python type.
        """
        cls._type_check(data)
        return memoryview(pa.serialize(data).to_buffer())

    @classmethod
    def deserialize(cls, data):
        return pa.deserialize(data)


class Serializations(Enum):
    """
    Enum class that defines available serialization options.
    """

    msgpack = Msgpack
    arrow = Arrow
    none = GenericSerializationMethod

    @classmethod
    def print_values(cls):
        """
        Returns comma separated string of serialization options for pretty
        printing.
        """
        return ", ".join([v.name for v in cls])


def is_valid_serialization(method: Optional[str]) -> bool:
    """
    Checks serialization method string against available serialization options.
    Returns True/False if method is valid/invalid.
    """
    return (method in Serializations.__members__) or (method is None)


def serialize(data, method: Optional[SerializationMethod] = "none"):
    """
    Serializes data using the requested method, defaulting to "none".

    Args:
        data: The data to serialize.
        method: The serialization method to use; defaults to "none"

    Returns:
        The serialized data.

    Raises:
        ValueError if requested method is not in available serialization options
            defined by Serializations enum.
    """
    method = "none" if method is None else method

    if not is_valid_serialization(method):
        raise ValueError(
            f"Invalid serialization method. Must be one of {Serializations.print_values()}."
        )

    return Serializations[method].value.serialize(data)


def deserialize(data, method: Optional[SerializationMethod] = "msgpack"):
    """
    Deserializes data using the requested method, defaulting to "none".

    Args:
        data: The data to deserialize.
        method: The deserialization method to use; defaults to "none"

    Returns:
        The deserialized data.

    Raises:
        ValueError if requested method is not in available serialization options
            defined by Serializations enum.
    """
    method = "none" if method is None else method

    if not is_valid_serialization(method):
        raise ValueError(
            f"Invalid deserialization method {method}. Must be one of {Serializations.print_values()}."
        )

    return Serializations[method].value.deserialize(data)

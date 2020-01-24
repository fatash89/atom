from msgpack import packb, unpackb
import pyarrow as pa
from enum import Enum
import builtins


class GenericSerializationMethod():
    """
    Class containing generic functions for serialization methods (no serialization).
    Parent class for all serialization method classes.
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
    def serialize(cls, data):
        """
        Serializes data with Apache Arrow if data is a built-in Python type.
        Raises error if data is not a built-in Python type.
        """
        if not hasattr(builtins, type(data).__name__):
            raise TypeError(f"Data is type {type(data).__name__}, which is not a built-in Python type; Arrow will default "
                            "to pickle. Change data type or choose a different serialization method.")
        else:
            return memoryview(pa.serialize(data).to_buffer())

    @classmethod
    def deserialize(cls, data):
        return pa.deserialize(data)


class Serializations(Enum):
    """
    Enum class that defines available serialization options.
    """
    msgpack = Msgpack
    arrow   = Arrow
    none    = GenericSerializationMethod

    @classmethod
    def print_values(cls):
        """
        Returns comma separated string of serialization options for pretty printing.
        """
        return ", ".join([v.name for v in cls])


def is_valid_serialization(method):
    """
    Checks serialization method string against available serialization options.
    Returns True/False if method is valid/invalid.
    """
    return (method in Serializations.__members__)


def serialize(data, method="msgpack"):
    """
    Serializes data using the requested method, defaulting to msgpack.

    Args:
        data: The data to serialize.
        method (str, optional): The serialization method to use; defaults to msgpack
    Returns:
        The serialized data.
    Raises:
        ValueError if requested method is not in available serialization options defined
        by Serializations enum.
    """
    if not is_valid_serialization(method):
        raise ValueError(f'Invalid serialization method. Must be one of {Serializations.print_values()}.')

    return Serializations[method].value.serialize(data)


def deserialize(data, method="msgpack"):
    """
    Deserializes data using the requested method, defaulting to msgpack.

    Args:
        data: The data to deserialize.
        method (str, optional): The deserialization method to use; defaults to msgpack
    Returns:
        The deserialized data.
    Raises:
        ValueError if requested method is not in available serialization options defined
        by Serializations enum.
    """
    if not is_valid_serialization(method):
        raise ValueError(f'Invalid deserialization method {method}. Must be one of {Serializations.print_values()}.')

    return Serializations[method].value.deserialize(data)

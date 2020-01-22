from msgpack import packb, unpackb
import pyarrow as pa
from enum import Enum


class msgpack():
    """
    Class containing msgpack serialization and deserialization functions.
    """

    @classmethod
    def serialize(cls, data):
        return packb(data, use_bin_type=True)

    @classmethod
    def deserialize(cls, data):
        return unpackb(data, raw=False)


class arrow():
    """
    Class containing Apache Arrow serialization and deserialization functions.
    """

    @classmethod
    def serialize(cls, data):
        if type(data).__name__ not in dir(__builtins__):
            raise TypeError("Data is not a built-in Python type; Arrow will default to pickle."
                            "Change data type or choose a different serialization method.")
        else:
            return pa.serialize(data).to_buffer().to_pybytes()

    @classmethod
    def deserialize(cls, data):
        return pa.deserialize(data)


class Serializations(Enum):
    """
    Enum class that defines available serialization options.
    """
    msgpack = msgpack
    arrow   = arrow
    none    = None

    @classmethod
    def print_values(cls):
        """
        Returns comma separated string of serialization options for pretty printing.
        """
        return ", ".join([v.name for v in cls])


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
    if method not in Serializations.__members__:
        raise ValueError(f'Invalid serialization method. Must be one of {Serializations.print_values()}.')

    if Serializations[method].value:
        return Serializations[method].value.serialize(data)
    else:
        return data


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
    if method not in Serializations.__members__:
        raise ValueError(f'Invalid deserialization method {method}. Must be one of {Serializations.print_values()}.')

    if Serializations[method].value:
        return Serializations[method].value.deserialize(data)
    else:
        return data

from msgpack import packb, unpackb
import pyarrow as pa


def serialize(data, method="msgpack"):
    """
    Serializes data using the requested method, defaulting to msgpack.

    Args:
        data: The data to serialize.
        method (str, optional): The serialization method to use; defaults to msgpack
    Returns:
        The serialized data.
    """
    if method == "msgpack":
        return packb(data, use_bin_type=True)
    elif method == "arrow":
        return pa.serialize(data).to_buffer()
    else:
        raise ValueError('Invalid serialization method requested')


def deserialize(data, method="msgpack"):
    """
    Deserializes data using the requested method, defaulting to msgpack.

    Args:
        data: The data to deserialize.
        method (str, optional): The deserialization method to use; defaults to msgpack
    Returns:
        The deserialized data.
    """
    if method == "msgpack":
        return unpackb(data, raw=False)
    elif method == "arrow":
        return pa.deserialize(data)
    else:
        raise ValueError('Invalid deserialization method requested')

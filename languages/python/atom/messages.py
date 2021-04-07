from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Optional, Union, cast, overload

import atom.serialization as atom_ser
from typing_extensions import Literal

CMD_RESERVED_KEYS = ("data", "cmd", "element", "ser")
RES_RESERVED_KEYS = ("data", "err_code", "err_str", "element", "cmd", "cmd_id", "ser")
# "ser" overwritten on write; "id" overwritten on read; "meta" maybe overwritten
ENTRY_RESERVED_KEYS = ("ser", "id", "meta")


@overload
def format_redis_py(data: None) -> Literal[""]:
    ...


@overload
def format_redis_py(data: dict[Any, Any]) -> dict[Any, Any]:
    ...


def format_redis_py(data: Any) -> Any:
    if data is None:
        return ""
    if type(data) is dict:
        output = {}
        for k, v in data.items():
            if v is None:
                output[k] = ""
            else:
                output[k] = v
        return output
    else:
        return data


class Cmd:
    def __init__(self, element: str, cmd: str, data):
        """
        Specifies the format of a command that an element sends to another.

        Args:
            element: The element from which the command came from.
            cmd: The name of the command to run on the element.
            data: The data to be passed into the element's command.
        """
        if not isinstance(element, str):
            raise TypeError("element must be a str")
        if not isinstance(cmd, str):
            raise TypeError("cmd must be a str")

        self.element = element
        self.cmd = cmd
        self.data = data


class Response:
    ser: atom_ser.SerializationMethod

    def __init__(
        self,
        data="",
        err_code: int = 0,
        err_str: str = "",
        serialization: Optional[atom_ser.SerializationMethod] = None,
        serialize: Optional[bool] = None,
    ):
        """
        Specifies the format of a response that an element returns from a
        command.

        Args:
            data: The data returned from the element's command.
            err_code: The error code if error, otherwise 0.
            err_str: The error message, if any.
            serialization: Method of serialization to use; defaults to None.

            Deprecated:
            serialize: Whether or not to serialize data using msgpack.
        """
        if not isinstance(err_code, int):
            raise TypeError("err_code must be an int")
        if not isinstance(err_str, str):
            raise TypeError("err_str must be a str")

        if serialize is not None:  # check for deprecated legacy mode
            serialization = "msgpack" if serialize else None

        self.data = atom_ser.serialize(data, method=serialization)
        self.ser = (
            cast(atom_ser.SerializationMethod, str(serialization))
            if serialization is not None
            else "none"
        )

        self.err_code = err_code
        self.err_str = err_str


class Entry:
    def __init__(self, field_data_map: dict[str, Any]):
        """
        Formats the data published on a stream from an element.

        Args:
            field_data_map: Dict where the keys are the names of the fields and
                the values are the data of the corresponding field.
        """
        for field, data in field_data_map.items():
            if not isinstance(field, str):
                raise TypeError(f"field {field} must be a str")
            setattr(self, field, data)


class Acknowledge:
    def __init__(self, element: str, cmd_id: bytes, timeout: int) -> None:
        """
        Formats the acknowledge that a element sends to a caller upon receiving
        a command.

        Args:
            element: The element from which this acknowledge comes from.
            cmd_id: The Redis ID of the command that generated this acknowledge.
            timeout: Time for the caller to wait for the command to finish.
        """
        if not isinstance(element, str):
            raise TypeError("element must be a str")
        if not isinstance(cmd_id, bytes):
            raise TypeError("cmd_id must be bytes")
        if not isinstance(timeout, int):
            raise TypeError("timeout must be an int")
        self.element = element
        self.cmd_id = cmd_id
        self.timeout = timeout


class StreamHandler:
    def __init__(self, element: str, stream: str, handler: Callable) -> None:
        """
        Formats the association with a stream and handler of the stream's data.

        Args:
            element: Name of the element that owns the stream of interest.
            stream: Name of the stream to listen to.
            handler: Function to call on the data received from the stream.
        """
        if not isinstance(element, str):
            raise TypeError("element must be a str")
        if not isinstance(stream, str):
            raise TypeError("stream must be a str")
        if not callable(handler):
            raise TypeError("handler must be a function")
        self.element = element
        self.stream = stream
        self.handler = handler


class LogLevel(Enum):
    """
    An enum for the Unix syslog severity levels.
    """

    EMERG = 0
    ALERT = 1
    CRIT = 2
    ERR = 3
    WARNING = 4
    NOTICE = 5
    INFO = 6
    DEBUG = 7


class Log:
    def __init__(
        self, element: str, host: str, level: Union[LogLevel, int], msg: str
    ) -> None:
        """
        Formats the log published on the element's log stream

        Args:
            element: Name of the element writing the log.
            level: Syslog severity level.
            msg: Message for log.
        """
        if not isinstance(element, str):
            raise TypeError("element must be a str")
        if not isinstance(host, str):
            raise TypeError("host must be a str")
        if not isinstance(level, LogLevel) and not isinstance(level, int):
            raise TypeError("level must be of type LogLevel or int")
        if not isinstance(msg, str):
            raise TypeError("message must be a str")
        if isinstance(level, LogLevel):
            self.level = level.value
        else:
            if level < 0 or level > 7:
                raise ValueError("level must be in range [0, 7]")
            self.level = level
        self.element = element
        self.host = host
        self.msg = msg

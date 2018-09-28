import time
from collections import namedtuple


class Cmd:
    def __init__(self, client, cmd, data):
        if not isinstance(client, str):
            raise TypeError("client must be a str")
        if not isinstance(cmd, str):
            raise TypeError("cmd must be a str")
        self.client = client
        self.cmd = cmd
        self.data = data


class Response:
    def __init__(self, data="", err_code=0, err_str=""):
        if not isinstance(err_code, int):
            raise TypeError("err_code must be an int")
        if not isinstance(err_str, str):
            raise TypeError("err_str must be a str")
        self.data = data
        self.err_code = err_code
        self.err_str = err_str

    def to_internal(self, skill, cmd, cmd_id):
        return InternalResponse(skill, cmd, cmd_id, self.err_code, self.err_str, self.data)


class InternalResponse(Response):
    def __init__(self, skill, cmd, cmd_id, err_code, err_str="", data=""):
        if not isinstance(skill, str):
            raise TypeError("skill must be a str")
        if not isinstance(cmd, str):
            raise TypeError("cmd must be a str")
        if not isinstance(cmd_id, bytes):
            raise TypeError("cmd_id must be bytes")
        self.skill = skill
        self.cmd = cmd
        self.cmd_id = cmd_id
        super().__init__(data, err_code, err_str)

    def to_response(self):
        return Response(self.data, self.err_code, self.err_str)


class Droplet:
    def __init__(self, field_data_map, timestamp=None):
        if timestamp is None:
            timestamp = str(time.time())
        if not isinstance(timestamp, str):
            raise TypeError("timestamp must be a str")
        self.timestamp = timestamp

        for field, data in field_data_map.items():
            if not isinstance(field, str):
                raise TypeError(f"field {field} must be a str")
            setattr(self, field, data)
            

class Acknowledge:
    def __init__(self, skill, cmd_id, timeout):
        if not isinstance(skill, str):
            raise TypeError("skill must be a str")
        if not isinstance(cmd_id, bytes):
            raise TypeError("cmd_id must be bytes")
        if not isinstance(timeout, int):
            raise TypeError("timeout must be an int")
        self.skill = skill
        self.cmd_id = cmd_id
        self.timeout = timeout


class StreamHandler:
    def __init__(self, skill, stream, handler):
        if not isinstance(skill, str):
            raise TypeError("skill must be a str")
        if not isinstance(stream, str):
            raise TypeError("stream must be a str")
        if not callable(handler):
            raise TypeError("handler must be a function")
        self.skill = skill
        self.stream = stream
        self.handler = handler

import time
from collections import namedtuple


class Cmd:
    def __init__(self, client, cmd, data):
        """
        Specifies the format of a command that a Client sends to a Skill.

        Args:
            client (str): The Client from which the command came from.
            cmd (str): The name of the command to run on the Skill.
            data: The data to be passed into the Skill's command.
        """
        if not isinstance(client, str):
            raise TypeError("client must be a str")
        if not isinstance(cmd, str):
            raise TypeError("cmd must be a str")
        self.client = client
        self.cmd = cmd
        self.data = data


class Response:
    def __init__(self, data="", err_code=0, err_str=""):
        """
        Specifies the format of a response that a Skill returns from a command.

        Args:
            data (optional): The data returned from the Skill's command.
            err_code (int, optional): The error code if error, otherwise 0.
            err_str (str, optional): The error message, if any.
        """
        if not isinstance(err_code, int):
            raise TypeError("err_code must be an int")
        if not isinstance(err_str, str):
            raise TypeError("err_str must be a str")
        self.data = data
        self.err_code = err_code
        self.err_str = err_str

    def to_internal(self, skill, cmd, cmd_id):
        """
        Converts a Response to an InternalResponse.

        Args:
            skill (str): The Skill from which the Response came from.
            cmd (str): The command of the Skill that was called.
            cmd_id (bytes): The Redis ID of the command that generated this response.

        Returns:
            InternalResponse
        """
        return InternalResponse(skill, cmd, cmd_id, self.err_code, self.err_str, self.data)


class InternalResponse(Response):
    def __init__(self, skill, cmd, cmd_id, err_code=0, err_str="", data=""):
        """
        Format of a Response when being sent through Redis.
        Only intended for internal usage as it contains extra data for logging.

        Args:
            skill (str): The Skill from which the Response came from.
            cmd (str): The command of the Skill that was called.
            cmd_id (bytes): The Redis ID of the command that generated this response.
            err_code (int, optional): The error code if error, otherwise 0.
            err_str (str, optional): The error message, if any.
            data (optional): The data returned from the Skill's command.
        """
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
        """
        Strips away the extra data of InternalResponse to create Response.
        """
        return Response(self.data, self.err_code, self.err_str)


class Droplet:
    def __init__(self, field_data_map, timestamp=None):
        """
        Formats the data published on a stream from a Skill.

        Args:
            field_data_map (dict): Dict where the keys are the names of the fields
                of the droplet and the values are the data of the corresponding field.
            timestamp (str, optional): Timestamp of when the data was created.
        """
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
        """
        Formats the acknowledge that a Skill sends to a Client upon receiving a command.

        Args:
            skill (str): The Skill from which this acknowledge comes from.
            cmd_id (bytes): The Redis ID of the command that generated this acknowledge.
            timeout (int): Time for the Client to wait for the command to finish.
        """
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
        """
        Formats the association with a Skill's stream and Client's handler of the stream's data.

        Args:
            skill (str): Name of the Skill that owns the stream of interest.
            stream (str): Name of the stream to listen to.
            handler (callable): Function to call on the data received from the stream.
        """
        if not isinstance(skill, str):
            raise TypeError("skill must be a str")
        if not isinstance(stream, str):
            raise TypeError("stream must be a str")
        if not callable(handler):
            raise TypeError("handler must be a function")
        self.skill = skill
        self.stream = stream
        self.handler = handler

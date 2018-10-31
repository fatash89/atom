import redis
from skills import Client
from skills.client import DEFAULT_REDIS_SOCKET, DEFAULT_REDIS_PORT
from skills.config import LANG, VERSION, ACK_TIMEOUT, RESPONSE_TIMEOUT, STREAM_LEN, MAX_BLOCK
from skills.config import SKILLS_COMMAND_UNSUPPORTED, SKILLS_CALLBACK_FAILED, SKILLS_USER_ERRORS_BEGIN
from skills.messages import Acknowledge, Droplet, Response


class Skill(Client):
    def __init__(self, name, host=None, port=DEFAULT_REDIS_PORT, socket_path=DEFAULT_REDIS_SOCKET):
        """
        A Skill contains all the functionality of a Client in addition to accepting commands,
        delivering responses to commands, and publishing droplets on streams.
        All Skills have a command and response stream with optional streams for publishing droplets.

        Args:
            name (str): The name of this Skill.
            host (str, optional): The ip address of the Redis server to connect to.
            port (int, optional): The port of the Redis server to connect to.
            socket_path (str, optional): Path to Redis Unix socket.
        """
        super().__init__(name, host, port, socket_path)
        self.handler_map = {}
        self.timeouts = {}
        self.streams = set()

        self._pipe.xadd(
            self._make_skill_id(self.name),
            maxlen=STREAM_LEN,
            **{"language": LANG, "version": VERSION})
        # Keep track of cmd_last_id to know last time the skill's command stream was read from
        self.cmd_last_id = self._pipe.execute()[-1].decode()

    def __del__(self):
        """
        Deletes all streams belonging to this Skill and
        removes all Clients and Skills with the same name.
        """
        for stream in self.streams.copy():
            self.clean_up_stream(stream)
        super().__del__()

    def clean_up_stream(self, stream):
        """
        Deletes the specified stream.

        Args:
            stream (string): The stream to delete.
        """
        if stream not in self.streams:
            raise Exception(f"Stream {stream} does not exist!")
        self._rclient.delete(self._make_stream_id(self.name, stream))
        self.streams.remove(stream)

    def add_command(self, name, handler, timeout=RESPONSE_TIMEOUT):
        """
        Adds a command to the Skill for a Client to call.

        Args:
            name (str): Name of the command.
            handler (callable): Function to call given the command name.
            timeout (int, optional): Time for the Client to wait for the command to finish.
        """
        if not callable(handler):
            raise TypeError("Passed in handler is not a function!")
        self.handler_map[name] = handler
        self.timeouts[name] = timeout

    def run_command_loop(self):
        """
        Waits for command to be put in Skill's command stream.
        Sends acknowledge to client and then runs command.
        Returns response with processed data to client.
        """
        while True:
            # Get oldest new command from skill's command stream
            stream = {self._make_skill_id(self.name): self.cmd_last_id}
            cmd_response = self._rclient.xread(block=MAX_BLOCK, count=1, **stream)
            if cmd_response is None:
                continue

            # Set the cmd_last_id to this command's id to keep track of our last read
            cmd_id, cmd = cmd_response[self._make_skill_id(self.name)][0]
            self.cmd_last_id = cmd_id

            client = cmd[b"client"].decode()
            cmd_name = cmd[b"cmd"].decode()
            data = cmd[b"data"].decode()

            if not client:
                print("No client name present in command!")
                continue

            # Send acknowledge to client
            if cmd_name not in self.timeouts.keys():
                timeout = RESPONSE_TIMEOUT
            else:
                timeout = self.timeouts[cmd_name]
            acknowledge = Acknowledge(self.name, cmd_id, timeout)
            self._pipe.xadd(self._make_client_id(client), **vars(acknowledge))
            self._pipe.execute()

            # Send response to client
            if cmd_name not in self.handler_map.keys():
                response = Response(
                    err_code=SKILLS_COMMAND_UNSUPPORTED,
                    err_str="Unsupported command.")
            else:
                try:
                    response = self.handler_map[cmd_name](data)
                    if not isinstance(response, Response):
                        raise TypeError(f"Return type of {cmd_name} is not of type Response")
                    # Add SKILLS_USER_ERRORS_BEGIN to err_code to map to skill error range
                    if response.err_code != 0:
                        response.err_code += SKILLS_USER_ERRORS_BEGIN
                except Exception as e:
                    response = Response(
                        err_code=SKILLS_CALLBACK_FAILED,
                        err_str=f"{str(type(e))} {str(e)}")

            response = response.to_internal(self.name, cmd_name, cmd_id)
            self._pipe.xadd(self._make_client_id(client), **vars(response))
            self._pipe.execute()

    def add_droplet(self, stream_name, field_data_map, timestamp=None, maxlen=STREAM_LEN):
        """
        Creates Skill's stream if it does not exist.
        Adds the fields and data to a Droplet and puts it in the Skill's stream.

        Args:
            stream_name (str): The stream to add the droplet to.
            field_data_map (dict): Dict which creates the Droplet. See messages.Droplet for more usage.
            timestamp (str, optional): Timestamp of when the data was created.
            maxlen (int, optional): The maximum number of droplets to keep in the stream.
        """
        self.streams.add(stream_name)
        droplet = Droplet(field_data_map, timestamp)
        self._pipe.xadd(
            self._make_stream_id(self.name, stream_name),
            maxlen=maxlen, **vars(droplet))
        self._pipe.execute()

import redis
from skills import Client
from skills.config import LANG, VERSION, ACK_TIMEOUT, RESPONSE_TIMEOUT, STREAM_LEN, SKILL_ERROR_OFFSET, MAX_BLOCK
from skills.messages import Acknowledge, Droplet, Response


class Skill(Client):
    def __init__(self, name, host="localhost", port=6379, db=0, socket_path="/tmp/redis.sock"):
        super().__init__(name, host, port, db, socket_path)
        self.handler_map = {}
        self.timeouts = {}
        self.streams = set()

        self._pipe.xadd(self._make_skill_id(self.name), maxlen=STREAM_LEN, **{"language": LANG, "version": VERSION})
        # Keep track of cmd_last_id to know last time the skill's command stream was read from
        self.cmd_last_id = self._pipe.execute()[-1].decode()

    def __del__(self):
        """
        Deletes all streams belonging to this skill and
        removes all clients and skills with the same name.
        """
        for stream in self.streams.copy():
            self.clean_up_stream(stream)
        super().__del__()

    def clean_up_stream(self, stream):
        if stream not in self.streams:
            raise Exception(f"Stream {stream} does not exist!")
        self._rclient.delete(self._make_stream_id(self.name, stream))
        self.streams.remove(stream)

    def add_command(self, name, handler, timeout=RESPONSE_TIMEOUT):
        if not callable(handler):
            raise TypeError("Passed in handler is not a function!")
        self.handler_map[name] = handler
        self.timeouts[name] = timeout

    def run_command_loop(self):
        """
        Waits for command to be added to skill's command stream.
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
                response = Response(err_code=6, err_msg="Unsupported command.")
            else:
                try:
                    response = self.handler_map[cmd_name](data)
                    if not isinstance(response, Response):
                        raise TypeError(f"Return type of {cmd_name} is not of type Response")
                    # Add SKILL_ERROR_OFFSET to err_code to map to skill error range
                    if response.err_code != 0:
                        response.err_code += SKILL_ERROR_OFFSET
                except Exception as e:
                    response = Response(err_code=7, err_msg=f"{str(type(e))} {str(e)}")

            response = response.to_internal(self.name, cmd_name, cmd_id)
            self._pipe.xadd(self._make_client_id(client), **vars(response))
            self._pipe.execute()

    def add_droplet(self, stream, field_data_map, timestamp=None, maxlen=STREAM_LEN):
        """
        Creates skill's stream if it does not exist.
        Adds the the data to a Droplet and adds it to the skill's stream.
        """
        self.streams.add(stream)
        droplet = Droplet(field_data_map, timestamp)
        self._pipe.xadd(self._make_stream_id(self.name, stream), maxlen=maxlen, **vars(droplet))
        self._pipe.execute()

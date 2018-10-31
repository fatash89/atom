import redis
from skills.config import LANG, VERSION, ACK_TIMEOUT, STREAM_LEN, MAX_BLOCK
from skills.config import SKILLS_COMMAND_NO_ACK, SKILLS_COMMAND_NO_RESPONSE
from skills.messages import Cmd, Response, StreamHandler

# Default redis socket and port
DEFAULT_REDIS_PORT = 6379
DEFAULT_REDIS_SOCKET = "/shared/redis.sock"

class Client:
    def __init__(self, name, host=None, port=DEFAULT_REDIS_PORT, socket_path=DEFAULT_REDIS_SOCKET):
        """
        A Client has the purpose of interacting with Skills by getting data from their streams
        or sending commands and receiving responses. All Clients have a response stream.

        Args:
            name (str): The name of this Client.
            host (str, optional): The ip address of the Redis server to connect to.
            port (int, optional): The port of the Redis server to connect to.
            socket_path (str, optional): Path to Redis Unix socket.
        """
        self.name = name
        if (host is not None):
            self._rclient = redis.StrictRedis(host=host, port=port)
        else:
            self._rclient = redis.StrictRedis(unix_socket_path=socket_path)
        self._pipe = self._rclient.pipeline()

        self._pipe.xadd(
            self._make_client_id(self.name),
            maxlen=STREAM_LEN,
            **{"language": LANG, "version": VERSION})
        # Keep track of response_last_id to know last time the client's response stream was read from
        self.response_last_id = self._pipe.execute()[-1].decode()

    def __repr__(self):
        return f"{self.__class__.__name__}({self.name})"

    def __del__(self):
        """
        Removes all Clients and Skills with the same name.
        """
        self._rclient.delete(self._make_client_id(self.name))
        self._rclient.delete(self._make_skill_id(self.name))

    def _make_client_id(self, client_name):
        """
        Creates the string representation for a Client's response stream id.

        Args:
            client_name (str): Name of the Client to generate the id for.
        """
        return f"client:{client_name}"

    def _make_skill_id(self, skill_name):
        """
        Creates the string representation for a Skill's command stream id.

        Args:
            skill_name (str): Name of the Skill to generate the id for.
        """
        return f"skill:{skill_name}"

    def _make_stream_id(self, skill_name, stream_name):
        """
        Creates the string representation of a Skill's stream id.

        Args:
            skill_name (str): Name of the Skill to generate the id for.
            stream_name (str): Name of skill_name's stream to generate the id for.
        """
        return f"stream:{skill_name}:{stream_name}"

    def _get_redis_timestamp(self):
        """
        Gets the current timestamp from Redis.
        """
        secs, msecs = self._rclient.time()
        timestamp = str(secs) + str(msecs)[:3]
        return timestamp

    def get_all_clients(self):
        """
        Gets the names of all the Clients connected to the Redis server.

        Returns:
            List of Client ids connected to the Redis server.
        """
        clients = self._rclient.keys(self._make_client_id("*"))
        return clients

    def get_all_skills(self):
        """
        Gets the names of all the Skills connected to the Redis server.

        Returns:
            List of Skill ids connected to the Redis server.
        """
        skills = self._rclient.keys(self._make_skill_id("*"))
        return skills

    def get_all_streams(self, skill_name="*"):
        """
        Gets the names of all the streams of the specified Skill (all by default).

        Args:
            skill_name (str): Name of the Skill of which to get the streams from.

        Returns:
            List of Stream ids belonging to skill_name
        """
        streams = self._rclient.keys(self._make_stream_id(skill_name, "*"))
        return streams

    def send_command(self, skill_name, cmd_name, data, block=True):
        """
        Sends command to skill and waits for acknowledge.
        When acknowledge is received, waits for timeout from acknowledge or until response is received.

        Args:
            skill_name (str): Name of the Skill to send the command to.
            cmd_name (str): Name of the command to execute of skill_name.
            data: Data to be passed to the function specified by cmd_name.
            block (bool): Wait for the response before returning from the function.

        Returns:
            messages.Response
        """
        # Send command to skill's command stream
        cmd = Cmd(self.name, cmd_name, data)
        self._pipe.xadd(self._make_skill_id(skill_name), maxlen=STREAM_LEN, **vars(cmd))
        cmd_id = self._pipe.execute()[-1].decode()
        timeout = None

        # Receive acknowledge from skill
        responses = self._rclient.xread(
            block=ACK_TIMEOUT,
            **{self._make_client_id(self.name): self.response_last_id})
        if responses is None:
            return vars(Response(
                err_code=SKILLS_COMMAND_NO_ACK,
                err_str="Did not receive acknowledge from skill."))
        for self.response_last_id, response in responses[self._make_client_id(self.name)]:
            if response[b"skill"].decode() == skill_name and \
            response[b"cmd_id"].decode() == cmd_id and b"timeout" in response:
                timeout = int(response[b"timeout"].decode())
                break

        if timeout is None:
            return vars(Response(
                err_code=SKILLS_COMMAND_NO_ACK,
                err_str="Did not receive acknowledge from skill."))

        # Receive response from skill
        responses = self._rclient.xread(
            block=timeout, **{self._make_client_id(self.name): self.response_last_id})
        if responses is None:
            return vars(Response(
                err_code=SKILLS_COMMAND_NO_RESPONSE,
                err_str="Did not receive response from skill."))
        for self.response_last_id, response in responses[self._make_client_id(self.name)]:
            if response[b"skill"].decode() == skill_name and \
            response[b"cmd_id"].decode() == cmd_id and b"data" in response:
                err_code = int(response[b"err_code"].decode())
                err_str = response[b"err_str"].decode()
                return vars(Response(data=response[b"data"], err_code=err_code, err_str=err_str))

        # Proper response was not in responses
        return vars(Response(
            err_code=SKILLS_COMMAND_NO_RESPONSE,
            err_str="Did not receive response from skill."))

    def listen_on_streams(self, stream_handlers, n_loops=None, timeout=MAX_BLOCK):
        """
        Listens to streams and pass any received data to corresponding handler.

        Args:
            stream_handlers (list of messages.StreamHandler):
            n_loops (int): Number of times to send the stream data to the handlers.
            timeout (int): How long to block on the stream. If surpassed, the function returns.
        """
        if n_loops is None:
            # Create an infinite loop
            n_loops = iter(int, 1)
        else:
            n_loops = range(n_loops)

        streams = {}
        stream_handler_map = {}
        for stream_handler in stream_handlers:
            if not isinstance(stream_handler, StreamHandler):
                raise TypeError(f"{stream_handler} is not a StreamHandler!")
            stream_id = self._make_stream_id(stream_handler.skill, stream_handler.stream)
            streams[stream_id] = self._get_redis_timestamp()
            stream_handler_map[stream_id] = stream_handler.handler
        for _ in n_loops:
            stream_droplets = self._rclient.xread(block=timeout, **streams)
            if stream_droplets is None:
                return
            for stream, droplets in stream_droplets.items():
                for uid, droplet in droplets:
                    streams[stream] = uid
                    stream_handler_map[stream](droplet)

    def get_n_most_recent(self, skill_name, stream_name, n):
        """
        Gets the n most recent droplets from the specified stream.

        Args:
            skill_name (str): Name of the Skill to get the droplets from.
            stream_name (str): Name of the stream to get the droplets from.
            n (int): Number of droplets to get.

        Returns:
            List of dicts containing the data of the droplets.
        """
        uid_droplets = self._rclient.xrevrange(
            self._make_stream_id(skill_name, stream_name), count=n)
        droplets = []
        # Convert the bytestring fields of the droplet to string
        for _, droplet in uid_droplets:
            for k in list(droplet.keys()).copy():
                k_str = k.decode()
                if k_str == "timestamp":
                    droplet[k_str] = droplet[k].decode()
                else:
                    droplet[k_str] = droplet[k]
                del droplet[k]
            droplets.append(droplet)
        return droplets

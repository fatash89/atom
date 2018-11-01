import redis
from atom.config import DEFAULT_REDIS_PORT, DEFAULT_REDIS_SOCKET
from atom.config import LANG, VERSION, ACK_TIMEOUT, RESPONSE_TIMEOUT, STREAM_LEN, MAX_BLOCK
from atom.config import ATOM_COMMAND_NO_ACK, ATOM_COMMAND_NO_RESPONSE
from atom.config import ATOM_COMMAND_UNSUPPORTED, ATOM_CALLBACK_FAILED, ATOM_USER_ERRORS_BEGIN
from atom.messages import Cmd, Response, StreamHandler
from atom.messages import Acknowledge, Entry, Response


class Element:
    def __init__(self, name, host=None, port=DEFAULT_REDIS_PORT, socket_path=DEFAULT_REDIS_SOCKET):
        """
        Args:
            name (str): The name of the element to register with Atom.
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
        self.handler_map = {}
        self.timeouts = {}
        self.streams = set()

        self._pipe.xadd(
            self._make_response_id(self.name),
            maxlen=STREAM_LEN,
            **{
                "language": LANG,
                "version": VERSION
            })
        # Keep track of response_last_id to know last time the client's response stream was read from
        self.response_last_id = self._pipe.execute()[-1].decode()

        self._pipe.xadd(
            self._make_command_id(self.name),
            maxlen=STREAM_LEN,
            **{
                "language": LANG,
                "version": VERSION
            })
        # Keep track of command_last_id to know last time the element's command stream was read from
        self.command_last_id = self._pipe.execute()[-1].decode()

    def __repr__(self):
        return f"{self.__class__.__name__}({self.name})"

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

    def __del__(self):
        """
        Removes all elements with the same name.
        """
        for stream in self.streams.copy():
            self.clean_up_stream(stream)
        self._rclient.delete(self._make_response_id(self.name))
        self._rclient.delete(self._make_command_id(self.name))

    def _make_response_id(self, element_name):
        """
        Creates the string representation for a element's response stream id.

        Args:
            element_name (str): Name of the element to generate the id for.
        """
        return f"response:{element_name}"

    def _make_command_id(self, element_name):
        """
        Creates the string representation for an element's command stream id.

        Args:
            element_name (str): Name of the element to generate the id for.
        """
        return f"command:{element_name}"

    def _make_stream_id(self, element_name, stream_name):
        """
        Creates the string representation of a element's stream id.

        Args:
            element_name (str): Name of the element to generate the id for.
            stream_name (str): Name of element_name's stream to generate the id for.
        """
        return f"stream:{element_name}:{stream_name}"

    def _get_redis_timestamp(self):
        """
        Gets the current timestamp from Redis.
        """
        secs, msecs = self._rclient.time()
        timestamp = str(secs) + str(msecs)[:3]
        return timestamp

    def get_all_elements(self):
        """
        Gets the names of all the elements connected to the Redis server.

        Returns:
            List of element ids connected to the Redis server.
        """
        elements = [
            element.decode().split(":")[-1]
            for element in self._rclient.keys(self._make_response_id("*"))
        ]
        return elements

    def get_all_streams(self, element_name="*"):
        """
        Gets the names of all the streams of the specified element (all by default).

        Args:
            element_name (str): Name of the element of which to get the streams from.

        Returns:
            List of Stream ids belonging to element_name
        """
        streams = [
            stream.decode()
            for stream in self._rclient.keys(self._make_stream_id(element_name, "*"))
        ]
        return streams

    def command_add(self, name, handler, timeout=RESPONSE_TIMEOUT):
        """
        Adds a command to the element for another element to call.

        Args:
            name (str): Name of the command.
            handler (callable): Function to call given the command name.
            timeout (int, optional): Time for the caller to wait for the command to finish.
        """
        if not callable(handler):
            raise TypeError("Passed in handler is not a function!")
        self.handler_map[name] = handler
        self.timeouts[name] = timeout

    def command_loop(self):
        """
        Waits for command to be put in element's command stream.
        Sends acknowledge to caller and then runs command.
        Returns response with processed data to caller.
        """
        while True:
            # Get oldest new command from element's command stream
            stream = {self._make_command_id(self.name): self.command_last_id}
            cmd_response = self._rclient.xread(block=MAX_BLOCK, count=1, **stream)
            if cmd_response is None:
                continue

            # Set the command_last_id to this command's id to keep track of our last read
            cmd_id, cmd = cmd_response[self._make_command_id(self.name)][0]
            self.command_last_id = cmd_id

            caller = cmd[b"element"].decode()
            cmd_name = cmd[b"cmd"].decode()
            data = cmd[b"data"]

            if not caller:
                print("No caller name present in command!")
                continue

            # Send acknowledge to caller
            if cmd_name not in self.timeouts.keys():
                timeout = RESPONSE_TIMEOUT
            else:
                timeout = self.timeouts[cmd_name]
            acknowledge = Acknowledge(self.name, cmd_id, timeout)
            self._pipe.xadd(self._make_response_id(caller), **vars(acknowledge))
            self._pipe.execute()

            # Send response to caller
            if cmd_name not in self.handler_map.keys():
                response = Response(
                    err_code=ATOM_COMMAND_UNSUPPORTED, err_str="Unsupported command.")
            else:
                try:
                    response = self.handler_map[cmd_name](data)
                    if not isinstance(response, Response):
                        raise TypeError(f"Return type of {cmd_name} is not of type Response")
                    # Add ATOM_USER_ERRORS_BEGIN to err_code to map to element error range
                    if response.err_code != 0:
                        response.err_code += ATOM_USER_ERRORS_BEGIN
                except Exception as e:
                    response = Response(
                        err_code=ATOM_CALLBACK_FAILED, err_str=f"{str(type(e))} {str(e)}")

            response = response.to_internal(self.name, cmd_name, cmd_id)
            self._pipe.xadd(self._make_response_id(caller), **vars(response))
            self._pipe.execute()

    def command_send(self, element_name, cmd_name, data, block=True):
        """
        Sends command to element and waits for acknowledge.
        When acknowledge is received, waits for timeout from acknowledge or until response is received.

        Args:
            element_name (str): Name of the element to send the command to.
            cmd_name (str): Name of the command to execute of element_name.
            data: Entry to be passed to the function specified by cmd_name.
            block (bool): Wait for the response before returning from the function.

        Returns:
            messages.Response
        """
        # Send command to element's command stream
        cmd = Cmd(self.name, cmd_name, data)
        self._pipe.xadd(self._make_command_id(element_name), maxlen=STREAM_LEN, **vars(cmd))
        cmd_id = self._pipe.execute()[-1].decode()
        timeout = None

        # Receive acknowledge from element
        responses = self._rclient.xread(
            block=ACK_TIMEOUT, **{self._make_response_id(self.name): self.response_last_id})
        if responses is None:
            return vars(
                Response(
                    err_code=ATOM_COMMAND_NO_ACK,
                    err_str="Did not receive acknowledge from element."))
        for self.response_last_id, response in responses[self._make_response_id(self.name)]:
            if response[b"element"].decode() == element_name and \
            response[b"cmd_id"].decode() == cmd_id and b"timeout" in response:
                timeout = int(response[b"timeout"].decode())
                break

        if timeout is None:
            return vars(
                Response(
                    err_code=ATOM_COMMAND_NO_ACK,
                    err_str="Did not receive acknowledge from element."))

        # Receive response from element
        responses = self._rclient.xread(
            block=timeout, **{self._make_response_id(self.name): self.response_last_id})
        if responses is None:
            return vars(
                Response(
                    err_code=ATOM_COMMAND_NO_RESPONSE,
                    err_str="Did not receive response from element."))
        for self.response_last_id, response in responses[self._make_response_id(self.name)]:
            if response[b"element"].decode() == element_name and \
            response[b"cmd_id"].decode() == cmd_id and b"data" in response:
                err_code = int(response[b"err_code"].decode())
                err_str = response[b"err_str"].decode()
                return vars(Response(data=response[b"data"], err_code=err_code, err_str=err_str))

        # Proper response was not in responses
        return vars(
            Response(
                err_code=ATOM_COMMAND_NO_RESPONSE,
                err_str="Did not receive response from element."))

    def entry_read_loop(self, stream_handlers, n_loops=None, timeout=MAX_BLOCK):
        """
        Listens to streams and pass any received entry to corresponding handler.

        Args:
            stream_handlers (list of messages.StreamHandler):
            n_loops (int): Number of times to send the stream entry to the handlers.
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
            stream_id = self._make_stream_id(stream_handler.element, stream_handler.stream)
            streams[stream_id] = self._get_redis_timestamp()
            stream_handler_map[stream_id] = stream_handler.handler
        for _ in n_loops:
            stream_entries = self._rclient.xread(block=timeout, **streams)
            if stream_entries is None:
                return
            for stream, entries in stream_entries.items():
                for uid, entry in entries:
                    streams[stream] = uid
                    stream_handler_map[stream](entry)

    def entry_read_n(self, element_name, stream_name, n):
        """
        Gets the n most recent entries from the specified stream.

        Args:
            element_name (str): Name of the element to get the entry from.
            stream_name (str): Name of the stream to get the entry from.
            n (int): Number of entries to get.

        Returns:
            List of dicts containing the data of the entries
        """
        uid_entries = self._rclient.xrevrange(
            self._make_stream_id(element_name, stream_name), count=n)
        entries = []
        # Convert the bytestring fields of the entry to string
        for _, entry in uid_entries:
            for k in list(entry.keys()).copy():
                k_str = k.decode()
                if k_str == "timestamp":
                    entry[k_str] = entry[k].decode()
                else:
                    entry[k_str] = entry[k]
                del entry[k]
            entries.append(entry)
        return entries

    def entry_write(self, stream_name, field_data_map, timestamp=None, maxlen=STREAM_LEN):
        """
        Creates element's stream if it does not exist.
        Adds the fields and data to a Entry and puts it in the element's stream.

        Args:
            stream_name (str): The stream to add the data to.
            field_data_map (dict): Dict which creates the Entry. See messages.Entry for more usage.
            timestamp (str, optional): Timestamp of when the data was created.
            maxlen (int, optional): The maximum number of data to keep in the stream.
        """
        self.streams.add(stream_name)
        entry = Entry(field_data_map, timestamp)
        self._pipe.xadd(
            self._make_stream_id(self.name, stream_name), maxlen=maxlen, **vars(entry))
        self._pipe.execute()

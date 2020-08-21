import copy
from multiprocessing import Process
import multiprocessing
from traceback import format_exc
import threading
import time
import uuid
import os
from os import uname
from queue import Queue, LifoQueue
from queue import Empty as QueueEmpty
from collections import defaultdict

import redis
from redistimeseries.client import Client as RedisTimeSeries

from atom.config import DEFAULT_REDIS_PORT, DEFAULT_METRICS_PORT, DEFAULT_REDIS_SOCKET, DEFAULT_METRICS_SOCKET, HEALTHCHECK_RETRY_INTERVAL
from atom.config import LANG, VERSION, ACK_TIMEOUT, RESPONSE_TIMEOUT, STREAM_LEN, MAX_BLOCK
from atom.config import ATOM_NO_ERROR, ATOM_COMMAND_NO_ACK, ATOM_COMMAND_NO_RESPONSE
from atom.config import ATOM_COMMAND_UNSUPPORTED, ATOM_CALLBACK_FAILED, ATOM_USER_ERRORS_BEGIN, ATOM_INTERNAL_ERROR
from atom.config import HEALTHCHECK_COMMAND, VERSION_COMMAND, REDIS_PIPELINE_POOL_SIZE, COMMAND_LIST_COMMAND
from atom.config import METRICS_ELEMENT_LABEL
from atom.messages import Cmd, Response, StreamHandler, format_redis_py
from atom.messages import Acknowledge, Entry, Log, LogLevel, ENTRY_RESERVED_KEYS
import atom.serialization as ser

# Reserved commands
RESERVED_COMMANDS = [
    COMMAND_LIST_COMMAND,
    VERSION_COMMAND,
    HEALTHCHECK_COMMAND
]

# Reserved metrics labels
RESERVED_METRICS_LABELS = [
    METRICS_ELEMENT_LABEL
]

# Metrics default retention -- 1 day on raw data
METRICS_DEFAULT_RETENTION = 86400000
# Metrics default aggregation rules
METRICS_DEFAULT_AGG_RULES = [
    # Keep data in 10m buckets for 3 days
    ("10m", 600000,  259200000),
    # Then keep data in 1h buckets for 30 days
    ("01h", 3600000, 2592000000),
    # Then keep data in 1d buckets for 365 days
    ("24h", 86400000, 31536000000),
]

class ElementConnectionTimeoutError(redis.exceptions.TimeoutError):
    pass

class AtomError(Exception):
    def __init__(self, *args):
        if args:
            self.message = args[0]
        else:
            self.message = None

    def __str__(self):
        if self.message:
            return f"Atom Error: {self.message}"
        else:
            return "An Atom Error Occurred"

class MetricsPipeline():
    def __init__(self, element):
        self.element = element
    def __enter__(self):
        self.pipeline = self.element.metrics_get_pipeline()
        return self.pipeline
    def __exit__(self, type, value, traceback):
        self.element.metrics_write_pipeline(self.pipeline)

class Element:
    def __init__(self, name, host=None, port=DEFAULT_REDIS_PORT, metrics_host=None, metrics_port=DEFAULT_METRICS_PORT,
                 socket_path=DEFAULT_REDIS_SOCKET, metrics_socket_path=DEFAULT_METRICS_SOCKET, conn_timeout_ms=30000, data_timeout_ms=5000, enforce_metrics=False):
        """
        Args:
            name (str): The name of the element to register with Atom.
            host (str, optional): The ip address of the Redis server to connect to.
            port (int, optional): The port of the Redis server to connect to.
            socket_path (str, optional): Path to Redis Unix socket.
            metrics_host (str, optional): The ip address of the metrics Redis server to connect to.
            metrics_port (int, optional): The port of the metrics Redis server to connect to.
            metrics_socket_path (str, optional): Path to metrics Redis Unix socket.
            enforce_metrics (bool, optional): While metrics is a relatively new feature
                this will allow an element to connect to a nucleus without metrics
                and fail with a log but not throw an error. This enables us to be backwards
                compatible with older setups.
            conn_timeout_ms (int, optional): The number of milliseconds to wait
                                             before timing out when establishing
                                             a Redis connection
            data_timeout_ms (int, optional): The number of milliseconds to wait
                                             before timing out while waiting for
                                             data back over a Redis connection.
        """

        self.name = name
        self.host = uname().nodename
        self.handler_map = {}
        self.timeouts = {}
        self._redis_connection_timeout = float(conn_timeout_ms / 1000.)
        self._redis_data_timeout = float(data_timeout_ms / 1000.)
        assert self._redis_connection_timeout > 0, \
            "timeout must be positive and non-zero"
        self.streams = set()
        self._rclient = None
        self._command_loop_shutdown = multiprocessing.Event()
        self._rpipeline_pool = Queue()
        self._mpipeline_pool = LifoQueue()
        self._timed_out = False
        self._pid = os.getpid()
        self._cleaned_up = False
        self.processes = []
        self._redis_connected = False

        #
        # Set up metrics
        #
        self._metrics_enabled = False
        self._metric_timing = {}
        self._metric_commands = defaultdict(lambda: defaultdict(lambda: False))
        self._metric_entry_read_n = defaultdict(lambda: defaultdict(lambda: False))
        self._metric_entry_read_since = defaultdict(lambda: defaultdict(lambda: False))
        self._metric_reference_create = False
        self._metric_reference_create_from_stream = defaultdict(lambda: defaultdict(lambda: False))
        self._metric_reference_get = False

        # For now, only enable metrics if turned on in an environment flag
        if os.getenv("ATOM_USE_METRICS", "FALSE") == "TRUE":

            # Set up redis client for metrics
            if metrics_host is not None:
                self._metrics_host = metrics_host
                self._metrics_port = metrics_port
                self._mclient = RedisTimeSeries(
                    host=self._metrics_host,
                    port=self._metrics_port,
                    socket_timeout=self._redis_data_timeout,
                    socket_connect_timeout=self._redis_connection_timeout
                )
            else:
                self._metrics_socket_path = metrics_socket_path
                self._mclient = RedisTimeSeries(
                    unix_socket_path=self._metrics_socket_path,
                    socket_timeout=self._redis_data_timeout,
                    socket_connect_timeout=self._redis_connection_timeout
                )

            try:
                data = self._mclient.ping()
                if not data:
                    # Don't have redis, so need to only print to stdout
                    self.log(LogLevel.WARNING, f"Invalid ping response {data} from metrics server", redis=False)

                # Create pipeline pool
                for i in range(REDIS_PIPELINE_POOL_SIZE):
                    self._mpipeline_pool.put(self._mclient.pipeline())

                self.log(LogLevel.INFO, "Metrics initialized.", redis=False)
                self._metrics_enabled = True

            except (redis.exceptions.TimeoutError, redis.exceptions.RedisError, redis.exceptions.ConnectionError) as e:
                self.log(LogLevel.ERR, f"Unable to connect to metrics server, error {e}", redis=False)
                if enforce_metrics:

                    # Clean up the redis part of the element since that
                    #   was initialized OK
                    self._clean_up()

                    raise AtomError("Unable to connect to metrics server")

        #
        # Set up Atom
        #

        # Set up redis client for main redis
        if host is not None:
            self._host = host
            self._port = port
            self._rclient = redis.StrictRedis(
                host=self._host,
                port=self._port,
                socket_timeout=self._redis_data_timeout,
                socket_connect_timeout=self._redis_connection_timeout
            )
        else:
            self._socket_path = socket_path
            self._rclient = redis.StrictRedis(
                unix_socket_path=socket_path,
                socket_timeout=self._redis_data_timeout,
                socket_connect_timeout=self._redis_connection_timeout
            )

        try:
            data = self._rclient.ping()
            if not data:
                # Don't have redis, so need to only print to stdout
                self.log(LogLevel.WARNING, f"Invalid ping response {data} from redis server!", redis=False)

        except redis.exceptions.TimeoutError:
            self._timed_out = True
            raise ElementConnectionTimeoutError()

        except redis.exceptions.RedisError:
            raise AtomError("Could not connect to nucleus!")

        # Note we connected to redis
        self._redis_connected = True

        # Init our pool of redis clients/pipelines
        for i in range(REDIS_PIPELINE_POOL_SIZE):
            self._rpipeline_pool.put(self._rclient.pipeline())

        _pipe = self._rpipeline_pool.get()

        # increment global element ref counter
        self._increment_command_group_counter(_pipe)

        _pipe.xadd(
            self._make_response_id(self.name),
            {
                "language": LANG,
                "version": VERSION
            },
            maxlen=STREAM_LEN)
        # Keep track of response_last_id to know last time the client's response stream was read from
        self.response_last_id = _pipe.execute()[-1].decode()
        self.response_last_id_lock = threading.Lock()

        _pipe.xadd(
            self._make_command_id(self.name),
            {
                "language": LANG,
                "version": VERSION
            },
            maxlen=STREAM_LEN)
        # Keep track of command_last_id to know last time the element's command stream was read from
        self.command_last_id = _pipe.execute()[-1].decode()
        _pipe = self._release_pipeline(_pipe)

        # Init a default healthcheck, overridable
        # By default, if no healthcheck is set, we assume everything is ok and return error code 0
        self.healthcheck_set(lambda: Response())

        # Init a version check callback which reports our language/version
        current_major_version = ".".join(VERSION.split(".")[:-1])
        self.command_add(
            VERSION_COMMAND,
            lambda: Response(data={"language": LANG, "version": float(current_major_version)}, serialization="msgpack")
        )

        # Add command to query all commands
        self.command_add(
            COMMAND_LIST_COMMAND,
            lambda: Response(
                data=[k for k in self.handler_map if k not in RESERVED_COMMANDS],
                serialization="msgpack"
            )
        )

        # Load lua scripts
        self._stream_reference_sha = None
        this_dir, this_filename = os.path.split(__file__)
        with open(os.path.join(this_dir, 'stream_reference.lua')) as f:
            data = f.read()
            _pipe = self._rpipeline_pool.get()
            _pipe.script_load(data)
            script_response = _pipe.execute()
            _pipe = self._release_pipeline(_pipe)

            if (not isinstance(script_response, list)) or \
                (len(script_response) != 1) or \
                (not isinstance(script_response[0], str)):
                self.log(LogLevel.ERR, "Failed to load lua script stream_reference.lua")
            else:
                self._stream_reference_sha = script_response[0]

        self.log(LogLevel.INFO, "Element initialized.")

    def __repr__(self):
        return f"{self.__class__.__name__}({self.name})"

    def clean_up_stream(self, stream):
        """
        Deletes the specified stream.

        Args:
            stream (string): The stream to delete.
        """
        if stream not in self.streams:
            raise RuntimeError(
                "Stream '%s' is not present in Element "
                "streams (element: %s)" % (stream, self.name),
            )
        self._rclient.delete(self._make_stream_id(self.name, stream))
        self.streams.remove(stream)

    def _clean_up(self):
        """Clean up everything for the element"""

        if not self._cleaned_up:
            # If the spawning process's element is being deleted, we need
            # to ensure we signal a shutdown to the children
            cur_pid = os.getpid()
            if cur_pid == self._pid:
                self.command_loop_shutdown()

            # decrement ref count
            if self._redis_connected:
                try:
                    _pipe = self._rpipeline_pool.get()
                    self._decrement_command_group_counter(_pipe)
                    _pipe = self._release_pipeline(_pipe)
                except redis.exceptions.TimeoutError:
                    # the connection is already stale or has timed out
                    pass

            self._cleaned_up = True

    def __del__(self):
        """Clean up"""
        self._clean_up()

    def _clean_up_streams(self):
        # if we have encountered a connection timeout there's no use
        # in re-attempting stream cleanup commands as they will implicitly
        # cause the redis pool to reconnect and trigger a subsequent
        # timeout incurring ~2x the intended timeout in some contexts
        if self._timed_out:
            return

        for stream in self.streams.copy():
            self.clean_up_stream(stream)
        try:
            self._rclient.delete(self._make_response_id(self.name))
            self._rclient.delete(self._make_command_id(self.name))
            self._rclient.delete(self._make_consumer_group_counter(self.name))
        except redis.exceptions.RedisError:
            raise Exception("Could not connect to nucleus!")

    def _release_pipeline(self, pipeline, metrics=False):
        """
        Resets the specified pipeline and returns it to the pool of available pipelines.

        Args:
            pipeline (Redis Pipeline): The pipeline to release
        """
        pipeline.reset()
        self._rpipeline_pool.put(pipeline)
        return None

    def _get_metrics_pipeline(self):
        """
        Get a pipeline for use in metrics. We'll try to reuse
        a pipeline that needs flushing (i.e. called with pipeline=pipeline)
        previously and then fall back on using a standard pipeline if not.

        Args:
            timeout (int, optional): Number of seconds to block on a get
                from the pipeline pool. We should almost never see waits on
                getting a pipeline but don't want to hang in the event it
                does start happening

        Return:
            pipeline: the pipeline itself
            len(pipeline): how much data is in the pipeline. This
                will be needed to filter out other peoples' data
                if it happened to be in your pipeline before your commands
                were added.
        """
        try:
            pipeline = self._mpipeline_pool.get(block=False)
        except QueueEmpty:
            self.log(LogLevel.ERR, "Failed to get metrics pipeline, something is very wrong!")
            raise AtomError("Ran out of metrics pipelines!")

        return pipeline

    def _write_metrics_pipeline(self, pipeline, error_ok=None):
        """
        Release (and perhaps execute) a pipeline that was used for a metrics
        call. If execute is TRUE we will execute the pipeline and return
        it to the general pool. If execute is FALSE we will not execute the
        pipeline and we will put it back into the async pool. Then, it will get
        executed either when someone flushes or opportunistically by
        the next person who releases a pipeline with execute=True.

        Args:
            pipeline: pipeline to release (return value 0 of _get_metrics_pipeline)
            prev_len: previous length of the pipeline before we got it (return
                value 1 of _get_metrics_pipeline)
        """
        data = None

        try:
            data = pipeline.execute()
        #  KNOWN ISSUE WITH NO WORKAROUND: Adding two metrics values with the
        #   same timestamp throws this error. We generally shouldn't hit this,
        #   but if we do we shouldn't crash because of it -- lowing metrics
        #   is not the end of the world here.
        except redis.exceptions.ResponseError as e:
            if error_ok and error_ok in str(e):
                pass
            else:
                self.log(LogLevel.ERR, f"Failed to write metrics with exception {e}")

        pipeline.reset()
        self._mpipeline_pool.put(pipeline)

        # Only return the data that we care about (if any)
        return data

    def _update_response_id_if_older(self, new_id):
        """
        Atomically update global response_last_id to new id, if timestamp on new id is more recent

        Args:
            new_id (str): New response id we want to set
        """
        self.response_last_id_lock.acquire()
        components = self.response_last_id.split("-")
        global_id_time = int(components[0])
        global_id_seq = int(components[1])
        components = new_id.split("-")
        new_id_time = int(components[0])
        new_id_seq = int(components[1])
        if (new_id_time > global_id_time or (new_id_time == global_id_time and new_id_seq > global_id_seq)):
            self.response_last_id = new_id
        self.response_last_id_lock.release()

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

    def _make_consumer_group_counter(self, element_name):
        """
        Creates the string representation for an element's command group
        stream counter id.

        Args:
            element_name (str): Name of the element to generate the id for.
        """
        return f"command_consumer_group_counter:{element_name}"

    def _make_consumer_group_id(self, element_name):
        """
        Creates the string representation for an element's command group
        stream id.

        Args:
            element_name (str): Name of the element to generate the id for.
        """
        return f"command_consumer_group:{element_name}"

    def _make_stream_id(self, element_name, stream_name):
        """
        Creates the string representation of an element's stream id.

        Args:
            element_name (str): Name of the element to generate the id for.
            stream_name (str): Name of element_name's stream to generate the id for.
        """
        if element_name is None:
            return stream_name
        else:
            return f"stream:{element_name}:{stream_name}"

    def _make_metric_id(self, element_name, key):
        """
        Creates the string representation of a metric ID created by an
        element

        Args:
            element_name (str): Name of the element to generate the metric ID for
            key: Original key passed by the caller
        """
        return f"{element_name}:{key}"

    def _metric_add_default_labels(self, labels):
        """
        Adds the default labels that come at an element-level. For now
            only the element name but in the future should add in the
            device ID and/or compute running on, etc.

        Raises:
            AtomError: if a reserved label key is used
        """

        # Make the default labels
        default_labels = {}
        default_labels[METRICS_ELEMENT_LABEL] = self.name

        # If we have pre-existing labels, make sure they don't have any
        #   reserved keys and then return the combined dictionaries
        if labels:
            for label in labels:
                if label in RESERVED_METRICS_LABELS:
                    raise AtomError(f"'{label}' is a reserved key in labels")

            return {**labels, **default_labels}
        # Otherwise just return the defaults
        else:
            return default_labels

    def _make_reference_id(self):
        """
        Creates a reference ID

        Args:

        """

        return f"reference:{self.name}:{str(uuid.uuid4())}"

    def _get_redis_timestamp(self):
        """
        Gets the current timestamp from Redis.
        """
        secs, msecs = self._rclient.time()
        timestamp = str(secs) + str(msecs).zfill(6)[:3]
        return timestamp

    def _decode_entry(self, entry):
        """
        Decodes the binary keys of an entry

        Args:
            entry (dict): The entry in dictionary form to decode.
        Returns:
            The decoded entry as a dictionary.
        """
        decoded_entry = {}
        for k in list(entry.keys()):
            if type(k) is bytes:
                k_str = k.decode()
            else:
                k_str = k
            decoded_entry[k_str] = entry[k]
        return decoded_entry

    def _deserialize_entry(self, entry, method=None):
        """
        Deserializes the binary data of the entry.

        Args:
            entry (dict): The entry in dictionary form to deserialize.
            method (str, optional): The method of deserialization to use;
                                    defaults to None.
        Returns:
            The deserialized entry as a dictionary.
        """
        for k, v in entry.items():
            if type(v) is bytes:
                try:
                    entry[k] = ser.deserialize(v, method=method)
                except:
                    pass
        return entry

    def _check_element_version(self, element_name, supported_language_set=None, supported_min_version=None):
        """
        Convenient helper function to query an element about whether it meets min language and version requirements for some feature

        Args:
            element_name (str): Name of the element to query
            supported_language_set (set, optional): Optional set of supported languages target element must be a part of to pass
            supported_min_version (float, optional): Optional min version target element must meet to pass
        """
        # Check if element is reachable and supports the version command
        response = self.get_element_version(element_name)
        if response["err_code"] != ATOM_NO_ERROR or type(response["data"]) is not dict:
            return False
        # Check for valid response to version command
        if not ("version" in response["data"] and "language" in response["data"] and type(response["data"]["version"]) is float):
            return False
        # Validate element meets language requirement
        if supported_language_set and response["data"]["language"] not in supported_language_set:
            return False
        # Validate element meets version requirement
        if supported_min_version and response["data"]["version"] < supported_min_version:
            return False
        return True

    def _get_serialization_method(self, data, user_serialization, force_serialization, deserialize=None):
        """
        Helper function to make a unified serialization decision based off of
        common user arguments. The serialization method returned will
        be a string, that will be based on the following logic:

        1. If `force_serialization` is true, then return the user-passed
            serialization method
        2. If the `ser` key is present in the data, go with that
        3. If the `ser` key is not present and the `deserialize` param is
            present then the type is `msgpack`
        4. Else, leave the data alone

        Args:
            data (dict): set of keys through which to search for special
                serialization key "ser".
            user_serialization (none/str): User-passed argument to API
            force_serialization (bool): Boolean to ignore "ser" key if found
                in favor of the user-passed serialization. This can be useful
                if data is being read from atom in order to then move it
                through another transport layer which still needs the
                serialization
            deserialize (none/bool): Legacy param. If not equal to none, implies
                user_serialization = "msgpack"
        """

        serialization = user_serialization

        if not force_serialization:
            if "ser" in data.keys():
                serialization = data.pop("ser")
                if type(serialization) != str:
                    serialization = serialization.decode()
            elif deserialize is not None:  # check for deprecated legacy mode
                serialization = "msgpack" if deserialize else None

        return serialization

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

    def get_element_version(self, element_name):
        """
        Queries the version info for the given element name.

        Args:
            element_name (str): Name of the element to query

        Returns:
            A dictionary of the response from the command.
        """
        return self.command_send(element_name, VERSION_COMMAND, "", serialization="msgpack")

    def get_all_commands(self, element_name=None, ignore_caller=True):
        """
        Gets the names of the commands of the specified element (all elements by default).

        Args:
            element_name (str): Name of the element of which to get the commands.
            ignore_caller (bool): Do not send commands to the caller.

        Returns:
            List of available commands for all elements or specified element.
        """
        if element_name is None:
            elements = self.get_all_elements()
        elif isinstance(element_name, str):
            elements = [element_name]
        elif isinstance(element_name, (list, tuple)):
            elements = copy.deepcopy(element_name)
        else:
            raise ValueError("unsupported element_name: %s" % (element_name,))
        if ignore_caller and self.name in elements:
            elements.remove(self.name)

        command_list = []
        for element in elements:
            # Check support for command_list command
            if self._check_element_version(element, {'Python'}, 0.3):
                # Retrieve commands for each element
                elem_commands = self.command_send(
                    element,
                    COMMAND_LIST_COMMAND,
                    serialization="msgpack"
                )['data']
                # Rename each command pre-pending the element name
                command_list.extend([f'{element}:{command}' for command in elem_commands])
        return command_list

    def command_add(self, name, handler, timeout=RESPONSE_TIMEOUT, serialization=None, deserialize=None):
        """
        Adds a command to the element for another element to call.

        Args:
            name (str): Name of the command.
            handler (callable): Function to call given the command name.
            timeout (int, optional): Time for the caller to wait for the command to finish.
            serialization (str, optional): The method of serialization to use;
                                           defaults to None.

            Deprecated:
            deserialize (bool, optional): Whether or not to deserialize the data using
                                          msgpack before passing it to the handler.
        """
        if not callable(handler):
            raise TypeError("Passed in handler is not a function!")
        if (name in RESERVED_COMMANDS and name in self.handler_map):
            raise ValueError(
                f"'{name}' is a reserved command name dedicated to {name} "
                 "commands, choose another name"
             )

        if deserialize is not None:  # check for deprecated legacy mode
            serialization = "msgpack" if deserialize else None

        if not ser.is_valid_serialization(serialization):
            raise ValueError(f"Invalid serialization method \"{serialization}\"."
                             "Must be one of {ser.Serializations.print_values()}.")

        self.handler_map[name] = {"handler": handler, "serialization": serialization}

        self.timeouts[name] = timeout

        # Make the metric for the command
        self.metrics_create(f"atom:command:count:{name}", labels={"severity": "timing", "type": "atom_command_info"}, use_default_rules=True, default_agg_list=["SUM"], update=True)
        # Make the metric for timing the command handler
        self.metrics_create(f"atom:command:runtime:{name}", labels={"severity": "info", "type": "atom_command_info"}, use_default_rules=True, default_agg_list=["AVG", "MIN", "MAX"], update=True)
        # Make the error counter for the command handler
        self.metrics_create(f"atom:command:failed:{name}", labels={"severity": "error", "type": "atom_command_info"}, use_default_rules=True, default_agg_list=["SUM"], update=True)
        self.metrics_create(f"atom:command:unhandled_error:{name}", labels={"severity": "error", "type": "atom_command_info"}, use_default_rules=True, default_agg_list=["SUM"], update=True)
        self.metrics_create(f"atom:command:error:{name}", labels={"severity": "error", "type": "atom_command_info"}, use_default_rules=True, default_agg_list=["SUM"], update=True)


    def healthcheck_set(self, handler):
        """
        Sets a custom healthcheck callback

        Args:
            handler (callable): Function to call when evaluating whether this element is healthy or not.
                                Should return a Response with err_code ATOM_NO_ERROR if healthy.
        """
        if not callable(handler):
            raise TypeError("Passed in handler is not a function!")
        # Handler must return response with 0 error_code to pass healthcheck
        self.handler_map[HEALTHCHECK_COMMAND] = {"handler": handler, "serialization": None}
        self.timeouts[HEALTHCHECK_COMMAND] = RESPONSE_TIMEOUT

    def wait_for_elements_healthy(self, element_list, retry_interval=HEALTHCHECK_RETRY_INTERVAL, strict=False):
        """
        Blocking call will wait until all elements in the element respond that they are healthy.

        Args:
            element_list ([str]): List of element names to run healthchecks on
                                  Should return a Response with err_code ATOM_NO_ERROR if healthy.
            retry_interval (float, optional) Time in seconds to wait before retrying after a failed attempt.
            strict (bool, optional) In strict mode, all elements must be reachable and support healthchecks to pass.
                                    If false, elements that don't have healthchecks will be assumed healthy.
        """

        while True:
            all_healthy = True
            for element_name in element_list:
                # Verify element is reachable and supports healthcheck feature
                if not self._check_element_version(element_name, supported_language_set={LANG}, supported_min_version=0.2):
                    # In strict mode, if element is not reachable or doesn't support healthchecks, assume unhealthy
                    if strict:
                        self.log(LogLevel.WARNING, f"Failed healthcheck on {element_name}, retrying...")
                        all_healthy = False
                        break
                    else:
                        continue

                response = self.command_send(element_name, HEALTHCHECK_COMMAND, "")
                if response["err_code"] != ATOM_NO_ERROR:
                    self.log(LogLevel.WARNING, f"Failed healthcheck on {element_name}, retrying...")
                    all_healthy = False
                    break
            if all_healthy:
                break

            time.sleep(retry_interval)

    def command_loop(self, n_procs=1, block=True, read_block_ms=1000, join_timeout=10.0):
        """Main command execution event loop

        For each worker process, performs the following event loop:
            - Waits for command to be put in element's command stream consumer
              group
            - Sends Acknowledge to caller and then runs command
            - Returns Response with processed data to caller

        Args:
            n_procs (integer): Number of worker processes.  Each worker process
                               will pull work from the Element's shared command
                               consumer group (defaults to 1).
            block (bool, optional): Wait for the response before returning
                                    from the function.
                                       block.
            read_block_ms (integer, optional): Number of milliseconds to block
                                               for during a stream read insde of
                                               a command loop.
            join_timeout (integer, optional): If block=True, how long to wait while
                                              joining threads at the end of the
                                              command loop before raising an
                                              exception
        """
        # update self._pid in case e.g. we were constructed in a parent thread but
        # `command_loop` was explicitly called as a sub-process
        self._pid = os.getpid()
        n_procs = int(n_procs)
        if n_procs <= 0:
            raise ValueError("n_procs must be a positive integer")

        # note: This warning is emitted in situations where the calling process has more
        #       than one active thread.  When the command_loop children processes are
        #       forked they will only copy the thread state of the active thread which
        #       invoked the fork.  Other active thread state will *not* be copied to
        #       these descendent processes.  This may cause some problems with proper
        #       execution of the Element's command_loop if the command depends on this
        #       thread state being available on the descendent processes.
        #       Please see the following Stack Overflow link for more context:
        #       https://stackoverflow.com/questions/39890363/what-happens-when-a-thread-forks
        thread_count = threading.active_count()
        if thread_count > 1:
            self.log(
                LogLevel.WARNING,
                f"[element:{self.name}] Active thread count is currently {thread_count}.  Child command_loop "
                "processes will only copy one active thread's state and therefore may not "
                "work properly."
            )

        self.processes = []
        for i in range(n_procs):
            p = Process(target=self._command_loop, args=(self._command_loop_shutdown, i,), kwargs={'read_block_ms' : read_block_ms})
            p.start()
            self.processes.append(p)

        if block:
            self._command_loop_join(join_timeout=join_timeout)

    def _increment_command_group_counter(self, _pipe):
        """Incremeents reference counter for element stream collection"""
        _pipe.incr(self._make_consumer_group_counter(self.name))
        result = _pipe.execute()[-1]
        self.log(
            LogLevel.DEBUG,
            f'inrementing element {self.name} {result}',
            stdout=False
        )
        return result

    def _decrement_command_group_counter(self, _pipe):
        """Decrements reference counter for element stream collection"""
        _pipe.decr(self._make_consumer_group_counter(self.name))
        result = _pipe.execute()[-1]
        self.log(
            LogLevel.DEBUG,
            f'decrementing element {self.name} {result}',
            stdout=False
        )
        if not result:
            #TODO: consider logging
            self.log(
                LogLevel.DEBUG,
                f'cleaning up stream {self.name}',
                stdout=False
            )
            self._clean_up_streams()
        return result

    def _command_loop(self, shutdown_event, worker_num, read_block_ms=1000):
        if hasattr(self, '_host'):
            _rclient = redis.StrictRedis(host=self._host, port=self._port)
        else:
            _rclient = redis.StrictRedis(unix_socket_path=self._socket_path)
        _pipe = _rclient.pipeline()

        #cur_pid = os.getpid()
        #if cur_pid != self._pid:
        #    self._increment_command_group_counter(_pipe)

        # Make timing metrics
        self.metrics_create(f"atom:command_loop:worker{worker_num}:block_time", labels={"severity": "timing", "detail" : "block_time", "type": "atom_command_loop", "worker" : f"{worker_num}"}, use_default_rules=True, default_agg_list=["AVG", "MIN", "MAX"], update=True)
        self.metrics_create(f"atom:command_loop:worker{worker_num}:block_handler_time", labels={"severity": "timing", "detail" : "block_handler_time", "type": "atom_command_loop", "worker" : f"{worker_num}"}, use_default_rules=True, default_agg_list=["AVG", "MIN", "MAX"], update=True)
        self.metrics_create(f"atom:command_loop:worker{worker_num}:handler_time", labels={"severity": "timing", "detail" : "handler_time", "type": "atom_command_loop", "worker" : f"{worker_num}"}, use_default_rules=True, default_agg_list=["AVG", "MIN", "MAX"], update=True)
        self.metrics_create(f"atom:command_loop:worker{worker_num}:handler_block_time", labels={"severity": "timing", "detail" : "handler_block_time", "type": "atom_command_loop", "worker" : f"{worker_num}"}, use_default_rules=True, default_agg_list=["AVG", "MIN", "MAX"], update=True)

        # Info counters
        self.metrics_create(f"atom:command_loop:worker{worker_num}:n_commands", labels={"severity": "info", "detail" : "n_commands", "type": "atom_command_loop", "worker" : f"{worker_num}"}, use_default_rules=True, default_agg_list=["SUM"], update=True)

        # Error counters
        self.metrics_create(f"atom:command_loop:worker{worker_num}:xreadgroup_error", labels={"severity": "error", "detail" : "xreadgroup_error", "type": "atom_command_loop", "worker" : f"{worker_num}"}, use_default_rules=True, default_agg_list=["SUM"], update=True)
        self.metrics_create(f"atom:command_loop:worker{worker_num}:stream_match_error", labels={"severity": "error", "detail" : "stream_match_error", "type": "atom_command_loop", "worker" : f"{worker_num}"}, use_default_rules=True, default_agg_list=["SUM"], update=True)
        self.metrics_create(f"atom:command_loop:worker{worker_num}:no_caller", labels={"severity": "error", "detail" : "no_caller", "type": "atom_command_loop", "worker" : f"{worker_num}"}, use_default_rules=True, default_agg_list=["SUM"], update=True)
        self.metrics_create(f"atom:command_loop:worker{worker_num}:unsupported_command", labels={"severity": "error", "detail" : "unsupported_command", "type": "atom_command_loop", "worker" : f"{worker_num}"}, use_default_rules=True, default_agg_list=["SUM"], update=True)
        self.metrics_create(f"atom:command_loop:worker{worker_num}:callback_unhandled_error", labels={"severity": "error", "detail" : "callback_unhandled_error", "type": "atom_command_loop", "worker" : f"{worker_num}"}, use_default_rules=True, default_agg_list=["SUM"], update=True)
        self.metrics_create(f"atom:command_loop:worker{worker_num}:callback_handled_error", labels={"severity": "error", "detail" : "callback_handled_error", "type": "atom_command_loop", "worker" : f"{worker_num}"}, use_default_rules=True, default_agg_list=["SUM"], update=True)
        self.metrics_create(f"atom:command_loop:worker{worker_num}:response_error", labels={"severity": "error", "detail" : "response_error", "type": "atom_command_loop", "worker" : f"{worker_num}"}, use_default_rules=True, default_agg_list=["SUM"], update=True)
        self.metrics_create(f"atom:command_loop:worker{worker_num}:xack_error", labels={"severity": "error", "detail" : "xack_error", "type": "atom_command_loop", "worker" : f"{worker_num}"}, use_default_rules=True, default_agg_list=["SUM"], update=True)

        # get a group handle
        # note: if use_command_last_id is set then the group will receive
        #       messages newer than the most recent command id observed by the
        #       Element class.  However, by default it will than accept
        #       messages newer than the creation of the consumer group.
        #
        stream_name = self._make_command_id(self.name)
        group_name = self._make_consumer_group_id(self.name)
        group_last_cmd_id = self.command_last_id
        try:
            _rclient.xgroup_create(
                stream_name,
                group_name,
                group_last_cmd_id,
                mkstream=True
            )
        except redis.exceptions.ResponseError:
            # If we encounter a `ResponseError` we assume it's because of a `BUSYGROUP`
            # signal, implying the consumer group already exists for this command.
            #
            # Thus, we go on our merry way as we can successfully proceed pulling from the
            # already created group :)
            pass
        # make a new uuid for the consumer name
        consumer_uuid = str(uuid.uuid4())
        while not shutdown_event.is_set():

            with MetricsPipeline(self) as pipeline:

                # Get oldest new command from element's command stream
                # note: consumer group consumer id is implicitly announced
                try:

                    # Pre-block metrics
                    self.metrics_timing_start(f"atom:command_loop:worker{worker_num}:block_time")

                    # Block, get a command
                    cmd_responses = _rclient.xreadgroup(
                        group_name,
                        consumer_uuid,
                        {stream_name: '>'},
                        block=read_block_ms,
                        count=1
                    )

                    # Post-block metrics
                    self.metrics_timing_end(f"atom:command_loop:worker{worker_num}:block_time", pipeline=pipeline)
                    self.metrics_timing_start(f"atom:command_loop:worker{worker_num}:block_handler_time")
                except redis.exceptions.ResponseError:
                    self.log(
                        LogLevel.ERR,
                        f"Recieved redis ResponseError.  Possible attempted "
                        "XREADGROUP on closed stream %s (is shutdown: %s).  "
                        "Please ensure you have performed the command_loop_shutdown"
                        " command on the object running command_loop." % (
                            stream_name,
                            shutdown_event.is_set()
                        ),
                        _pipe=_pipe
                    )
                    self.metrics_add((f"atom:command_loop:worker{worker_num}:xreadgroup_error", 1))
                    return

                if not cmd_responses:
                    continue
                cmd_stream_name, msgs = cmd_responses[0]
                if cmd_stream_name.decode() != stream_name:
                    self.metrics_add((f"atom:command_loop:worker{worker_num}:stream_match_error", 1))
                    raise RuntimeError(
                        "Expected received stream name to match: %s %s" % (
                            cmd_stream_name,
                            stream_name
                        ))

                assert len(msgs) == 1, "expected one message: %s" % (msgs,)

                msg = msgs[0]  # we only read one
                cmd_id, cmd = msg

                # Set the command_last_id to this command's id to keep track of our
                # last read
                self.command_last_id = cmd_id.decode()

                try:
                    caller = cmd[b"element"].decode()
                    cmd_name = cmd[b"cmd"].decode()
                    data = cmd[b"data"]
                except KeyError:
                    # Ignore non-commands
                    continue

                if not caller:
                    self.log(LogLevel.ERR, "No caller name present in command!", _pipe=_pipe)
                    self.metrics_add((f"atom:command_loop:worker{worker_num}:no_caller", 1))
                    continue

                # Send acknowledge to caller
                if cmd_name not in self.timeouts.keys():
                    timeout = RESPONSE_TIMEOUT
                else:
                    timeout = self.timeouts[cmd_name]
                acknowledge = Acknowledge(self.name, cmd_id, timeout)

                _pipe.xadd(self._make_response_id(caller), vars(acknowledge), maxlen=STREAM_LEN)
                _pipe.execute()

                # Send response to caller
                if cmd_name not in self.handler_map.keys():
                    self.log(LogLevel.ERR, "Received unsupported command: %s" % (cmd_name,), _pipe=_pipe)
                    response = Response(
                        err_code=ATOM_COMMAND_UNSUPPORTED,
                        err_str="Unsupported command."
                    )
                    self.metrics_add((f"atom:command_loop:worker{worker_num}:unsupported_command", 1), pipeline=pipeline)
                else:

                    # Pre-handler metrics
                    self.metrics_timing_end(f"atom:command_loop:worker{worker_num}:block_handler_time", pipeline=pipeline)
                    self.metrics_timing_start(f"atom:command_loop:worker{worker_num}:handler_time")
                    self.metrics_timing_start(f"atom:command:runtime:{cmd_name}")


                    if cmd_name not in RESERVED_COMMANDS:
                        if "deserialize" in self.handler_map[cmd_name]:  # check for deprecated legacy mode
                            serialization = "msgpack" if self.handler_map[cmd_name]["deserialize"] else None
                        else:
                            serialization = self.handler_map[cmd_name]["serialization"]
                        data = ser.deserialize(data, method=serialization)
                        try:
                            response = self.handler_map[cmd_name]["handler"](data)

                        except:
                            self.log(
                                LogLevel.ERR,
                                "encountered error with command: %s\n%s" % (
                                    cmd_name,
                                    format_exc()
                                ),
                                _pipe=_pipe
                            )
                            response = Response(
                                err_code=ATOM_INTERNAL_ERROR,
                                err_str="encountered an internal exception "
                                        "during command execution: %s" % (cmd_name,)
                            )
                            self.metrics_add((f"atom:command_loop:worker{worker_num}:callback_unhandled_error", 1), pipeline=pipeline)
                            self.metrics_add((f"atom:command:unhandled_error:{cmd_name}", 1), pipeline=pipeline)

                    else:
                        # healthcheck/version requests/command_list commands don't
                        # care what data you are sending
                        response = self.handler_map[cmd_name]["handler"]()

                    # Post-handler-metrics
                    self.metrics_timing_end(f"atom:command:runtime:{cmd_name}", pipeline=pipeline)
                    self.metrics_timing_end(f"atom:command_loop:worker{worker_num}:handler_time", pipeline=pipeline)
                    self.metrics_timing_start(f"atom:command_loop:worker{worker_num}:handler_block_time")

                    # Add ATOM_USER_ERRORS_BEGIN to err_code to map to element error range
                    if isinstance(response, Response):
                        if response.err_code != 0:
                            response.err_code += ATOM_USER_ERRORS_BEGIN
                            self.metrics_add((f"atom:command:error:{cmd_name}", 1), pipeline=pipeline)

                    else:
                        response = Response(
                            err_code=ATOM_CALLBACK_FAILED,
                            err_str=f"Return type of {cmd_name} is not of type Response"
                        )
                        self.metrics_add((f"atom:command_loop:worker{worker_num}:callback_handled_error", 1), pipeline=pipeline)
                        self.metrics_add((f"atom:command:failed:{cmd_name}", 1), pipeline=pipeline)

                    # Note we called the command and got through it
                    self.metrics_add((f"atom:command:count:{cmd_name}", 1), pipeline=pipeline)


                # send response on appropriate stream
                kv = vars(response)
                kv["cmd_id"] = cmd_id
                kv["element"] = self.name
                kv["cmd"] = cmd_name
                try:
                    _pipe.xadd(self._make_response_id(caller), kv, maxlen=STREAM_LEN)
                    _pipe.execute()
                except:
                    # If we fail to xadd the response, go ahead and continue
                    # we will xack the response to bring it out of pending list.
                    # This command will be treated as being "handled" and will not
                    # be re-attempted
                    self.metrics_add((f"atom:command_loop:worker{worker_num}:response_error", 1), pipeline=pipeline)

                # `XACK` the command we have just completed back to the consumer
                # group to remove the command from the consumer group pending
                # entry list (PEL).
                try:
                    _pipe.xack(
                        stream_name,
                        group_name,
                        cmd_id
                    )
                    _pipe.execute()
                    self.metrics_add((f"atom:command_loop:worker{worker_num}:n_commands", 1), pipeline=pipeline)
                except:
                    self.log(
                        LogLevel.ERR,
                        "encountered error during xack (stream name:%s, group name: "
                        "%s, cmd_id: %s)\n%s" % (
                            stream_name,
                            group_name,
                            cmd_id,
                            format_exc()
                        ),
                        _pipe=_pipe
                    )
                    self.metrics_add((f"atom:command_loop:worker{worker_num}:xack_error", 1), pipeline=pipeline)

                # we're essentially going into the block and if we wrap it up here we don't
                #   need to handle edge cases where it hadn't been started before
                self.metrics_timing_end(f"atom:command_loop:worker{worker_num}:handler_block_time", pipeline=pipeline)


    def _command_loop_join(self, join_timeout=10.0):
        """Waits for all threads from command loop to be finished"""
        for p in self.processes:
            p.join(join_timeout)

    def command_loop_shutdown(self, block=False, join_timeout=10.0):
        """Triggers graceful exit of command loop"""
        self._command_loop_shutdown.set()
        if block:
            self._command_loop_join(join_timeout=join_timeout)

    def command_send(self,
                     element_name,
                     cmd_name,
                     data="",
                     block=True,
                     ack_timeout=ACK_TIMEOUT,
                     serialization=None,
                     serialize=None,
                     deserialize=None):
        """
        Sends command to element and waits for acknowledge.
        When acknowledge is received, waits for timeout from acknowledge or until response is received.

        Args:
            element_name (str): Name of the element to send the command to.
            cmd_name (str): Name of the command to execute of element_name.
            data: Entry to be passed to the function specified by cmd_name.
            block (bool): Wait for the response before returning from the function.
            ack_timeout (int, optional): Time in milliseconds to wait for ack before
                                         timing out, overrides default value.
            serialization (str, optional): Method of serialization to use;
                                           defaults to None.

            Deprecated:
            serialize (bool, optional): Whether or not to serialize the data with msgpack
                                        before sending it to the command; defaults to None.
            deserialize (bool, optional): Whether or not to deserialize the data with
                                          msgpack in the response; defaults to None.

        Returns:
            A dictionary of the response from the command.
        """
        # cache the last response id at the time we are issuing this command, since this can get overwritten
        local_last_id = self.response_last_id
        timeout = None
        resp = None
        data = format_redis_py(data)

        # Get a metrics pipeline
        with MetricsPipeline(self) as pipeline:

            # If we haven't sent this command before, need to make the metrics
            #   for it
            if not self._metric_commands[element_name][cmd_name]:
                self.metrics_create(f"atom:command_send:serialize:{element_name}:{cmd_name}", labels={"severity": "info", "type": "atom_command_send", "detail" : "serialize"}, use_default_rules=True, default_agg_list=["AVG", "MIN", "MAX"], update=True)
                self.metrics_create(f"atom:command_send:runtime:{element_name}:{cmd_name}", labels={"severity": "info", "type": "atom_command_send", "detail" : "runtime"}, use_default_rules=True, default_agg_list=["AVG", "MIN", "MAX"], update=True)
                self.metrics_create(f"atom:command_send:deserialize:{element_name}:{cmd_name}", labels={"severity": "info", "type": "atom_command_send", "detail" : "deserialize"}, use_default_rules=True, default_agg_list=["AVG", "MIN", "MAX"], update=True)
                self.metrics_create(f"atom:command_send:error:{element_name}:{cmd_name}", labels={"severity": "error", "type": "atom_command_send"}, use_default_rules=True, default_agg_list=["SUM"], update=True)

                self._metric_commands[element_name][cmd_name] = True

            # Send command to element's command stream
            if serialize is not None:  # check for deprecated legacy mode
                serialization = "msgpack" if serialize else None

            self.metrics_timing_start(f"atom:command_send:serialize:{element_name}:{cmd_name}")
            data = ser.serialize(data, method=serialization) if (data != "") else data
            self.metrics_timing_end(f"atom:command_send:serialize:{element_name}:{cmd_name}", pipeline=pipeline)

            self.metrics_timing_start(f"atom:command_send:runtime:{element_name}:{cmd_name}")
            cmd = Cmd(self.name, cmd_name, data)
            _pipe = self._rpipeline_pool.get()
            _pipe.xadd(self._make_command_id(element_name), vars(cmd), maxlen=STREAM_LEN)
            cmd_id = _pipe.execute()[-1].decode()
            _pipe = self._release_pipeline(_pipe)

            # Receive acknowledge from element
            # You have no guarantee that the response from the xread is for your specific thread,
            # so keep trying until we either receive our ack, or timeout is exceeded
            start_read = time.time()
            elapsed_time_ms = (time.time() - start_read) * 1000
            while True:
                responses = self._rclient.xread(
                    {self._make_response_id(self.name): local_last_id},
                    block=max(int(ack_timeout - elapsed_time_ms), 1)
                )
                if not responses:
                    elapsed_time_ms = (time.time() - start_read) * 1000
                    if elapsed_time_ms >= ack_timeout:
                        err_str = f"Did not receive acknowledge from {element_name}."
                        self.log(LogLevel.ERR, err_str)
                        self.metrics_add((f"atom:command_send:error:{element_name}:{cmd_name}", 1))
                        return vars(Response(err_code=ATOM_COMMAND_NO_ACK, err_str=err_str))
                        break
                    else:
                        continue

                stream, msgs = responses[0]  # we only read one stream
                for id, response in msgs:
                    local_last_id = id.decode()

                    if b"element" in response and response[b"element"].decode() == element_name \
                    and b"cmd_id" in response and response[b"cmd_id"].decode() == cmd_id \
                    and b"timeout" in response:
                        timeout = int(response[b"timeout"].decode())
                        break

                    self._update_response_id_if_older(local_last_id)

                # If the response we received wasn't for this command, keep trying until ack timeout
                if timeout is not None:
                    break

            if timeout is None:
                err_str = f"Did not receive acknowledge from {element_name}."
                self.log(LogLevel.ERR, err_str)
                self.metrics_add((f"atom:command_send:error:{element_name}:{cmd_name}", 1))
                return vars(Response(err_code=ATOM_COMMAND_NO_ACK, err_str=err_str))

            # Receive response from element
            # You have no guarantee that the response from the xread is for your specific thread,
            # so keep trying until we either receive our response, or timeout is exceeded
            start_read = time.time()
            while True:
                elapsed_time_ms = (time.time() - start_read) * 1000
                if elapsed_time_ms >= timeout:
                    break

                responses = self._rclient.xread(
                    {self._make_response_id(self.name): local_last_id},
                    block=max(int(timeout - elapsed_time_ms), 1)
                )
                if not responses:
                    err_str = f"Did not receive response from {element_name}."
                    self.log(LogLevel.ERR, err_str)
                    self.metrics_add((f"atom:command_send:error:{element_name}:{cmd_name}", 1))
                    return vars(Response(err_code=ATOM_COMMAND_NO_RESPONSE, err_str=err_str))

                stream_name, msgs = responses[0]  # we only read from one stream
                for msg in msgs:
                    id, response = msg
                    local_last_id = id.decode()

                    if b"element" in response and response[b"element"].decode() == element_name \
                    and b"cmd_id" in response and response[b"cmd_id"].decode() == cmd_id \
                    and b"err_code" in response:

                        self.metrics_timing_end(f"atom:command_send:runtime:{element_name}:{cmd_name}", pipeline=pipeline)
                        self.metrics_timing_start(f"atom:command_send:deserialize:{element_name}:{cmd_name}")

                        err_code = int(response[b"err_code"].decode())
                        err_str = response[b"err_str"].decode() if b"err_str" in response else ""
                        if err_code != ATOM_NO_ERROR:
                            self.log(LogLevel.ERR, err_str)

                        response_data = response.get(b"data", "")
                        # check response for serialization method; if not present, use user specified method
                        if b"ser" in response:
                            serialization = response[b"ser"].decode()
                        elif deserialize is not None:  # check for deprecated legacy mode
                            serialization = "msgpack" if deserialize else None

                        try:
                            response_data = (ser.deserialize(response_data, method=serialization) if
                                             (len(response_data) != 0) else response_data)
                        except TypeError:
                            self.log(LogLevel.WARNING, "Could not deserialize response.")
                            self.metrics_add((f"atom:command_send:error:{element_name}:{cmd_name}", 1))

                        self.metrics_timing_end(f"atom:command_send:deserialize:{element_name}:{cmd_name}", pipeline=pipeline)

                        # Make the final response
                        resp = vars(Response(data=response_data, err_code=err_code, err_str=err_str))
                        break

                self._update_response_id_if_older(local_last_id)
                if resp is not None:
                    self.metrics_write_pipeline(pipeline)
                    return resp

                # If the response we received wasn't for this command, keep trying until timeout
                continue

            # Proper response was not in responses
            err_str = f"Did not receive response from {element_name}."
            self.log(LogLevel.ERR, err_str)
            self.metrics_add((f"atom:command_send:error:{element_name}:{cmd_name}", 1), pipeline=pipeline)

        return vars(Response(err_code=ATOM_COMMAND_NO_RESPONSE, err_str=err_str))

    def entry_read_loop(self, stream_handlers, n_loops=None, timeout=MAX_BLOCK, serialization=None, force_serialization=False, deserialize=None):
        """
        Listens to streams and pass any received entry to corresponding handler.

        Args:
            stream_handlers (list of messages.StreamHandler):
            n_loops (int): Number of times to send the stream entry to the handlers.
            timeout (int): How long to block on the stream. If surpassed, the function returns.
            serialization (str, optional): If deserializing, the method of serialization
                                           to use; defaults to None.
            force_serialization (bool): Boolean to ignore "ser" key if found
                in favor of the user-passed serialization. Defaults to false.

            Deprecated:
            deserialize (bool, optional): Whether or not to deserialize the entries
                                          using msgpack; defaults to None.
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
            stream_entries = self._rclient.xread(streams, block=timeout)
            if not stream_entries:
                return
            for stream, msgs in stream_entries:
                for uid, entry in msgs:
                    streams[stream] = uid
                    entry = self._decode_entry(entry)
                    serialization = self._get_serialization_method(entry, serialization, force_serialization, deserialize)
                    entry = self._deserialize_entry(entry, method=serialization)
                    entry["id"] = uid.decode()
                    stream_handler_map[stream.decode()](entry)

    def entry_read_n(self, element_name, stream_name, n, serialization=None, force_serialization=False, deserialize=None):
        """
        Gets the n most recent entries from the specified stream.

        Args:
            element_name (str): Name of the element to get the entry from.
            stream_name (str): Name of the stream to get the entry from.
            n (int): Number of entries to get.
            serialization (str, optional): The method of deserialization to use;
                                           defaults to None.
            force_serialization (bool): Boolean to ignore "ser" key if found
                in favor of the user-passed serialization. Defaults to false.

            Deprecated:
            deserialize (bool, optional): Whether or not to deserialize the entries\
                                          using msgpack; defaults to None.

        Returns:
            List of dicts containing the data of the entries
        """

        # Get a metrics pipeline
        with MetricsPipeline(self) as pipeline:

            # If we haven't read this entry with read_n before, create the metrics
            if not self._metric_entry_read_n[element_name][stream_name]:
                self.metrics_create(f"atom:entry_read_n:data:{element_name}:{stream_name}", labels={"severity": "info", "type": "atom_entry_read_n", "detail" : "data"}, use_default_rules=True, default_agg_list=["AVG", "MIN", "MAX"], update=True)
                self.metrics_create(f"atom:entry_read_n:deserialize:{element_name}:{stream_name}", labels={"severity": "info", "type": "atom_entry_read_n", "detail" : "deserialize"}, use_default_rules=True, default_agg_list=["AVG", "MIN", "MAX"], update=True)
                self.metrics_create(f"atom:entry_read_n:n:{element_name}:{stream_name}", labels={"severity": "info", "type": "atom_entry_read_n", "detail" : "n"}, use_default_rules=True, default_agg_list=["SUM"], update=True)

                self._metric_entry_read_n[element_name][stream_name] = True


            entries = []
            stream_id = self._make_stream_id(element_name, stream_name)

            self.metrics_timing_start(f"atom:entry_read_n:data:{element_name}:{stream_name}")
            uid_entries = self._rclient.xrevrange(stream_id, count=n)
            self.metrics_timing_end(f"atom:entry_read_n:data:{element_name}:{stream_name}", pipeline=pipeline)
            self.metrics_timing_start(f"atom:entry_read_n:deserialize:{element_name}:{stream_name}")
            for uid, entry in uid_entries:
                entry = self._decode_entry(entry)
                serialization = self._get_serialization_method(entry, serialization, force_serialization, deserialize)
                entry = self._deserialize_entry(entry, method=serialization)
                entry["id"] = uid.decode()
                entries.append(entry)
            self.metrics_timing_end(f"atom:entry_read_n:deserialize:{element_name}:{stream_name}", pipeline=pipeline)

            self.metrics_add((f"atom:entry_read_n:n:{element_name}:{stream_name}", len(entries)), pipeline=pipeline)

        return entries

    def entry_read_since(self,
                         element_name,
                         stream_name,
                         last_id="$",
                         n=None,
                         block=None,
                         serialization=None,
                         force_serialization=False,
                         deserialize=None):
        """
        Read entries from a stream since the last_id.

        Args:
            element_name (str): Name of the element to get the entry from.
            stream_name (str): Name of the stream to get the entry from.
            last_id (str, optional): Time from which to start get entries from. If '0', get all entries.
                If '$' (default), get only new entries after the function call (blocking).
            n (int, optional): Number of entries to get. If None, get all.
            block (int, optional): Time (ms) to block on the read. If 0, block forever.
                If None, don't block.
            serialization (str, optional): Method of deserialization to use;
                                           defaults to None.
            force_serialization (bool): Boolean to ignore "ser" key if found
                in favor of the user-passed serialization. Defaults to false.

            Deprecated:
            deserialize (bool, optional): Whether or not to deserialize the entries
                                          using msgpack; defaults to None.
        """

        # Get a metrics pipeline
        with MetricsPipeline(self) as pipeline:

            # If we haven't read this entry with read_since before, create the metrics
            if not self._metric_entry_read_since[element_name][stream_name]:
                self.metrics_create(f"atom:entry_read_since:data:{element_name}:{stream_name}", labels={"severity": "info", "type": "atom_entry_read_since", "detail" : "data"}, use_default_rules=True, default_agg_list=["AVG", "MIN", "MAX"], update=True)
                self.metrics_create(f"atom:entry_read_since:deserialize:{element_name}:{stream_name}", labels={"severity": "info", "type": "atom_entry_read_since", "detail" : "deserialize"}, use_default_rules=True, default_agg_list=["AVG", "MIN", "MAX"], update=True)
                self.metrics_create(f"atom:entry_read_since:n:{element_name}:{stream_name}", labels={"severity": "info", "type": "atom_entry_read_since", "detail" : "n"}, use_default_rules=True, default_agg_list=["SUM"], update=True)

                self._metric_entry_read_since[element_name][stream_name] = True


            streams, entries = {}, []
            stream_id = self._make_stream_id(element_name, stream_name)
            streams[stream_id] = last_id
            self.metrics_timing_start(f"atom:entry_read_since:data:{element_name}:{stream_name}")
            stream_entries = self._rclient.xread(streams, count=n, block=block)
            self.metrics_timing_end(f"atom:entry_read_since:data:{element_name}:{stream_name}", pipeline=pipeline)
            stream_names = [x[0].decode() for x in stream_entries]
            if not stream_entries or stream_id not in stream_names:
                self.metrics_write_pipeline(pipeline)
                return entries
            self.metrics_timing_start(f"atom:entry_read_since:deserialize:{element_name}:{stream_name}")
            for key, msgs in stream_entries:
                if key.decode() == stream_id:
                    for uid, entry in msgs:
                        entry = self._decode_entry(entry)
                        serialization = self._get_serialization_method(entry, serialization, force_serialization, deserialize)
                        entry = self._deserialize_entry(entry, method=serialization)
                        entry["id"] = uid.decode()
                        entries.append(entry)
            self.metrics_timing_end(f"atom:entry_read_since:deserialize:{element_name}:{stream_name}", pipeline=pipeline)
            self.metrics_add((f"atom:entry_read_since:n:{element_name}:{stream_name}", len(entries)), pipeline=pipeline)

        return entries

    def entry_write(self, stream_name, field_data_map, maxlen=STREAM_LEN, serialization=None, serialize=None):
        """
        Creates element's stream if it does not exist.
        Adds the fields and data to a Entry and puts it in the element's stream.

        Args:
            stream_name (str): The stream to add the data to.
            field_data_map (dict): Dict which creates the Entry. See messages.Entry for more usage.
            maxlen (int, optional): The maximum number of data to keep in the stream.
            serialization (str, optional): Method of serialization to use;
                                           defaults to None.

            Deprecated:
            serialize (bool, optional): Whether or not to serialize the entry using
                                        msgpack; defaults to None.

        Return: ID of item added to stream
        """

        # Get a metrics pipeline
        with MetricsPipeline(self) as pipeline:

            # If we haven't written this entry with entry_write before, make the metrics
            if stream_name not in self.streams:
                self.metrics_create(f"atom:entry_write:data:{stream_name}", labels={"severity": "info", "type": "atom_entry_write", "detail" : "data"}, use_default_rules=True, default_agg_list=["AVG", "MIN", "MAX"], update=True)
                self.metrics_create(f"atom:entry_write:serialize:{stream_name}", labels={"severity": "info", "type": "atom_entry_write", "detail" : "serialize"}, use_default_rules=True, default_agg_list=["AVG", "MIN", "MAX"], update=True)

            self.streams.add(stream_name)
            field_data_map = format_redis_py(field_data_map)

            if serialize is not None:  # check for deprecated legacy mode
                serialization = "msgpack" if serialize else None

            self.metrics_timing_start(f"atom:entry_write:serialize:{stream_name}")
            ser_field_data_map = {}
            for k, v in field_data_map.items():
                if k in ENTRY_RESERVED_KEYS:
                    raise ValueError(f"Invalid key \"{k}\": \"{k}\" is a reserved entry key")
                ser_field_data_map[k] = ser.serialize(v, method=serialization)

            ser_field_data_map["ser"] = str(serialization) if serialization is not None else "none"
            entry = Entry(ser_field_data_map)

            self.metrics_timing_end(f"atom:entry_write:serialize:{stream_name}", pipeline=pipeline)
            self.metrics_timing_start(f"atom:entry_write:data:{stream_name}")

            _pipe = self._rpipeline_pool.get()
            _pipe.xadd(self._make_stream_id(self.name, stream_name), vars(entry), maxlen=maxlen)
            ret = _pipe.execute()
            _pipe = self._release_pipeline(_pipe)

            self.metrics_timing_end(f"atom:entry_write:data:{stream_name}", pipeline=pipeline)

        if ((not isinstance(ret, list)) or (len(ret) != 1)
                or (not isinstance(ret[0], bytes))):
            print(ret)
            raise ValueError("Failed to write data to stream")

        return ret[0].decode()

    def log(self, level, msg, stdout=True, _pipe=None, redis=True):
        """
        Writes a message to log stream with loglevel.

        Args:
            level (messages.LogLevel): Unix syslog severity of message.
            message (str): The message to write for the log.
            stdout (bool, optional): Whether to write to stdout or only write to log stream.
            _pipe (pipeline, optional): Pipeline to use for the log message to
                be sent to redis
            redis (bool, optional): Default true, whether to log to
                redis or not
        """
        log = Log(self.name, self.host, level, msg)

        if redis:
            _release_pipe = False

            if _pipe is None:
                _release_pipe = True
                _pipe = self._rpipeline_pool.get()
            _pipe.xadd("log", vars(log), maxlen=STREAM_LEN)
            _pipe.execute()
            if _release_pipe:
                _pipe = self._release_pipeline(_pipe)

        if stdout:
            print(msg)

    def reference_create(self, *data, serialization=None, serialize=None, timeout_ms=10000):
        """
        Creates one or more expiring references (similar to a pointer) in the atom system.
        This will typically be used when we've gotten a piece of data from a
        stream and we want it to persist past the length of time it would live
        in the stream s.t. we can pass it to other commands/elements. The
        references will simply be cached values in redis and will expire after
        the timeout_ms amount of time.

        Args:
            data (binary or object): one or more data items to be included in the reference
            timeout_ms (int, optional): How long the reference should persist in atom
                        unless otherwise extended/deleted. Set to 0 to have the
                        reference never time out (generally a terrible idea)
            serialization (str, optional): Method of serialization to use;
                                           defaults to None.

            Deprecated:
            serialize (bool, optional): whether or not to serialize the data using
                                        msgpack before creating the reference

        Return:
            List of references corresponding to the arguments passed
        """
        keys = []

        # Get a metrics pipeline
        with MetricsPipeline(self) as pipeline:

            if not self._metric_reference_create:
                self.metrics_create(f"atom:reference_create:data", labels={"severity": "info", "type": "atom_reference_create", "detail" : "data"}, use_default_rules=True, default_agg_list=["AVG", "MIN", "MAX"], update=True)
                self.metrics_create(f"atom:reference_create:serialize", labels={"severity": "info", "type": "atom_reference_create", "detail" : "serialize"}, use_default_rules=True, default_agg_list=["AVG", "MIN", "MAX"], update=True)
                self.metrics_create(f"atom:reference_create:n", labels={"severity": "info", "type": "atom_reference_create", "detail" : "n"}, use_default_rules=True, default_agg_list=["SUM"], update=True)

                self._metric_reference_create = True

            if serialize is not None:  # check for deprecated legacy mode
                serialization = "msgpack" if serialize else None

            _pipe = self._rpipeline_pool.get()
            px_val = timeout_ms if timeout_ms != 0 else None
            self.metrics_timing_start(f"atom:reference_create:serialize")
            for datum in data:
                # Get the key name for the reference to use in redis
                key = self._make_reference_id()

                # Now, we can go ahead and do the SET in redis for the key
                # Expire as set by the user
                serialized_datum = ser.serialize(datum, method=serialization)
                key = key + ":ser:" + (str(serialization) if serialization is not None else "none")
                _pipe.set(key, serialized_datum, px=px_val, nx=True)
                keys.append(key)
            self.metrics_timing_end(f"atom:reference_create:serialize", pipeline=pipeline)
            self.metrics_timing_start(self.metrics_timing_start(f"atom:reference_create:data"))
            response = _pipe.execute()
            _pipe = self._release_pipeline(_pipe)
            self.metrics_timing_end(f"atom:reference_create:serialize", pipeline=pipeline)
            self.metrics_add((f"atom:reference_create:n", len(data)), pipeline=pipeline)

        if not all(response):
            raise ValueError(f"Failed to create reference! response {response}")

        # Return the key that was generated for the reference
        return keys

    def reference_create_from_stream(self, element, stream, stream_id="", timeout_ms=10000):
        """
        Creates an expiring reference (similar to a pointer) in the atom system.
        This API will take an element and a stream and, depending on the value
        of the stream_id field, will create a reference within Atom without
        the data ever having left Redis. This is optimal for performance and
        memory reasons. If the id arg is "" then we will make a reference
        from the most recent piece of data. If it is a particular ID we will
        make a reference from that piece of data.

        Since streams have multiple key:value pairs, one reference per key
        in the stream will be created, and the return type is a dictionary mapping
        stream keys to references.  The references are named so that the stream key
        is also included in the name of the corresponding reference.

        Args:

            element (string) : Name of the element whose stream we want to
                        make a reference from
            stream (string) : Stream from which we want to make a reference
            id (string) : If "", will use the most recent value from the
                        stream. Else, will try to make a reference from the
                        particular stream ID
            timeout_ms (int): How long the reference should persist in atom
                        unless otherwise extended/deleted. Set to 0 to have the
                        reference never time out (generally a terrible idea)

        Return:
            dictionary mapping stream keys to reference keys. Raises
            an error on failure.
        """

        if self._stream_reference_sha is None:
            raise ValueError("Lua script not loaded -- unable to call reference_create_from_stream")

        if not self._metric_reference_create_from_stream[element][stream]:
            self.metrics_create(f"atom:reference_create_from_stream:data:{element}:{stream}", labels={"severity": "info", "type": "atom_reference_create_from_stream", "detail" : "data"}, use_default_rules=True, default_agg_list=["AVG", "MIN", "MAX"], update=True)

            self._metric_reference_create_from_stream[element][stream] = True

        with MetricsPipeline(self) as pipeline:

            # Make the new reference key
            key = self._make_reference_id()

            # Get the stream we'll be reading from
            stream_name = self._make_stream_id(element, stream)

            self.metrics_timing_start(f"atom:reference_create_from_stream:data:{element}:{stream}")
            # Call the script to make a reference
            _pipe = self._rpipeline_pool.get()
            _pipe.evalsha(self._stream_reference_sha, 0, stream_name, stream_id, key, timeout_ms)
            data = _pipe.execute()
            _pipe = self._release_pipeline(_pipe)
            self.metrics_timing_end(f"atom:reference_create_from_stream:data:{element}:{stream}", pipeline=pipeline)

        if (type(data) != list) or (len(data) != 1) or (type(data[0]) != list):
            raise ValueError("Failed to make reference!")

        # Make a dictionary to return from the response
        key_dict = {}
        for key in data[0]:
            key_val = key.decode().split(':')[-1]
            key_dict[key_val] = key

        return key_dict

    def reference_get(self, *keys, serialization=None, force_serialization=False, deserialize=None):
        """
        Gets one or more reference from the atom system. Reads the key(s) from redis
        and returns the data, performing a serialize/deserialize operation on each
        key as commanded by the user

        Args:
            keys (str): One or more keys of references to get from Atom
            serialization (str, optional): If deserializing, the method of serialization to use; defaults to msgpack.
            force_serialization (bool): Boolean to ignore "ser" key if found
                in favor of the user-passed serialization. Defaults to false.

            Deprecated:
            deserialize (bool, optional): Whether or not to deserialize reference; defaults to False.
        Return:
            List of items corresponding to each reference key passed as an argument
        """

        # Get a metrics pipeline
        with MetricsPipeline(self) as pipeline:

            if not self._metric_reference_get:
                self.metrics_create(f"atom:reference_get:data", labels={"severity": "info", "type": "atom_reference_get", "detail" : "data"}, use_default_rules=True, default_agg_list=["AVG", "MIN", "MAX"], update=True)
                self.metrics_create(f"atom:reference_get:deserialize", labels={"severity": "info", "type": "atom_reference_get", "detail" : "deserialize"}, use_default_rules=True, default_agg_list=["AVG", "MIN", "MAX"], update=True)
                self.metrics_create(f"atom:reference_get:n", labels={"severity": "info", "type": "atom_reference_get", "detail" : "n"}, use_default_rules=True, default_agg_list=["SUM"], update=True)

                self._metric_reference_get = True


            # Get the data
            self.metrics_timing_start(f"atom:reference_get:data")
            _pipe = self._rpipeline_pool.get()
            for key in keys:
                _pipe.get(key)
            data = _pipe.execute()
            _pipe = self._release_pipeline(_pipe)
            self.metrics_timing_end(f"atom:reference_get:data", pipeline=pipeline)

            if type(data) is not list:
                self.metrics_write_pipeline(pipeline)
                raise ValueError(f"Invalid response from redis: {data}")

            self.metrics_timing_start(f"atom:reference_get:deserialize")
            deserialized_data = [ ]
            for key, ref in zip(keys, data):
                # look for serialization method in reference key first; if not present use user specified method
                key_split = key.split(':') if type(key) == str else key.decode().split(':')

                # Need to reformat the data into a dictionary with a "ser"
                #   key like it comes in on entries to use the shared logic function
                get_serialization_data = {}
                if "ser" in key_split:
                    get_serialization_data["ser"] = key_split[key_split.index("ser") + 1]

                # Use the serialization data to get the method for deserializing
                #   according to the user's preference
                serialization = self._get_serialization_method(
                    get_serialization_data,
                    serialization,
                    force_serialization,
                    deserialize
                )

                # Deserialize the data
                deserialized_data.append(ser.deserialize(ref, method=serialization) if ref is not None else None)
            self.metrics_timing_end(f"atom:reference_get:deserialize", pipeline=pipeline)

        return deserialized_data

    def reference_delete(self, *keys):
        """
        Deletes one or more references and cleans up their memory

        Args:
            keys (strs): Keys of references to delete from Atom
        """

        # Unlink the data
        _pipe = self._rpipeline_pool.get()
        for key in keys:
            _pipe.delete(key)
        data = _pipe.execute()
        _pipe = self._release_pipeline(_pipe)

        if type(data) is not list:
            raise ValueError(f"Invalid response from redis: {data}")
        if all(data) != 1:
            raise KeyError(f"Reference {key} not in redis")

    def reference_update_timeout_ms(self, key, timeout_ms):
        """
        Updates the timeout for an existing reference. This might want to
        be done as we won't know exactly how long we'll need the key for
        at the original point in time for which we created it

        Args:
            key (str): Key of a reference for which we want to update the
                        timeout
            timeout_ms (int): Timeout at which we want the key to expire.
                        Pass <= 0 for no timeout, i.e. never expire (generally
                        a terrible idea)

        """
        _pipe = self._rpipeline_pool.get()

        # Call pexpeire to set the timeout in ms if we got a positive
        #   nonzero timeout, else call persist to remove any existing
        #   timeout
        if timeout_ms > 0:
            _pipe.pexpire(key, timeout_ms)
        else:
            _pipe.persist(key)

        data = _pipe.execute()
        _pipe = self._release_pipeline(_pipe)

        # Make sure there's only one value in the data return
        if type(data) != list and len(data) != 1:
            raise ValueError(f"Invalid response from redis: {data}")

        if data[0] != 1:
            raise KeyError(f"Reference {key} not in redis")

    def reference_get_timeout_ms(self, key):
        """
        Get the current amount of ms left on the reference. Mainly useful
        for debug I'd imagine. Returns -1 if no timeout, else the timeout
        in ms.

        Args:
            key (str):  Key of a reference for which we want to get the
                        timeout ms for.
        """
        _pipe = self._rpipeline_pool.get()
        _pipe.pttl(key)
        data = _pipe.execute()
        _pipe = self._release_pipeline(_pipe)

        if type(data) != list and len(data) != 1:
            raise ValueError(f"Invalid response from redis: {data}")

        if data[0] == -2:
            raise KeyError(f"Reference {key} doesn't exist")

        return data[0]

    def metrics_get_pipeline(self):
        """
        Returns a metrics pipeline
        """
        if not self._metrics_enabled:
            return None

        return self._get_metrics_pipeline()

    def metrics_create(self, key, retention=60000, labels=None, rules=None, update=False, use_default_rules=False, default_agg_list=[]):
        """
        Create a metric at the given key with retention and labels.

        NOTE: not able to be done asynchronously -- there is too much internal
        back and forth with the redis server. This call will always make
        writes out to the metrics redis.

        Args:
            key (str): Key to use for the metric
            retention (int, optional): How long to keep data for the metric,
                in milliseconds. Default 60000ms == 1 minute. Be careful with
                this, it will grow unbounded if set to 0.
            labels (dictionary, optional): Optional labels to add to the
                data. Each key should be a string and each value should also
                be a string.
            rules (dictionary, optional): Optional dictionary of rules to apply
                to the metric using TS.CREATERULE (https://oss.redislabs.com/redistimeseries/commands/#tscreaterule)
                Each key in the dictionary should be a new time series key and
                the value should be a tuple with the following items:
                    [0]: aggregation type (str, one of: avg, sum, min, max, range, count, first, last, std.p, std.s, var.p, var.s)
                    [1]: aggregation time bucket (int, milliseconds over which to perform aggregation)
                    [2]: aggregation retention, i.e. how long to keep this aggregated stat for
            update (boolean, optional): We will call TS.CREATE to attempt to
                create the key. If this is FALSE (default) we'll return TRUE. If this
                is set to TRUE, then if the key already exists we'll do the following:
                    1. call TS.INFO on the key to ket its current labels and rules
                    2. call TS.ALTER to set the new retention value and labels
                    3. delete all existing rules
                    4. Add in the new rules
                This should result in the key matching the spec provided without
                    ever causing a failed insert on the key as it will always
                    exist and the key is never deleted.
            use_default_rules: If set the TRUE will use the default downsampling/retention
                rules. This keeps raw metrics for 24hr at high fidelity, then
                creates 3 day retention at 10m fidelity, 30 day retention at 1h
                fidelity and 365 day retention at 1 day fidelity.
            default_agg_list: If using the default retention strategy, this
                is a list of the aggregation we want done at those intervals

        Return:
            boolean, true on success
        """

        if not self._metrics_enabled:
            return False

        # Replace the user-passed key with the metric ID
        _key = self._make_metric_id(self.name, key)
        # Add in the default labels
        _labels = self._metric_add_default_labels(labels)

        # If using default rules, override the retention
        if use_default_rules:
            retention = METRICS_DEFAULT_RETENTION

        # Try to make the key. Need to know if the key already exists in order
        #   to figure out if this will fail
        _pipe = self._get_metrics_pipeline()
        _pipe.create(_key, retention_msecs=retention, labels=_labels)
        data = self._write_metrics_pipeline(_pipe, error_ok="TSDB: key already exists")

        # If we failed to create the key it already exists. If
        #   we want to update we'll go ahead and do so, otherwise
        #   we will just fail out here.
        if not data and not update:
            return False

        # If we need to update the key, delete all existing rules
        #   and call ALTER to change retention and labels
        if update:

            # Need to get info about the key
            _pipe = self._get_metrics_pipeline()
            _pipe.info(_key)
            data = self._write_metrics_pipeline(_pipe)
            if not data:
                return False

            _pipe = self._get_metrics_pipeline()

            # If we have any rules, delete them
            if len(data[0].rules) > 0:
                for rule in data[0].rules:
                    _pipe.deleterule(_key, rule[0])

            # Now we want to alter the rule to match our new retention and
            #   labels
            _pipe.alter(_key, retention_msecs=retention, labels=_labels)

            data = self._write_metrics_pipeline(_pipe)
            if not data:
                return False

        # If we want to use the default aggregation rules we just iterate
        #   over the time buckets and apply the aggregation types requested
        if use_default_rules:
            _rules = {}
            for agg in default_agg_list:
                for rule in METRICS_DEFAULT_AGG_RULES:
                    _rules[f"{key}:{rule[0]}:{agg}"] = (agg, rule[1], rule[2])
        # Otherwise we'll use the raw rules the user gave us
        else:
            _rules = rules

        # If we have new rules to add, add them
        if _rules:
            _pipe = self._get_metrics_pipeline()
            for rule in _rules.keys():
                rule_key = self._make_metric_id(self.name, rule)
                _pipe.create(rule_key, retention_msecs=_rules[rule][2], labels=_labels)
                _pipe.createrule(_key, rule_key, _rules[rule][0], _rules[rule][1])
            data = self._write_metrics_pipeline(_pipe)
            if not data:
                return False

        return True

    def metrics_add(self, *metrics, use_curr_time=False, pipeline=None):
        """
        Adds a metric at the given key with the given value. Timestamp
            can be set if desired, leaving at the default of '*' will result
            in using the redis-server's timestamp which is usually good enough.

        NOTE: The metric MUST have been created with metrics_create before calling
            metric_add. Otherwise, this will error out

        Args:
            metrics: one or more (key, value, timestamp) tuples where the
                data is of the format:
                    key (str): Key to use for the metric
                    value (int/float): Value to be adding to the time series
                    timetamp (int, optional): Timestamp to use for the value in the time
                        series. Leave at default to use the redis server's built-in
                        timestamp.
                NOTE: If use_curr_time is true then the timestamp field is
                    ignored and the tuples can be two entries long. Else, if the
                    values are still two entries long then we'll just use the
                    '*' argument for the timestamp.
            use_curr_time (bool, optional): If TRUE, ignores timestamp argument
                and sets the timestamp to the current wallclock time in
                milliseconds. This is useful for async patterns where you don't
                know how long it will take for the timestamp to get to the
                redis server. NOTE: execute = TRUE triggers the same behavior.
            pipeline (redis pipeline, optional): Leave NONE (default) to send the metric to
                the redis server in this function call. Pass a pipeline to just have
                the data added to the pipeline which you will need to flush later

        Return:
            list of integers representing the timestamps created. None on
                failure.
        """
        if not self._metrics_enabled:
            return None

        if not pipeline:
            _pipe = self._get_metrics_pipeline()
        else:
            _pipe = pipeline

        # Make the list of metrics for the single metrics addition call
        madd_list = []
        for metric in metrics:
            if len(metric) == 2:
                if use_curr_time or pipeline != None:
                    timestamp_val = int(round(time.time() * 1000))
                else:
                    timestamp_val = '*'
            elif len(metric) == 3:
                timestamp_val = metric[2]
            else:
                raise AtomError(f"Metric value {metric} not 2 or 3 entries long -- consult docs")

            madd_list.append((self._make_metric_id(self.name, metric[0]), timestamp_val, metric[1]))

        _pipe.madd(madd_list)

        data = None
        if not pipeline:
            data = self._write_metrics_pipeline(_pipe)

            if data:
                for i, val in enumerate(data):
                    for j, timestamp in enumerate(val):
                        if isinstance(timestamp, redis.exceptions.ResponseError):
                            self.log(LogLevel.ERR, f"metrics add error: {timestamp}")
                            val[j] = None

        # Since we're using madd instead of add (in order to not auto-create)
        #   we need to extract the outer list here for simplicity.
        return data

    def metrics_write_pipeline(self, pipeline, error_ok=None):
        """
        Write out a pipeline

        return:
            list of lists. Each sublist in the return is the return of calling
            execute on any outstanding pipeline. Length of the list returned
            is equal to the number of pipelines flushed.
        """
        if not self._metrics_enabled:
            return None

        return self._write_metrics_pipeline(pipeline, error_ok=error_ok)

    def metrics_timing_start(self, key):
        """
        Simple helper function to do the keeping-track-of-time for
        timing-based metrics.

        Args:
            key (string): Key we want to start tracking timing for
        """
        self._metric_timing[key] = time.monotonic()

    def metrics_timing_end(self, key, pipeline=None):
        """
        Simple helper function to finish a time that was being kept
        track of and write out the metric
        """
        if key not in self._metric_timing:
            raise AtomError(f"key {key} timer not started!")

        delta = time.monotonic() - self._metric_timing[key]
        self.metrics_add((key, delta), pipeline=pipeline)

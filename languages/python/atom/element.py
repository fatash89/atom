from __future__ import annotations

import copy
import logging
import logging.handlers
import multiprocessing
import os
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime
from multiprocessing import Process
from os import uname
from queue import Empty as QueueEmpty
from queue import LifoQueue, Queue
from traceback import format_exc
from typing import Any, Callable, Optional, Union

import redis
from redis.client import Pipeline
from redistimeseries.client import Client as RedisTimeSeries
from redistimeseries.client import Pipeline as RedisTimeSeriesPipeline
from typing_extensions import Literal

import atom.serialization as ser
from atom.config import (
    ACK_TIMEOUT,
    ATOM_CALLBACK_FAILED,
    ATOM_COMMAND_NO_ACK,
    ATOM_COMMAND_NO_RESPONSE,
    ATOM_COMMAND_UNSUPPORTED,
    ATOM_INTERNAL_ERROR,
    ATOM_NO_ERROR,
    ATOM_USER_ERRORS_BEGIN,
    COMMAND_LIST_COMMAND,
    DEFAULT_METRICS_PORT,
    DEFAULT_METRICS_SOCKET,
    DEFAULT_REDIS_PORT,
    DEFAULT_REDIS_SOCKET,
    HEALTHCHECK_COMMAND,
    HEALTHCHECK_RETRY_INTERVAL,
    LANG,
    LOG_DEFAULT_FILE_SIZE,
    LOG_DEFAULT_LEVEL,
    MAX_BLOCK,
    METRICS_AGGREGATION_LABEL,
    METRICS_AGGREGATION_TYPE_LABEL,
    METRICS_ATOM_VERSION_LABEL,
    METRICS_DEFAULT_AGG_TIMING,
    METRICS_DEFAULT_RETENTION,
    METRICS_DEVICE_LABEL,
    METRICS_ELEMENT_LABEL,
    METRICS_HOST_LABEL,
    METRICS_LANGUAGE_LABEL,
    METRICS_LEVEL_LABEL,
    METRICS_SUBTYPE_LABEL,
    METRICS_TYPE_LABEL,
    OVERRIDE_PARAM_FIELD,
    REDIS_PIPELINE_POOL_SIZE,
    RESERVED_COMMANDS,
    RESERVED_PARAM_FIELDS,
    RESPONSE_TIMEOUT,
    SERIALIZATION_PARAM_FIELD,
    STREAM_LEN,
    VERSION,
    VERSION_COMMAND,
    MetricsLevel,
)
from atom.messages import (
    ENTRY_RESERVED_KEYS,
    Acknowledge,
    Cmd,
    Entry,
    LogLevel,
    Response,
    StreamHandler,
    format_redis_py,
)

# Need to figure out how we're connecting to the Nucleus
#   Default to local sockets at the default address
ATOM_NUCLEUS_HOST = os.getenv("ATOM_NUCLEUS_HOST", None)
ATOM_METRICS_HOST = os.getenv("ATOM_METRICS_HOST", None)
ATOM_NUCLEUS_PORT = int(os.getenv("ATOM_NUCLEUS_PORT", str(DEFAULT_REDIS_PORT)))
ATOM_METRICS_PORT = int(os.getenv("ATOM_METRICS_PORT", str(DEFAULT_METRICS_PORT)))
ATOM_NUCLEUS_SOCKET = os.getenv("ATOM_NUCLEUS_SOCKET", DEFAULT_REDIS_SOCKET)
ATOM_METRICS_SOCKET = os.getenv("ATOM_METRICS_SOCKET", DEFAULT_METRICS_SOCKET)

# Get the log directory and log file size
ATOM_LOG_DIR = os.getenv("ATOM_LOG_DIR", "")
ATOM_LOG_FILE_SIZE = int(os.getenv("ATOM_LOG_FILE_SIZE", LOG_DEFAULT_FILE_SIZE))


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


class SetEmptyError(Exception):
    def __init__(self, *args):
        if args:
            self.message = args[0]
        else:
            self.message = None

    def __str__(self):
        if self.message:
            return f"Set Empty: {self.message}"
        else:
            return "Atom set is empty"


class RedisPipeline:
    """
    Wrapper around obtaining and releasing redis pipelines to make sure
    we don't leak any
    """

    def __init__(self, element: Element):
        self.element = element

    def __enter__(self):
        self.pipeline = self.element._rpipeline_pool.get()
        return self.pipeline

    def __exit__(self, type, value, traceback):
        self.element._release_pipeline(self.pipeline)


class MetricsPipeline:
    """
    Wrapper around obtaining and releasing metrics pipelines to make
    sure we don't leak any
    """

    def __init__(self, element: Element):
        self.element = element

    def __enter__(self):
        self.pipeline = self.element.metrics_get_pipeline()
        return self.pipeline

    def __exit__(self, type, value, traceback):
        self.element.metrics_write_pipeline(self.pipeline)


class Element:
    def __init__(
        self,
        name: str,
        host: Optional[str] = ATOM_NUCLEUS_HOST,
        port: int = ATOM_NUCLEUS_PORT,
        metrics_host: Optional[str] = ATOM_METRICS_HOST,
        metrics_port: int = ATOM_METRICS_PORT,
        socket_path: str = ATOM_NUCLEUS_SOCKET,
        metrics_socket_path: str = ATOM_METRICS_SOCKET,
        conn_timeout_ms: int = 30000,
        data_timeout_ms: int = 5000,
        enforce_metrics: bool = False,
    ):
        """
        Args:
            name (str): The name of the element to register with Atom.
            host (str, optional): The ip address of the Redis server
            port (int, optional): The port of the Redis server to connect to.
            socket_path (str, optional): Path to Redis Unix socket.
            metrics_host (str, optional): The ip address of the metrics Redis
            metrics_port (int, optional): The port of the metrics Redis server
            metrics_socket_path (str, optional): Path to metrics Redis socket.
            enforce_metrics (bool, optional): While metrics is a relatively new
                feature this will allow an element to connect to a nucleus
                without metrics and fail with a log but not throw an error.
                This enables us to be backwards compatible with older setups.
            conn_timeout_ms (int, optional): The number of milliseconds to wait
                                             before timing out when establishing
                                             a Redis connection
            data_timeout_ms (int, optional): The number of milliseconds to wait
                                             before timing out while waiting for
                                             data back over a Redis connection.
        """

        self.name = name
        self.host = uname().nodename
        self.handler_map: dict[str, Any] = {}
        self.timeouts: dict[str, int] = {}
        self._redis_connection_timeout = float(conn_timeout_ms / 1000.0)
        self._redis_data_timeout = float(data_timeout_ms / 1000.0)
        assert (
            self._redis_connection_timeout > 0
        ), "timeout must be positive and non-zero"
        self.streams: set[str] = set()
        self._rclient: Optional[redis.StrictRedis] = None
        self._command_loop_shutdown = multiprocessing.Event()
        self._rpipeline_pool: "Queue[Pipeline]" = Queue()
        self._mpipeline_pool: "LifoQueue[RedisTimeSeriesPipeline]" = LifoQueue()
        self._timed_out = False
        self._pid = os.getpid()
        self._cleaned_up = False
        self.processes: list[Process] = []
        self._redis_connected = False

        #
        # Set up metrics
        #
        self._metrics: set[str] = set()
        self._metrics_add_type_keys = set()
        self._metrics_enabled = False
        self._active_timing_metrics: dict[str, float] = {}
        self._command_metrics = defaultdict(lambda: {})
        self._command_loop_metrics = defaultdict(lambda: {})
        self._command_send_metrics = defaultdict(lambda: defaultdict(lambda: None))
        self._entry_read_n_metrics = defaultdict(lambda: defaultdict(lambda: None))
        self._entry_read_since_metrics = defaultdict(lambda: defaultdict(lambda: None))
        self._entry_write_metrics = defaultdict(lambda: None)
        self._parameter_metrics = defaultdict(lambda: {})
        self._counter_metrics = defaultdict(lambda: {})
        self._sorted_set_metrics = defaultdict(lambda: {})
        self._reference_create_metrics: dict[str, str] = None
        self._reference_create_from_stream_metrics = defaultdict(
            lambda: defaultdict(lambda: None)
        )
        self._reference_get_metrics: dict[str, str] = None
        self._reference_delete_metrics: dict[str, str] = None

        #
        # Set up metrics logging levels
        #
        self._metrics_level: MetricsLevel = MetricsLevel[
            os.getenv("ATOM_METRICS_LEVEL", "TIMING")
        ]
        self._metrics_use_aggregation = (
            os.getenv("ATOM_METRICS_USE_AGGREGATION", "FALSE") == "TRUE"
        )

        #
        # Set up logger
        #
        logger = logging.getLogger(self.name)
        try:
            rfh = logging.handlers.RotatingFileHandler(
                f"{ATOM_LOG_DIR}{self.name}.log", maxBytes=ATOM_LOG_FILE_SIZE
            )
        except FileNotFoundError as e:
            raise AtomError(f"Invalid element name for logger: {e}")

        extra = {"element_name": self.name}
        formatter = logging.Formatter(
            "%(asctime)s element:%(element_name)s [%(levelname)s] %(message)s"
        )
        rfh.setFormatter(formatter)
        logger.addHandler(rfh)
        self.logger = logging.LoggerAdapter(logger, extra)

        #
        # Set up log level
        #
        loglevel = os.getenv("ATOM_LOG_LEVEL", LOG_DEFAULT_LEVEL)
        numeric_level = getattr(logging, loglevel.upper(), None)
        if not isinstance(numeric_level, int):
            loglevel = LOG_DEFAULT_LEVEL
        self.logger.setLevel(loglevel)

        self._mclient: RedisTimeSeries
        # For now, only enable metrics if turned on in an environment flag
        if os.getenv("ATOM_USE_METRICS", "FALSE") == "TRUE":

            # Set up redis client for metrics
            if metrics_host is not None and metrics_host != "":
                self._metrics_host = metrics_host
                self._metrics_port = metrics_port
                self._mclient = RedisTimeSeries(
                    host=self._metrics_host,
                    port=self._metrics_port,
                    socket_timeout=self._redis_data_timeout,
                    socket_connect_timeout=self._redis_connection_timeout,
                    client_name=self.name,
                )
            else:
                self._metrics_socket_path = metrics_socket_path
                self._mclient = RedisTimeSeries(
                    unix_socket_path=self._metrics_socket_path,
                    socket_connect_timeout=self._redis_connection_timeout,
                    client_name=self.name,
                )

            try:
                data = self._mclient.redis.ping()
                if not data:
                    # Don't have redis, so need to only print to stdout
                    self.logger.warning(
                        f"Invalid ping response {data} from metrics server"
                    )

                # Create pipeline pool
                for i in range(REDIS_PIPELINE_POOL_SIZE):
                    self._mpipeline_pool.put(self._mclient.pipeline(transaction=False))

                self.logger.info("Metrics initialized.")
                self._metrics_enabled = True

            except (
                redis.exceptions.TimeoutError,
                redis.exceptions.RedisError,
                redis.exceptions.ConnectionError,
            ) as e:
                self.logger.error(f"Unable to connect to metrics server, error {e}")
                if enforce_metrics:

                    # Clean up the redis part of the element since that
                    #   was initialized OK
                    self._clean_up()

                    raise AtomError("Unable to connect to metrics server")

        #
        # Set up Atom
        #

        # Set up redis client for main redis
        if host is not None and host != "":
            self._host = host
            self._port = port
            self._rclient = redis.StrictRedis(
                host=self._host,
                port=self._port,
                socket_timeout=self._redis_data_timeout,
                socket_connect_timeout=self._redis_connection_timeout,
                client_name=self.name,
            )
        else:
            self._socket_path = socket_path
            self._rclient = redis.StrictRedis(
                unix_socket_path=socket_path,
                socket_connect_timeout=self._redis_connection_timeout,
                client_name=self.name,
            )

        try:
            data = self._rclient.ping()
            if not data:
                # Don't have redis, so need to only print to stdout
                self.logger.warning(f"Invalid ping response {data} from redis server!")

        except redis.exceptions.TimeoutError:
            self._timed_out = True
            raise ElementConnectionTimeoutError()

        except redis.exceptions.RedisError:
            raise AtomError("Could not connect to nucleus!")

        # Note we connected to redis
        self._redis_connected = True

        # Init our pool of redis clients/pipelines
        for i in range(REDIS_PIPELINE_POOL_SIZE):
            self._rpipeline_pool.put(self._rclient.pipeline(transaction=False))

        _pipe = self._rpipeline_pool.get()

        # increment global element ref counter
        self._increment_command_group_counter(_pipe)

        _pipe.xadd(
            self._make_response_id(self.name),
            {"language": LANG, "version": VERSION},
            maxlen=STREAM_LEN,
        )
        # Keep track of response_last_id to know last time the client's
        #   response stream was read from
        self.response_last_id = _pipe.execute()[-1].decode()
        self.response_last_id_lock = threading.Lock()

        _pipe.xadd(
            self._make_command_id(self.name),
            {"language": LANG, "version": VERSION},
            maxlen=STREAM_LEN,
        )
        # Keep track of command_last_id to know last time the element's command
        #   stream was read from
        self.command_last_id = _pipe.execute()[-1].decode()
        _pipe = self._release_pipeline(_pipe)

        # Init a default healthcheck, overridable
        # By default, if no healthcheck is set, we assume everything is ok and
        #   return error code 0
        self.healthcheck_set(lambda: Response())
        # Need to make sure we have metrics on the healthcheck command
        self._command_add_init_metrics(HEALTHCHECK_COMMAND)

        # Init a version check callback which reports our language/version
        current_major_version = ".".join(VERSION.split(".")[:-1])
        self.command_add(
            VERSION_COMMAND,
            lambda: Response(
                data={"language": LANG, "version": float(current_major_version)},
                serialization="msgpack",
            ),
        )

        # Add command to query all commands
        self.command_add(
            COMMAND_LIST_COMMAND,
            lambda: Response(
                data=[k for k in self.handler_map if k not in RESERVED_COMMANDS],
                serialization="msgpack",
            ),
        )

        # Load lua scripts
        self._stream_reference_sha = None
        this_dir, this_filename = os.path.split(__file__)
        with open(os.path.join(this_dir, "stream_reference.lua")) as f:
            data = f.read()
            _pipe = self._rpipeline_pool.get()
            _pipe.script_load(data)
            script_response = _pipe.execute()
            _pipe = self._release_pipeline(_pipe)

            if (
                (not isinstance(script_response, list))
                or (len(script_response) != 1)
                or (not isinstance(script_response[0], str))
            ):
                self.logger.error("Failed to load lua script stream_reference.lua")
            else:
                self._stream_reference_sha = script_response[0]

        self.logger.info("Element initialized.")

    def __repr__(self):
        return f"{self.__class__.__name__}({self.name})"

    def clean_up_stream(self, stream: str) -> None:
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
        self._rclient.unlink(self._make_stream_id(self.name, stream))
        self.streams.remove(stream)

    def _clean_up(self) -> None:
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

    def _clean_up_streams(self) -> None:
        # if we have encountered a connection timeout there's no use
        # in re-attempting stream cleanup commands as they will implicitly
        # cause the redis pool to reconnect and trigger a subsequent
        # timeout incurring ~2x the intended timeout in some contexts
        if self._timed_out:
            return

        for stream in self.streams.copy():
            self.clean_up_stream(stream)
        try:
            self._rclient.unlink(self._make_response_id(self.name))
            self._rclient.unlink(self._make_command_id(self.name))
            self._rclient.unlink(self._make_consumer_group_counter(self.name))
        except redis.exceptions.RedisError:
            raise Exception("Could not connect to nucleus!")

    def _release_pipeline(self, pipeline: Pipeline, metrics: bool = False) -> None:
        """
        Resets the specified pipeline and returns it to the pool of available
            pipelines.

        Args:
            pipeline (Redis Pipeline): The pipeline to release
        """
        pipeline.reset()
        self._rpipeline_pool.put(pipeline)
        return None

    def _update_response_id_if_older(self, new_id: str) -> None:
        """
        Atomically update global response_last_id to new id, if timestamp on new
            id is more recent

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
        if new_id_time > global_id_time or (
            new_id_time == global_id_time and new_id_seq > global_id_seq
        ):
            self.response_last_id = new_id
        self.response_last_id_lock.release()

    def _make_response_id(self, element_name: str) -> str:
        """
        Creates the string representation for a element's response stream id.

        Args:
            element_name (str): Name of the element to generate the id for.
        """
        return f"response:{element_name}"

    def _make_command_id(self, element_name: str) -> str:
        """
        Creates the string representation for an element's command stream id.

        Args:
            element_name (str): Name of the element to generate the id for.
        """
        return f"command:{element_name}"

    def _make_consumer_group_counter(self, element_name: str) -> str:
        """
        Creates the string representation for an element's command group
        stream counter id.

        Args:
            element_name (str): Name of the element to generate the id for.
        """
        return f"command_consumer_group_counter:{element_name}"

    def _make_consumer_group_id(self, element_name: str) -> str:
        """
        Creates the string representation for an element's command group
        stream id.

        Args:
            element_name (str): Name of the element to generate the id for.
        """
        return f"command_consumer_group:{element_name}"

    def _make_stream_id(self, element_name: str, stream_name: str) -> str:
        """
        Creates the string representation of an element's stream id.

        Args:
            element_name (str): Name of the element to generate the id for.
            stream_name (str): Name of element_name's stream to generate the id
                for.
        """
        if element_name is None:
            return stream_name
        else:
            return f"stream:{element_name}:{stream_name}"

    def _make_metric_id(self, element_name: str, m_type: str, *m_subtypes) -> str:
        """
        Creates the string representation of a metric ID created by an
        element

        Args:
            element_name (str): Name of the element to generate the metric ID
                for
            key: Original key passed by the caller
        """
        key_str = f"{element_name}:{m_type}"
        for subtype in m_subtypes:
            key_str += f":{subtype}"
        return key_str

    def _metrics_add_default_labels(
        self, labels: dict, level, m_type: str, *m_subtypes
    ) -> dict:
        """
        Adds the default labels that come from atom. Default labels will
        be things such as the element, perhaps host, type and all subtypes

        Args:
            labels: Original dictionary of labels
            level: Metrics level
            m_type: Type of the metric
            m_subtypes: List of subtypes for the metric

        Raises:
            AtomError: if a reserved label key is used
        """

        # Make the default labels
        default_labels = {}
        default_labels[METRICS_ELEMENT_LABEL] = self.name
        default_labels[METRICS_TYPE_LABEL] = m_type
        default_labels[METRICS_HOST_LABEL] = os.uname()[-1]
        default_labels[METRICS_DEVICE_LABEL] = os.getenv("ATOM_DEVICE_ID", "default")
        default_labels[METRICS_LANGUAGE_LABEL] = LANG
        default_labels[METRICS_ATOM_VERSION_LABEL] = VERSION
        default_labels[METRICS_LEVEL_LABEL] = level.name
        for i, subtype in enumerate(m_subtypes):
            default_labels[METRICS_SUBTYPE_LABEL + str(i)] = subtype

        # If we have pre-existing labels, make sure they don't have any
        #   reserved keys and then return the combined dictionaries
        if labels:
            for label in labels:
                if label in default_labels:
                    raise AtomError(f"'{label}' is a reserved key in labels")

            return {**labels, **default_labels}
        # Otherwise just return the defaults
        else:
            return default_labels

    def _metrics_validate_labels(self, labels: dict) -> None:
        if "" in labels.values():
            raise AtomError("Metrics labels cannot include empty strings")

    def _make_reference_id(self, key: Optional[str] = None) -> str:
        """
        Creates a reference ID

        Args:
            key (str, optional): User specified key; defaults to None
        Returns:
            Full reference key that includes element name
        """
        key = key if key else str(uuid.uuid4())
        return f"reference:{self.name}:{key}"

    def _get_redis_timestamp(self) -> str:
        """
        Gets the current timestamp from Redis.
        """
        secs, msecs = self._rclient.time()
        timestamp = str(secs) + str(msecs).zfill(6)[:3]
        return timestamp

    def _decode_entry(self, entry: dict) -> dict:
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

    def _deserialize_entry(self, entry: dict, method: Optional[str] = None) -> dict:
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
                except Exception:
                    pass
        return entry

    def _check_element_version(
        self,
        element_name: str,
        supported_language_set: Optional[set] = None,
        supported_min_version: Optional[float] = None,
    ) -> bool:
        """
        Convenient helper function to query an element about whether it meets
            min language and version requirements for some feature

        Args:
            element_name (str): Name of the element to query
            supported_language_set (set, optional): Optional set of supported
                languages target element must be a part of to pass
            supported_min_version (float, optional): Optional min version
                target element must meet to pass
        """
        # Check if element is reachable and supports the version command
        response = self.get_element_version(element_name)
        if response["err_code"] != ATOM_NO_ERROR or type(response["data"]) is not dict:
            return False
        # Check for valid response to version command
        if not (
            "version" in response["data"]
            and "language" in response["data"]
            and type(response["data"]["version"]) is float
        ):
            return False
        # Validate element meets language requirement
        if (
            supported_language_set
            and response["data"]["language"] not in supported_language_set
        ):
            return False
        # Validate element meets version requirement
        if (
            supported_min_version
            and response["data"]["version"] < supported_min_version
        ):
            return False
        return True

    def _get_serialization_method(
        self,
        data: dict,
        user_serialization: Optional[str],
        force_serialization: bool,
        deserialize: Optional[bool] = None,
    ) -> Optional[str]:
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

    def _redis_scan_keys(self, pattern: str) -> list[str]:
        """
        Scan redis for all keys matching the pattern. Will use redis SCAN
            under the hood since KEYS is not recommended/suitable for
            production environments.

        Args:
            pattern (string): Match pattern to search across keys
        """

        matches = []
        cursor = 0

        # Loop until we get a cursor of 0
        while True:

            # Get a pipeline and do a scan
            with RedisPipeline(self) as redis_pipeline:
                redis_pipeline.scan(cursor, match=pattern)
                cursor, new_matches = redis_pipeline.execute()[0]

            # Take the elements we got back and add them to the list of elements
            for match in new_matches:
                matches.append(match.decode())

            # When we get a cursor back of 0 then we are done
            if cursor == 0:
                break

        return matches

    def get_all_elements(self) -> list[str]:
        """
        Gets the names of all the elements connected to the Redis server.

        Returns:
            List of element ids connected to the Redis server.
        """

        matches = self._redis_scan_keys(self._make_response_id("*"))
        return [x.split(":")[-1] for x in matches]

    def get_all_streams(self, element_name: str = "*") -> list[str]:
        """
        Gets the names of all the streams of the specified element
            (all by default).

        Args:
            element_name (str): Name of the element of which to get the streams
                from.

        Returns:
            List of Stream ids belonging to element_name
        """
        return self._redis_scan_keys(self._make_stream_id(element_name, "*"))

    def get_element_version(self, element_name: str) -> dict:
        """
        Queries the version info for the given element name.

        Args:
            element_name (str): Name of the element to query

        Returns:
            A dictionary of the response from the command.
        """
        return self.command_send(
            element_name, VERSION_COMMAND, "", serialization="msgpack"
        )

    def get_all_commands(
        self, element_name: Optional[str] = None, ignore_caller: bool = True
    ) -> list[str]:
        """
        Gets the names of the commands of the specified element
            (all elements by default).

        Args:
            element_name (str): Name of the element of which to get the
                commands.
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
            if self._check_element_version(element, {"Python"}, 0.3):
                # Retrieve commands for each element
                elem_commands = self.command_send(
                    element, COMMAND_LIST_COMMAND, serialization="msgpack"
                )["data"]
                # Rename each command pre-pending the element name
                command_list.extend(
                    [f"{element}:{command}" for command in elem_commands]
                )
        return command_list

    def _command_add_init_metrics(self, name: str) -> None:
        """
        Create the metrics for a new command. Puts the command's metric
        keys into its dictionary structure so they can be added to in a more
        performant fashion moving forward

        Args:
            name (str): Name of the command
        """

        # Number of times a commmand is called
        self._command_metrics[name]["count"] = self.metrics_create(
            MetricsLevel.INFO, "atom:command", "count", name, agg_types=["SUM"]
        )

        # Make the metric for timing the command handler
        self._command_metrics[name]["runtime"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:command",
            "runtime",
            name,
            agg_types=["AVG", "MIN", "MAX"],
        )

        # Make the error counter for the command handler
        self._command_metrics[name]["failed"] = self.metrics_create(
            MetricsLevel.ERR, "atom:command", "failed", name, agg_types=["SUM"]
        )
        self._command_metrics[name]["unhandled"] = self.metrics_create(
            MetricsLevel.CRIT, "atom:command", "unhandled", name, agg_types=["SUM"]
        )
        self._command_metrics[name]["error"] = self.metrics_create(
            MetricsLevel.ERR, "atom:command", "error", name, agg_types=["SUM"]
        )

    def command_add(
        self,
        name: str,
        handler: Callable,
        timeout: int = RESPONSE_TIMEOUT,
        serialization: Optional[str] = None,
        deserialize: Optional[bool] = None,
    ) -> None:
        """
        Adds a command to the element for another element to call.

        Args:
            name (str): Name of the command.
            handler (callable): Function to call given the command name.
            timeout (int, optional): Time for the caller to wait for the command
                to finish.
            serialization (str, optional): The method of serialization to use;
                defaults to None.

            Deprecated:
            deserialize (bool, optional): Whether or not to deserialize the data
                using msgpack before passing it to the handler.
        """
        if not callable(handler):
            raise TypeError("Passed in handler is not a function!")
        if name in RESERVED_COMMANDS and name in self.handler_map:
            raise ValueError(
                f"'{name}' is a reserved command name dedicated to {name} "
                "commands, choose another name"
            )

        if deserialize is not None:  # check for deprecated legacy mode
            serialization = "msgpack" if deserialize else None

        if not ser.is_valid_serialization(serialization):
            raise ValueError(
                f'Invalid serialization method "{serialization}".'
                "Must be one of {ser.Serializations.print_values()}."
            )

        self.handler_map[name] = {"handler": handler, "serialization": serialization}

        self.timeouts[name] = timeout

        # Make the metric for the command
        self._command_add_init_metrics(name)

    def healthcheck_set(self, handler: Callable) -> None:
        """
        Sets a custom healthcheck callback

        Args:
            handler (callable): Function to call when evaluating whether this
                element is healthy or not. Should return a Response with
                err_code ATOM_NO_ERROR if healthy.
        """
        if not callable(handler):
            raise TypeError("Passed in handler is not a function!")
        # Handler must return response with 0 error_code to pass healthcheck
        self.handler_map[HEALTHCHECK_COMMAND] = {
            "handler": handler,
            "serialization": None,
        }
        self.timeouts[HEALTHCHECK_COMMAND] = RESPONSE_TIMEOUT

    def wait_for_elements_healthy(
        self,
        element_list: list[str],
        retry_interval: float = HEALTHCHECK_RETRY_INTERVAL,
        strict: bool = False,
    ) -> None:
        """
        Blocking call will wait until all elements in the element respond that
            they are healthy.

        Args:
            element_list ([str]): List of element names to run healthchecks on
                Should return a Response with err_code ATOM_NO_ERROR if healthy.
            retry_interval (float, optional) Time in seconds to wait before
                retrying after a failed attempt.
            strict (bool, optional) In strict mode, all elements must be
                reachable and support healthchecks to pass. If false, elements
                that don't have healthchecks will be assumed healthy.
        """

        while True:
            all_healthy = True
            for element_name in element_list:
                # Verify element is reachable and supports healthcheck feature
                if not self._check_element_version(
                    element_name,
                    supported_language_set={LANG},
                    supported_min_version=0.2,
                ):
                    # In strict mode, if element is not reachable or doesn't
                    #   support healthchecks, assume unhealthy
                    if strict:
                        self.logger.warning(
                            f"Failed healthcheck on {element_name}, retrying..."
                        )
                        all_healthy = False
                        break
                    else:
                        continue

                response = self.command_send(element_name, HEALTHCHECK_COMMAND, "")
                if response["err_code"] != ATOM_NO_ERROR:
                    self.logger.warning(
                        f"Failed healthcheck on {element_name}, retrying..."
                    )
                    all_healthy = False
                    break
            if all_healthy:
                break

            time.sleep(retry_interval)

    def command_loop(
        self,
        n_procs: int = 1,
        block: bool = True,
        read_block_ms: int = 1000,
        join_timeout: Optional[float] = None,
    ) -> None:
        """Main command execution event loop

        For each worker process, performs the following event loop:
            - Waits for command to be put in element's command stream consumer
              group
            - Sends Acknowledge to caller and then runs command
            - Returns Response with processed data to caller

        Args:
            n_procs (integer): Number of worker processes.  Each worker process
                will pull work from the Element's shared command consumer group
                (defaults to 1).
            block (bool, optional): Wait for the response before returning
                from the function
            read_block_ms (integer, optional): Number of milliseconds to block
                for during a stream read insde of a command loop.
            join_timeout (float, optional): If block=True, how long to wait
                while joining threads at the end of the command loop before
                raising an exception
        """
        # update self._pid in case e.g. we were constructed in a parent thread
        #   but `command_loop` was explicitly called as a sub-process
        self._pid = os.getpid()
        n_procs = int(n_procs)
        if n_procs <= 0:
            raise ValueError("n_procs must be a positive integer")

        # note: This warning is emitted in situations where the calling process
        #   has more than one active thread.  When the command_loop children
        #   processes are forked they will only copy the thread state of the
        #   active thread which invoked the fork.  Other active thread state
        #   will *not* be copied to these descendent processes.  This may cause
        #   some problems with proper execution of the Element's command_loop
        #   if the command depends on this thread state being available on the
        #   descendent processes. Please see the following Stack Overflow link
        #   for more context:
        #       https://stackoverflow.com/questions/39890363/what-happens-when-a-thread-forks # noqa W505
        thread_count = threading.active_count()
        if thread_count > 1:
            self.logger.warning(
                f"[element:{self.name}] Active thread count is currently {thread_count}.  Child command_loop "
                "processes will only copy one active thread's state and therefore may not "
                "work properly."
            )

        self.processes = []
        for i in range(n_procs):
            p = Process(
                target=self._command_loop,
                args=(
                    self._command_loop_shutdown,
                    i,
                ),
                kwargs={"read_block_ms": read_block_ms},
            )
            p.start()
            self.processes.append(p)

        if block:
            self._command_loop_join(join_timeout=join_timeout)

    def _increment_command_group_counter(self, _pipe: Pipeline) -> Any:
        """Incremeents reference counter for element stream collection"""
        _pipe.incr(self._make_consumer_group_counter(self.name))
        result = _pipe.execute()[-1]
        self.logger.debug(f"incrementing element {self.name} {result}")
        return result

    def _decrement_command_group_counter(self, _pipe: Pipeline) -> Any:
        """Decrements reference counter for element stream collection"""
        _pipe.decr(self._make_consumer_group_counter(self.name))
        result = _pipe.execute()[-1]
        if not result:
            self._clean_up_streams()
        return result

    def _command_loop_init_metrics(self, worker_num: int) -> None:
        """
        All of the metric creation calls for the command loop.

        NOTE: Technically workers will be in their own process so we really
        don't need the two-level dict with _command_loop_metrics. That said
        we may have some users who want to use threads in order to share state
        and we might as well take a small performance hit here to support it
        without running into subtle bugs down the line.

        Args:
            worker_num (int): Which command loop worker we are.
        """

        self._command_loop_metrics[worker_num]["block_time"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:command_loop",
            worker_num,
            "block_time",
            labels={"worker": f"{worker_num}"},
            agg_types=["AVG", "MIN", "MAX"],
        )
        self._command_loop_metrics[worker_num][
            "block_handler_time"
        ] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:command_loop",
            worker_num,
            "block_handler_time",
            labels={"worker": f"{worker_num}"},
            agg_types=["AVG", "MIN", "MAX"],
        )
        self._command_loop_metrics[worker_num]["handler_time"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:command_loop",
            worker_num,
            "handler_time",
            labels={"worker": f"{worker_num}"},
            agg_types=["AVG", "MIN", "MAX"],
        )
        self._command_loop_metrics[worker_num][
            "handler_block_time"
        ] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:command_loop",
            worker_num,
            "handler_block_time",
            labels={"worker": f"{worker_num}"},
            agg_types=["AVG", "MIN", "MAX"],
        )

        # Info counters
        self._command_loop_metrics[worker_num]["n_commands"] = self.metrics_create(
            MetricsLevel.INFO,
            "atom:command_loop",
            worker_num,
            "n_commands",
            labels={"worker": f"{worker_num}"},
            agg_types=["SUM"],
        )

        # Error counters
        self._command_loop_metrics[worker_num][
            "xreadgroup_error"
        ] = self.metrics_create(
            MetricsLevel.ERR,
            "atom:command_loop",
            worker_num,
            "xreadgroup_error",
            labels={"worker": f"{worker_num}"},
            agg_types=["SUM"],
        )
        self._command_loop_metrics[worker_num][
            "stream_match_error"
        ] = self.metrics_create(
            MetricsLevel.ERR,
            "atom:command_loop",
            worker_num,
            "stream_match_error",
            labels={"worker": f"{worker_num}"},
            agg_types=["SUM"],
        )
        self._command_loop_metrics[worker_num]["no_caller"] = self.metrics_create(
            MetricsLevel.ERR,
            "atom:command_loop",
            worker_num,
            "no_caller",
            labels={"worker": f"{worker_num}"},
            agg_types=["SUM"],
        )
        self._command_loop_metrics[worker_num][
            "unsupported_command"
        ] = self.metrics_create(
            MetricsLevel.ERR,
            "atom:command_loop",
            worker_num,
            "unsupported_command",
            labels={"worker": f"{worker_num}"},
            agg_types=["SUM"],
        )
        self._command_loop_metrics[worker_num]["unhandled"] = self.metrics_create(
            MetricsLevel.CRIT,
            "atom:command_loop",
            worker_num,
            "unhandled",
            labels={"worker": f"{worker_num}"},
            agg_types=["SUM"],
        )
        self._command_loop_metrics[worker_num]["failed"] = self.metrics_create(
            MetricsLevel.ERR,
            "atom:command_loop",
            worker_num,
            "failed",
            labels={"worker": f"{worker_num}"},
            agg_types=["SUM"],
        )
        self._command_loop_metrics[worker_num]["response_error"] = self.metrics_create(
            MetricsLevel.ERR,
            "atom:command_loop",
            worker_num,
            "response_error",
            labels={"worker": f"{worker_num}"},
            agg_types=["SUM"],
        )
        self._command_loop_metrics[worker_num]["xack_error"] = self.metrics_create(
            MetricsLevel.ERR,
            "atom:command_loop",
            worker_num,
            "xack_error",
            labels={"worker": f"{worker_num}"},
            agg_types=["SUM"],
        )

    def _command_loop(
        self, shutdown_event, worker_num: int, read_block_ms: int = 1000
    ) -> None:
        client_name = f"{self.name}-command-loop-{worker_num}"
        if hasattr(self, "_host"):
            _rclient = redis.StrictRedis(
                host=self._host, port=self._port, client_name=client_name
            )
        else:
            _rclient = redis.StrictRedis(
                unix_socket_path=self._socket_path, client_name=client_name
            )

        # get a group handle
        # note: if use_command_last_id is set then the group will receive
        #   messages newer than the most recent command id observed by the
        #   Element class.  However, by default it will than accept
        #   messages newer than the creation of the consumer group.
        #
        stream_name = self._make_command_id(self.name)
        group_name = self._make_consumer_group_id(self.name)
        group_last_cmd_id = self.command_last_id
        try:
            _rclient.xgroup_create(
                stream_name, group_name, group_last_cmd_id, mkstream=True
            )
        except redis.exceptions.ResponseError:
            # If we encounter a `ResponseError` we assume it's because of a
            #   `BUSYGROUP` signal, implying the consumer group already exists
            #   for this command.
            #
            # Thus, we go on our merry way as we can successfully proceed
            #   pulling from the already created group :)
            pass
        # make a new uuid for the consumer name
        consumer_uuid = str(uuid.uuid4())

        # Initialize metrics
        self._command_loop_init_metrics(worker_num)

        while not shutdown_event.is_set():

            with MetricsPipeline(self) as pipeline:

                # Get oldest new command from element's command stream
                # note: consumer group consumer id is implicitly announced
                try:

                    # Pre-block metrics
                    self.metrics_timing_start(
                        self._command_loop_metrics[worker_num]["block_time"]
                    )

                    # Block, get a command
                    cmd_responses = _rclient.xreadgroup(
                        group_name,
                        consumer_uuid,
                        {stream_name: ">"},
                        block=read_block_ms,
                        count=1,
                    )

                    # Post-block metrics
                    self.metrics_timing_end(
                        self._command_loop_metrics[worker_num]["block_time"],
                        pipeline=pipeline,
                    )
                    self.metrics_timing_start(
                        self._command_loop_metrics[worker_num]["block_handler_time"]
                    )
                except redis.exceptions.ResponseError:
                    self.logger.error(
                        f"Recieved redis ResponseError.  Possible attempted "
                        "XREADGROUP on closed stream %s (is shutdown: %s).  "
                        "Please ensure you have performed the command_loop_shutdown"
                        " command on the object running command_loop."
                        % (stream_name, shutdown_event.is_set())
                    )
                    self.metrics_add(
                        self._command_loop_metrics[worker_num]["xreadgroup_error"],
                        1,
                        pipeline=pipeline,
                    )
                    return

                if not cmd_responses:
                    continue
                cmd_stream_name, msgs = cmd_responses[0]
                if cmd_stream_name.decode() != stream_name:
                    self.metrics_add(
                        self._command_loop_metrics[worker_num]["stream_match_error"],
                        1,
                        pipeline=pipeline,
                    )
                    raise RuntimeError(
                        "Expected received stream name to match: %s %s"
                        % (cmd_stream_name, stream_name)
                    )

                assert len(msgs) == 1, "expected one message: %s" % (msgs,)

                msg = msgs[0]  # we only read one
                cmd_id, cmd = msg

                # Set the command_last_id to this command's id to keep track of
                #   our last read
                self.command_last_id = cmd_id.decode()

                try:
                    caller = cmd[b"element"].decode()
                    cmd_name = cmd[b"cmd"].decode()
                    data = cmd[b"data"]
                except KeyError:
                    # Ignore non-commands
                    continue

                if not caller:
                    self.logger.error("No caller name present in command!")
                    self.metrics_add(
                        (f"atom:command_loop:worker{worker_num}:no_caller", 1)
                    )
                    continue

                # Send acknowledge to caller
                if cmd_name not in self.timeouts.keys():
                    timeout = RESPONSE_TIMEOUT
                else:
                    timeout = self.timeouts[cmd_name]
                acknowledge = Acknowledge(self.name, cmd_id, timeout)

                _rclient.xadd(
                    self._make_response_id(caller), vars(acknowledge), maxlen=STREAM_LEN
                )

                # Send response to caller
                if cmd_name not in self.handler_map.keys():
                    self.logger.error("Received unsupported command: %s" % (cmd_name,))
                    response = Response(
                        err_code=ATOM_COMMAND_UNSUPPORTED,
                        err_str="Unsupported command.",
                    )
                    self.metrics_add(
                        self._command_loop_metrics[worker_num]["unsupported_command"],
                        1,
                        pipeline=pipeline,
                    )
                else:

                    # Pre-handler metrics
                    self.metrics_timing_end(
                        self._command_loop_metrics[worker_num]["block_handler_time"],
                        pipeline=pipeline,
                    )
                    self.metrics_timing_start(
                        self._command_loop_metrics[worker_num]["handler_time"]
                    )
                    self.metrics_timing_start(
                        self._command_metrics[cmd_name]["runtime"]
                    )

                    if cmd_name not in RESERVED_COMMANDS:
                        if (
                            "deserialize" in self.handler_map[cmd_name]
                        ):  # check for deprecated legacy mode
                            serialization = (
                                "msgpack"
                                if self.handler_map[cmd_name]["deserialize"]
                                else None
                            )
                        else:
                            serialization = self.handler_map[cmd_name]["serialization"]
                        data = ser.deserialize(data, method=serialization)
                        try:
                            response = self.handler_map[cmd_name]["handler"](data)

                        except Exception:
                            self.logger.error(
                                "encountered error with command: %s\n%s"
                                % (cmd_name, format_exc())
                            )
                            response = Response(
                                err_code=ATOM_INTERNAL_ERROR,
                                err_str="encountered an internal exception "
                                "during command execution: %s" % (cmd_name,),
                            )
                            self.metrics_add(
                                self._command_loop_metrics[worker_num]["unhandled"],
                                1,
                                pipeline=pipeline,
                            )
                            self.metrics_add(
                                self._command_metrics[cmd_name]["unhandled"],
                                1,
                                pipeline=pipeline,
                            )

                    else:
                        # healthcheck/version requests/command_list commands
                        #   don't care what data you are sending
                        response = self.handler_map[cmd_name]["handler"]()

                    # Post-handler-metrics
                    self.metrics_timing_end(
                        self._command_metrics[cmd_name]["runtime"], pipeline=pipeline
                    )
                    self.metrics_timing_end(
                        self._command_loop_metrics[worker_num]["handler_time"],
                        pipeline=pipeline,
                    )

                    # Add ATOM_USER_ERRORS_BEGIN to err_code to map to element
                    #   error range
                    if isinstance(response, Response):
                        if response.err_code != 0:
                            response.err_code += ATOM_USER_ERRORS_BEGIN
                            self.metrics_add(
                                self._command_metrics[cmd_name]["error"],
                                1,
                                pipeline=pipeline,
                            )

                    else:
                        response = Response(
                            err_code=ATOM_CALLBACK_FAILED,
                            err_str=f"Return type of {cmd_name} is not of type Response",
                        )
                        self.metrics_add(
                            self._command_loop_metrics[worker_num]["failed"],
                            1,
                            pipeline=pipeline,
                        )
                        self.metrics_add(
                            self._command_metrics[cmd_name]["failed"],
                            1,
                            pipeline=pipeline,
                        )

                    # Note we called the command and got through it
                    self.metrics_add(
                        self._command_metrics[cmd_name]["count"], 1, pipeline=pipeline
                    )

                # Need to start the handler <> block time
                self.metrics_timing_start(
                    self._command_loop_metrics[worker_num]["handler_block_time"]
                )

                # send response on appropriate stream
                kv = vars(response)
                kv["cmd_id"] = cmd_id
                kv["element"] = self.name
                kv["cmd"] = cmd_name
                try:
                    _rclient.xadd(self._make_response_id(caller), kv, maxlen=STREAM_LEN)
                except Exception:
                    # If we fail to xadd the response, go ahead and continue
                    # we will xack the response to bring it out of pending list.
                    # This command will be treated as being "handled" and will
                    # not be re-attempted
                    self.metrics_add(
                        self._command_loop_metrics[worker_num]["response_error"],
                        1,
                        pipeline=pipeline,
                    )

                # `XACK` the command we have just completed back to the consumer
                # group to remove the command from the consumer group pending
                # entry list (PEL).
                try:
                    _rclient.xack(stream_name, group_name, cmd_id)
                    self.metrics_add(
                        self._command_loop_metrics[worker_num]["n_commands"],
                        1,
                        pipeline=pipeline,
                    )
                except Exception:
                    self.logger.error(
                        "encountered error during xack (stream name:%s, group name: "
                        "%s, cmd_id: %s)\n%s"
                        % (stream_name, group_name, cmd_id, format_exc())
                    )
                    self.metrics_add(
                        self._command_loop_metrics[worker_num]["xack_error"],
                        1,
                        pipeline=pipeline,
                    )

                # we're essentially going into the block and if we wrap it up
                # here we don't need to handle edge cases where it hadn't
                # been started before
                self.metrics_timing_end(
                    self._command_loop_metrics[worker_num]["handler_block_time"],
                    pipeline=pipeline,
                )

    def _command_loop_join(self, join_timeout: Optional[float] = 10.0) -> None:
        """Waits for all threads from command loop to be finished"""
        for p in self.processes:
            p.join(join_timeout)

    def command_loop_shutdown(
        self, block: bool = False, join_timeout: float = 10.0
    ) -> None:
        """Triggers graceful exit of command loop"""
        self._command_loop_shutdown.set()
        if block:
            self._command_loop_join(join_timeout=join_timeout)

    def _command_send_init_metrics(self, element_name: str, cmd_name: str) -> None:
        """
        Create all of the metrics for a command send call

        Args:
            element_name (str): Name of the element we're calling
            cmd_name (str): Name of the command we're calling
        """

        # If we already have something non-None in there, return out
        if self._command_send_metrics[element_name][cmd_name]:
            return

        # Otherwise, we proceed and make the metrics and their dictionary

        self._command_send_metrics[element_name][cmd_name] = {}

        self._command_send_metrics[element_name][cmd_name][
            "serialize"
        ] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:command_send",
            "serialize",
            element_name,
            cmd_name,
            agg_types=["AVG", "MIN", "MAX"],
        )
        self._command_send_metrics[element_name][cmd_name][
            "runtime"
        ] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:command_send",
            "runtime",
            element_name,
            cmd_name,
            agg_types=["AVG", "MIN", "MAX"],
        )
        self._command_send_metrics[element_name][cmd_name][
            "deserialize"
        ] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:command_send",
            "deserialize",
            element_name,
            cmd_name,
            agg_types=["AVG", "MIN", "MAX"],
        )
        self._command_send_metrics[element_name][cmd_name][
            "error"
        ] = self.metrics_create(
            MetricsLevel.ERR,
            "atom:command_send",
            "error",
            element_name,
            cmd_name,
            agg_types=["SUM"],
        )

    def command_send(
        self,
        element_name: str,
        cmd_name: str,
        data="",
        block: bool = True,
        ack_timeout: int = ACK_TIMEOUT,
        serialization: Optional[str] = None,
        serialize: Optional[bool] = None,
        deserialize: Optional[bool] = None,
    ) -> dict:
        """
        Sends command to element and waits for acknowledge.
        When acknowledge is received, waits for timeout from acknowledge or
            until response is received.

        Args:
            element_name (str): Name of the element to send the command to.
            cmd_name (str): Name of the command to execute of element_name.
            data: Entry to be passed to the function specified by cmd_name.
            block (bool): Wait for the response before returning from the
                function.
            ack_timeout (int, optional): Time in milliseconds to wait for ack
                before timing out, overrides default value.
            serialization (str, optional): Method of serialization to use;
                defaults to None.

            Deprecated:
            serialize (bool, optional): Whether or not to serialize the data
                with msgpack before sending it to the command; defaults to None.
            deserialize (bool, optional): Whether or not to deserialize the data
                with msgpack in the response; defaults to None.

        Returns:
            A dictionary of the response from the command.
        """
        # cache the last response id at the time we are issuing this command,
        #   since this can get overwritten
        local_last_id = self.response_last_id
        timeout = None
        resp = None
        data = format_redis_py(data)

        # Initialize the metrics for sending this command
        self._command_send_init_metrics(element_name, cmd_name)

        # Get a metrics pipeline
        with MetricsPipeline(self) as pipeline:

            # Send command to element's command stream
            if serialize is not None:  # check for deprecated legacy mode
                serialization = "msgpack" if serialize else None

            self.metrics_timing_start(
                self._command_send_metrics[element_name][cmd_name]["serialize"]
            )
            data = ser.serialize(data, method=serialization) if (data != "") else data
            self.metrics_timing_end(
                self._command_send_metrics[element_name][cmd_name]["serialize"],
                pipeline=pipeline,
            )

            self.metrics_timing_start(
                self._command_send_metrics[element_name][cmd_name]["runtime"]
            )
            cmd = Cmd(self.name, cmd_name, data)
            _pipe = self._rpipeline_pool.get()
            _pipe.xadd(
                self._make_command_id(element_name), vars(cmd), maxlen=STREAM_LEN
            )
            cmd_id = _pipe.execute()[-1].decode()
            _pipe = self._release_pipeline(_pipe)

            # Receive acknowledge from element
            # You have no guarantee that the response from the xread is for your
            #   specific thread, so keep trying until we either receive our ack,
            #   or timeout is exceeded
            start_read = time.time()
            elapsed_time_ms = (time.time() - start_read) * 1000
            while True:
                responses = self._rclient.xread(
                    {self._make_response_id(self.name): local_last_id},
                    block=max(int(ack_timeout - elapsed_time_ms), 1),
                )
                if not responses:
                    elapsed_time_ms = (time.time() - start_read) * 1000
                    if elapsed_time_ms >= ack_timeout:
                        err_str = f"Did not receive acknowledge from {element_name}."
                        self.logger.error(err_str)
                        self.metrics_add(
                            self._command_send_metrics[element_name][cmd_name]["error"],
                            1,
                            pipeline=pipeline,
                        )
                        return vars(
                            Response(err_code=ATOM_COMMAND_NO_ACK, err_str=err_str)
                        )
                        break
                    else:
                        continue

                stream, msgs = responses[0]  # we only read one stream
                for id, response in msgs:
                    local_last_id = id.decode()

                    if (
                        b"element" in response
                        and response[b"element"].decode() == element_name
                        and b"cmd_id" in response
                        and response[b"cmd_id"].decode() == cmd_id
                        and b"timeout" in response
                    ):
                        timeout = int(response[b"timeout"].decode())
                        break

                    self._update_response_id_if_older(local_last_id)

                # If the response we received wasn't for this command, keep
                #   trying until ack timeout
                if timeout is not None:
                    break

            if timeout is None:
                err_str = f"Did not receive acknowledge from {element_name}."
                self.logger.error(err_str)
                self.metrics_add(
                    self._command_send_metrics[element_name][cmd_name]["error"],
                    1,
                    pipeline=pipeline,
                )
                return vars(Response(err_code=ATOM_COMMAND_NO_ACK, err_str=err_str))

            # Receive response from element
            # You have no guarantee that the response from the xread is for your
            #   specific thread, so keep trying until we either receive our
            #   response, or timeout is exceeded
            start_read = time.time()
            while True:
                elapsed_time_ms = (time.time() - start_read) * 1000
                if elapsed_time_ms >= timeout:
                    break

                responses = self._rclient.xread(
                    {self._make_response_id(self.name): local_last_id},
                    block=max(int(timeout - elapsed_time_ms), 1),
                )
                if not responses:
                    err_str = f"Did not receive response from {element_name}."
                    self.logger.error(err_str)
                    self.metrics_add(
                        self._command_send_metrics[element_name][cmd_name]["error"],
                        1,
                        pipeline=pipeline,
                    )
                    return vars(
                        Response(err_code=ATOM_COMMAND_NO_RESPONSE, err_str=err_str)
                    )

                stream_name, msgs = responses[0]  # we only read from one stream
                for msg in msgs:
                    id, response = msg
                    local_last_id = id.decode()

                    if (
                        b"element" in response
                        and response[b"element"].decode() == element_name
                        and b"cmd_id" in response
                        and response[b"cmd_id"].decode() == cmd_id
                        and b"err_code" in response
                    ):

                        self.metrics_timing_end(
                            self._command_send_metrics[element_name][cmd_name][
                                "runtime"
                            ],
                            pipeline=pipeline,
                        )
                        self.metrics_timing_start(
                            self._command_send_metrics[element_name][cmd_name][
                                "deserialize"
                            ]
                        )

                        err_code = int(response[b"err_code"].decode())
                        err_str = (
                            response[b"err_str"].decode()
                            if b"err_str" in response
                            else ""
                        )
                        if err_code != ATOM_NO_ERROR:
                            self.logger.error(err_str)

                        response_data = response.get(b"data", "")
                        # check response for serialization method; if not
                        #   present, use user specified method
                        if b"ser" in response:
                            serialization = response[b"ser"].decode()
                        elif (
                            deserialize is not None
                        ):  # check for deprecated legacy mode
                            serialization = "msgpack" if deserialize else None

                        try:
                            response_data = (
                                ser.deserialize(response_data, method=serialization)
                                if (len(response_data) != 0)
                                else response_data
                            )
                        except TypeError:
                            self.logger.warning("Could not deserialize response.")
                            self.metrics_add(
                                (
                                    f"atom:command_send:error:{element_name}:{cmd_name}",
                                    1,
                                )
                            )

                        self.metrics_timing_end(
                            self._command_send_metrics[element_name][cmd_name][
                                "deserialize"
                            ],
                            pipeline=pipeline,
                        )

                        # Make the final response
                        resp = vars(
                            Response(
                                data=response_data, err_code=err_code, err_str=err_str
                            )
                        )
                        break

                self._update_response_id_if_older(local_last_id)
                if resp is not None:
                    return resp

                # If the response we received wasn't for this command, keep
                #   trying until timeout
                continue

            # Proper response was not in responses
            err_str = f"Did not receive response from {element_name}."
            self.logger.error(err_str)
            self.metrics_add(
                self._command_send_metrics[element_name][cmd_name]["error"],
                1,
                pipeline=pipeline,
            )

        return vars(Response(err_code=ATOM_COMMAND_NO_RESPONSE, err_str=err_str))

    def entry_read_loop(
        self,
        stream_handlers: Sequence[StreamHandler],
        n_loops: Optional[int] = None,
        timeout: int = MAX_BLOCK,
        serialization: Optional[str] = None,
        force_serialization: bool = False,
        deserialize: Optional[bool] = None,
    ) -> None:
        """
        Listens to streams and pass any received entry to corresponding handler.

        Args:
            stream_handlers (list of messages.StreamHandler):
            n_loops (int): Number of times to send the stream entry to the
                handlers.
            timeout (int): How long to block on the stream. If surpassed, the
                unction returns.
            serialization (str, optional): If deserializing, the method of
                serialization to use; defaults to None.
            force_serialization (bool): Boolean to ignore "ser" key if found
                in favor of the user-passed serialization. Defaults to false.

            Deprecated:
            deserialize (bool, optional): Whether or not to deserialize the
                entries using msgpack; defaults to None.
        """
        if n_loops is None:
            # Create an infinite loop
            loop_iter = iter(int, 1)
        else:
            loop_iter = range(n_loops)

        streams = {}
        stream_handler_map = {}
        for stream_handler in stream_handlers:
            if not isinstance(stream_handler, StreamHandler):
                raise TypeError(f"{stream_handler} is not a StreamHandler!")
            stream_id = self._make_stream_id(
                stream_handler.element, stream_handler.stream
            )
            streams[stream_id] = self._get_redis_timestamp()
            stream_handler_map[stream_id] = stream_handler.handler
        for _ in loop_iter:
            stream_entries = self._rclient.xread(streams, block=timeout)
            if not stream_entries:
                return
            for stream, msgs in stream_entries:
                for uid, entry in msgs:
                    streams[stream] = uid
                    entry = self._decode_entry(entry)
                    serialization = self._get_serialization_method(
                        entry, serialization, force_serialization, deserialize
                    )
                    entry = self._deserialize_entry(entry, method=serialization)
                    entry["id"] = uid.decode()
                    stream_handler_map[stream.decode()](entry)

    def _entry_read_n_init_metrics(self, element_name: str, stream_name: str) -> None:
        """
        Initialize metrics for reading from an element's stream

        Args:
            element_name (str): name of the element we're reading from
            stream_name (str): name of the stream we're reading from
        """

        # If we've already initialized this, return
        if self._entry_read_n_metrics[element_name][stream_name]:
            return

        self._entry_read_n_metrics[element_name][stream_name] = {}

        self._entry_read_n_metrics[element_name][stream_name][
            "data"
        ] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:entry_read_n",
            "data",
            element_name,
            stream_name,
            agg_types=["AVG", "MIN", "MAX"],
        )
        self._entry_read_n_metrics[element_name][stream_name][
            "deserialize"
        ] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:entry_read_n",
            "deserialize",
            element_name,
            stream_name,
            agg_types=["AVG", "MIN", "MAX"],
        )
        self._entry_read_n_metrics[element_name][stream_name][
            "n"
        ] = self.metrics_create(
            MetricsLevel.INFO,
            "atom:entry_read_n",
            "n",
            element_name,
            stream_name,
            agg_types=["SUM"],
        )

    def entry_read_n(
        self,
        element_name: str,
        stream_name: str,
        n: int,
        serialization: Optional[str] = None,
        force_serialization: bool = False,
        deserialize: Optional[bool] = None,
    ) -> list[dict]:
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
            deserialize (bool, optional): Whether or not to deserialize the
                entries using msgpack; defaults to None.

        Returns:
            List of dicts containing the data of the entries
        """

        # Initialize metrics
        self._entry_read_n_init_metrics(element_name, stream_name)

        # Get a metrics pipeline
        with MetricsPipeline(self) as pipeline:

            entries = []
            stream_id = self._make_stream_id(element_name, stream_name)

            # Read data
            self.metrics_timing_start(
                self._entry_read_n_metrics[element_name][stream_name]["data"]
            )
            uid_entries = self._rclient.xrevrange(stream_id, count=n)
            self.metrics_timing_end(
                self._entry_read_n_metrics[element_name][stream_name]["data"],
                pipeline=pipeline,
            )

            # Deserialize
            self.metrics_timing_start(
                self._entry_read_n_metrics[element_name][stream_name]["deserialize"]
            )
            for uid, entry in uid_entries:
                entry = self._decode_entry(entry)
                serialization = self._get_serialization_method(
                    entry, serialization, force_serialization, deserialize
                )
                entry = self._deserialize_entry(entry, method=serialization)
                entry["id"] = uid.decode()
                entries.append(entry)
            self.metrics_timing_end(
                self._entry_read_n_metrics[element_name][stream_name]["deserialize"],
                pipeline=pipeline,
            )

            # Note we read entries
            self.metrics_add(
                self._entry_read_n_metrics[element_name][stream_name]["n"],
                len(uid_entries),
                pipeline=pipeline,
            )

        return entries

    def _entry_read_since_init_metrics(
        self, element_name: str, stream_name: str
    ) -> None:
        """
        Initialize metrics for reading from an element's stream

        Args:
            element_name (str): name of the element we're reading from
            stream_name (str): name of the stream we're reading from
        """

        # If we've already initialized this, return
        if self._entry_read_since_metrics[element_name][stream_name]:
            return

        self._entry_read_since_metrics[element_name][stream_name] = {}

        self._entry_read_since_metrics[element_name][stream_name][
            "data"
        ] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:entry_read_since",
            "data",
            element_name,
            stream_name,
            agg_types=["AVG", "MIN", "MAX"],
        )
        self._entry_read_since_metrics[element_name][stream_name][
            "deserialize"
        ] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:entry_read_since",
            "deserialize",
            element_name,
            stream_name,
            agg_types=["AVG", "MIN", "MAX"],
        )
        self._entry_read_since_metrics[element_name][stream_name][
            "n"
        ] = self.metrics_create(
            MetricsLevel.INFO,
            "atom:entry_read_n",
            "n",
            element_name,
            stream_name,
            agg_types=["SUM"],
        )

    def entry_read_since(
        self,
        element_name: str,
        stream_name: str,
        last_id: str = "$",
        n: Optional[int] = None,
        block: Optional[int] = None,
        serialization: Optional[str] = None,
        force_serialization: bool = False,
        deserialize: Optional[bool] = None,
    ) -> list[dict]:
        """
        Read entries from a stream since the last_id.

        Args:
            element_name (str): Name of the element to get the entry from.
            stream_name (str): Name of the stream to get the entry from.
            last_id (str, optional): Time from which to start get entries from.
                If '0', get all entries.
                If '$' (default), get only new entries after the function call
                    (blocking).
            n (int, optional): Number of entries to get. If None, get all.
            block (int, optional): Time (ms) to block on the read. If 0, block
                forever. If None, don't block.
            serialization (str, optional): Method of deserialization to use;
                defaults to None.
            force_serialization (bool): Boolean to ignore "ser" key if found
                in favor of the user-passed serialization. Defaults to false.

            Deprecated:
            deserialize (bool, optional): Whether or not to deserialize the
                entries using msgpack; defaults to None.
        """

        # Initialize metrics
        self._entry_read_since_init_metrics(element_name, stream_name)

        # Get a metrics pipeline
        with MetricsPipeline(self) as pipeline:

            streams, entries = {}, []
            stream_id = self._make_stream_id(element_name, stream_name)
            streams[stream_id] = last_id

            # Read data
            self.metrics_timing_start(
                self._entry_read_since_metrics[element_name][stream_name]["data"]
            )
            stream_entries = self._rclient.xread(streams, count=n, block=block)
            self.metrics_timing_end(
                self._entry_read_since_metrics[element_name][stream_name]["data"],
                pipeline=pipeline,
            )
            stream_names = [x[0].decode() for x in stream_entries]
            if not stream_entries or stream_id not in stream_names:
                return entries

            # Deserialize
            self.metrics_timing_start(
                self._entry_read_since_metrics[element_name][stream_name]["deserialize"]
            )
            for key, msgs in stream_entries:
                if key.decode() == stream_id:
                    for uid, entry in msgs:
                        entry = self._decode_entry(entry)
                        serialization = self._get_serialization_method(
                            entry, serialization, force_serialization, deserialize
                        )
                        entry = self._deserialize_entry(entry, method=serialization)
                        entry["id"] = uid.decode()
                        entries.append(entry)
            self.metrics_timing_end(
                self._entry_read_since_metrics[element_name][stream_name]["data"],
                pipeline=pipeline,
            )

            # Note we read the entries
            self.metrics_add(
                self._entry_read_since_metrics[element_name][stream_name]["n"],
                len(stream_entries),
                pipeline=pipeline,
            )

        return entries

    def _entry_write_init_metrics(self, stream_name: str) -> None:
        """
        Initialize metrics for writing to a stream

        Args:
            stream_name (str): Stream we're writing to
        """

        # If we've already initialized the metrics, no need to worry
        if self._entry_write_metrics[stream_name]:
            return

        self._entry_write_metrics[stream_name] = {}

        self._entry_write_metrics[stream_name]["data"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:entry_write",
            "data",
            stream_name,
            agg_types=["AVG", "MIN", "MAX"],
        )
        self._entry_write_metrics[stream_name]["serialize"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:entry_write",
            "serialize",
            stream_name,
            agg_types=["AVG", "MIN", "MAX"],
        )

    def entry_write(
        self,
        stream_name: str,
        field_data_map: dict,
        maxlen: int = STREAM_LEN,
        serialization: Optional[str] = None,
        serialize: Optional[bool] = None,
    ) -> str:
        """
        Creates element's stream if it does not exist.
        Adds the fields and data to a Entry and puts it in the element's stream.

        Args:
            stream_name (str): The stream to add the data to.
            field_data_map (dict): Dict which creates the Entry. See messages.
                Entry for more usage.
            maxlen (int, optional): The maximum number of data to keep in the
                stream.
            serialization (str, optional): Method of serialization to use;
                defaults to None.

            Deprecated:
            serialize (bool, optional): Whether or not to serialize the entry
                using msgpack; defaults to None.

        Return: ID of item added to stream
        """

        # Initialize metrics
        self._entry_write_init_metrics(stream_name)

        # Get a metrics pipeline
        with MetricsPipeline(self) as pipeline:

            self.streams.add(stream_name)
            field_data_map = format_redis_py(field_data_map)

            if serialize is not None:  # check for deprecated legacy mode
                serialization = "msgpack" if serialize else None

            # Serialize
            self.metrics_timing_start(
                self._entry_write_metrics[stream_name]["serialize"]
            )
            ser_field_data_map = {}
            for k, v in field_data_map.items():
                if k in ENTRY_RESERVED_KEYS:
                    raise ValueError(
                        f'Invalid key "{k}": "{k}" is a reserved entry key'
                    )
                ser_field_data_map[k] = ser.serialize(v, method=serialization)

            ser_field_data_map["ser"] = (
                str(serialization) if serialization is not None else "none"
            )
            entry = Entry(ser_field_data_map)
            self.metrics_timing_end(
                self._entry_write_metrics[stream_name]["serialize"], pipeline=pipeline
            )

            # Write Data
            self.metrics_timing_start(self._entry_write_metrics[stream_name]["data"])
            _pipe = self._rpipeline_pool.get()
            _pipe.xadd(
                self._make_stream_id(self.name, stream_name), vars(entry), maxlen=maxlen
            )
            ret = _pipe.execute()
            _pipe = self._release_pipeline(_pipe)
            self.metrics_timing_end(
                self._entry_write_metrics[stream_name]["data"], pipeline=pipeline
            )

        if (
            (not isinstance(ret, list))
            or (len(ret) != 1)
            or (not isinstance(ret[0], bytes))
        ):
            print(ret)
            raise ValueError("Failed to write data to stream")

        return ret[0].decode()

    def log(
        self,
        level: LogLevel,
        msg: str,
        stdout: bool = True,
        _pipe: Pipeline = None,
        redis: bool = False,
    ) -> None:
        """
        Forwards calls to self.logger
        Args:
            level (messages.LogLevel): Unix syslog severity of message.
            message (str): The message to write for the log.
            stdout (bool, optional): Whether to write to stdout or only write to
                log stream.
            _pipe (pipeline, optional): Pipeline to use for the log message to
                be sent to redis
            redis (bool, optional): Default true, whether to log to
                redis or not
        """

        numeric_level = getattr(logging, level.name.upper(), None)
        if not isinstance(numeric_level, int):
            numeric_level = getattr(logging, LOG_DEFAULT_LEVEL)
        self.logger.log(numeric_level, msg)

    def _parameter_init_metrics(self, key: str) -> None:
        """
        Initialize parameter write metrics
        """

        # If we've already initialized the metrics, no need to worry
        if self._parameter_metrics[key]:
            return

        self._parameter_metrics[key]["write_data"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:parameter",
            key,
            "write_data",
            agg_types=["AVG", "MIN", "MAX", "COUNT"],
        )
        self._parameter_metrics[key]["serialize"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:parameter",
            key,
            "serialize",
            agg_types=["AVG", "MIN", "MAX"],
        )
        self._parameter_metrics[key]["check"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:parameter",
            key,
            "check",
            agg_types=["AVG", "MIN", "MAX"],
        )
        self._parameter_metrics[key]["read_data"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:parameter",
            key,
            "read_data",
            agg_types=["AVG", "MIN", "MAX", "COUNT"],
        )
        self._parameter_metrics[key]["deserialize"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:parameter",
            key,
            "deserialize",
            agg_types=["AVG", "MIN", "MAX"],
        )
        self._parameter_metrics[key]["delete"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:parameter",
            key,
            "delete",
            agg_types=["AVG", "MIN", "MAX", "COUNT"],
        )

    def _make_parameter_key(self, key: str) -> str:
        """
        Prefixes requested key under parameter namespace.
        """
        return f"parameter:{key}"

    def parameter_write(
        self,
        key: str,
        data: dict,
        override: bool = True,
        serialization: Optional[str] = None,
        timeout_ms: int = 0,
    ) -> list[str]:
        """
        Creates a Redis hash store, prefixed under the "parameter:" namespace
        with user specified key. Each field in the data dictionary will be
        stored as a field on the Redis hash. Override and serialization fields
        will be added based on the user-passed args. The store will never
        expire by default and should be explicitly deleted when no longer
        needed.

        If the store already exists under the specified key, the override
        field will be checked. The fields will be updated if override is true,
        otherwise an error will be raised. A parameter's serialization method
        cannot be changed once it is set at the intial write.

        Args:
            key (str): name of parameter to store
            data (dict): dictionary of data fields to store
            override (bool, optional): whether or not hash fields can be
                overwritten
            serialization (str, optional): Method of serialization to use;
                defaults to None.
            timeout_ms (int, optional): How long the reference should persist
                in atom unless otherwise extended/deleted. Defaults to 0 for no
                timeout, i.e. parameter exists until explicitly deleted.
        Returns:
            list of fields written to
        Raises:
            AtomError if key exists and cannot be overridden or a serialization
            method other than the existing one is requested
        """
        redis_key = self._make_parameter_key(key)
        fields = []
        existing_override = None
        serialization = "none" if serialization is None else serialization

        # Initialize metrics
        self._parameter_init_metrics(key)

        # Get a metrics pipeline
        with MetricsPipeline(self) as pipeline:

            _pipe = self._rpipeline_pool.get()

            # Check if parameter exists
            self.metrics_timing_start(self._parameter_metrics[key]["check"])
            _pipe.exists(redis_key)
            key_exists = _pipe.execute()[0]

            if key_exists:
                # Check requested serialization is same as existing
                _pipe.hget(redis_key, SERIALIZATION_PARAM_FIELD)
                existing_ser = _pipe.execute()[0]

                if existing_ser != serialization.encode():
                    raise AtomError(
                        f"Parameter already exists with serialization {existing_ser};"
                        f"any changes must also use {existing_ser} serialization"
                    )

                # Check override setting
                _pipe.hget(redis_key, OVERRIDE_PARAM_FIELD)
                existing_override = _pipe.execute()[0].decode()

                if existing_override == "false":
                    # Check for requested fields
                    for field in data.keys():
                        _pipe.hget(redis_key, field)

                    fields_exist = _pipe.execute()

                    # Raise error if override is false and any requested fields
                    # already exist
                    if any(fields_exist):
                        raise AtomError("Cannot override existing parameter fields")

            self.metrics_timing_end(
                self._parameter_metrics[key]["check"], pipeline=pipeline
            )

            # Serialize
            self.metrics_timing_start(self._parameter_metrics[key]["serialize"])
            for field, datum in data.items():
                # Do the SET in redis for each field
                serialized_datum = ser.serialize(datum, method=serialization)
                _pipe.hset(redis_key, field, serialized_datum)
                fields.append(field)

            self.metrics_timing_end(
                self._parameter_metrics[key]["serialize"], pipeline=pipeline
            )

            # Add serialization field to new parameter
            if not key_exists:
                _pipe.hset(redis_key, SERIALIZATION_PARAM_FIELD, serialization)

            # Add override field if existing override isn't false
            if existing_override != "false":
                override_str = "true" if override is True else "false"
                _pipe.hset(redis_key, OVERRIDE_PARAM_FIELD, override_str)
            elif override is True:
                self.logger.warning("Cannot override existing false override value")

            # Set timeout in ms if nonzero positive
            if timeout_ms > 0:
                _pipe.pexpire(redis_key, timeout_ms)

            # Write data
            self.metrics_timing_start(self._parameter_metrics[key]["write_data"])
            response = _pipe.execute()
            _pipe = self._release_pipeline(_pipe)
            self.metrics_timing_end(
                self._parameter_metrics[key]["write_data"], pipeline=pipeline
            )

            # Finally, we want to log to the debug stream in the metrics
            #   redis about the parameter change. This will make it show up
            #   in the dashboards so we can see what the current/previous
            #   values of parameters have been
            self.metrics_log("parameter_stream", key, data, pipeline=pipeline)

        # Check for valid HSET responses
        if not all([(code == 0 or code == 1) for code in response]):
            raise AtomError(f"Failed to create parameter! response {response}")

        # Return list of all fields written to
        return fields

    def parameter_get_override(self, key: str) -> str:
        """
        Return parameter's override setting

        Args:
            key (str): Parameter key
        Returns:
            (str) "true" or "false" parameter override setting
        Raises:
            AtomError if parameter does not exist
        """
        key = self._make_parameter_key(key)
        _pipe = self._rpipeline_pool.get()
        _pipe.exists(key)
        key_exists = _pipe.execute()[0]
        if not key_exists:
            raise AtomError(f"Parameter {key} does not exist")

        _pipe.hget(key, OVERRIDE_PARAM_FIELD)
        override = _pipe.execute()[0]
        return override.decode()

    def parameter_read(
        self,
        key: str,
        fields: Optional[str] = None,
        serialization: Optional[str] = None,
        force_serialization: bool = False,
    ) -> Optional[dict[bytes, Any]]:
        """
        Gets a parameter from the atom system. Reads the key from redis and
        returns the data, performing a serialize/deserialize operation on each
        field as commanded by the user. Can optionally choose which fields to
        read from the parameter.

        Args:
            key (str): One parameter key to get from Atom
            fields (strs, optional): list of field names to read from parameter
            serialization (str, optional): If deserializing, the method of
                serialization to use; defaults to None.
            force_serialization (bool): Boolean to ignore serialization field if
                found in favor of the user-passed serialization. Defaults to
                false.
        Returns:
            dictionary of data read from the parameter store
        """
        redis_key = self._make_parameter_key(key)

        # Initialize metrics
        self._parameter_init_metrics(key)

        # Get a metrics pipeline
        with MetricsPipeline(self) as pipeline:

            # Get the data
            self.metrics_timing_start(self._parameter_metrics[key]["read_data"])
            _pipe = self._rpipeline_pool.get()
            _pipe.hgetall(redis_key)
            data: dict[bytes, Any] = _pipe.execute()[0]
            _pipe = self._release_pipeline(_pipe)
            self.metrics_timing_end(
                self._parameter_metrics[key]["read_data"], pipeline=pipeline
            )

            self.metrics_timing_start(self._parameter_metrics[key]["deserialize"])
            deserialized_data = {}
            # look for serialization method in parameter first; reformat data
            #   into a dictionary with a "ser" key to use shared logic function
            get_serialization_data = {}
            if SERIALIZATION_PARAM_FIELD.encode() in data.keys():
                get_serialization_data[SERIALIZATION_PARAM_FIELD] = data.pop(
                    SERIALIZATION_PARAM_FIELD.encode()
                )

            # Use the serialization data to get the method for deserializing
            #   according to the user's preference
            serialization = self._get_serialization_method(
                get_serialization_data,
                serialization,
                force_serialization,
            )

            # Deserialize the data
            for field, val in data.items():
                if field.decode() not in RESERVED_PARAM_FIELDS:
                    deserialized_data[field] = (
                        ser.deserialize(val, method=serialization)
                        if val is not None
                        else None
                    )

            self.metrics_timing_end(
                self._parameter_metrics[key]["deserialize"], pipeline=pipeline
            )

        if fields:
            fields_list = [fields] if type(fields) != list else fields
            return_data = {
                field.encode(): deserialized_data[field.encode()]
                for field in fields_list
            }
        else:
            return_data = deserialized_data

        return return_data if return_data else None

    def parameter_delete(self, key: str) -> bool:
        """
        Deletes a parameter and cleans up its memory

        Args:
            keys (str): Key of parameter to delete from Atom

        Return
            success (bool)
        """

        # Initialize metrics
        self._parameter_init_metrics(key)

        with MetricsPipeline(self) as metrics_pipeline:
            self.metrics_timing_start(self._parameter_metrics[key]["delete"])

            success, _ = self._redis_key_delete(self._make_parameter_key(key))

            self.metrics_timing_end(
                self._parameter_metrics[key]["delete"], pipeline=metrics_pipeline
            )

        return success

    def parameter_update_timeout_ms(self, key: str, timeout_ms: int) -> None:
        """
        Updates the timeout for an existing parameter. This might want to
        be done in case we don't want the parameter to live forever.

        Args:
            key (str): Key of a parameter for which we want to update the
                        timeout
            timeout_ms (int): Timeout at which we want the key to expire.
                        Pass <= 0 for no timeout, i.e. never expire (generally
                        a terrible idea)

        """
        self._redis_key_update_timeout_ms(self._make_parameter_key(key), timeout_ms)

    def parameter_get_timeout_ms(self, key: str):
        """
        Get the current amount of ms left on the parameter. Mainly useful
        for debug. Returns -1 if no timeout, else the timeout in ms.

        Args:
            key (str):  Key of a reference for which we want to get the
                        timeout ms for.
        """
        return self._redis_key_get_timeout_ms(self._make_parameter_key(key))

    def _reference_create_init_metrics(self) -> None:
        """
        Initialize reference create metrics
        """

        # If we've already initialized the metrics, no need to worry
        if self._reference_create_metrics:
            return

        self._reference_create_metrics = {}

        self._reference_create_metrics["data"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:reference_create",
            "data",
            agg_types=["AVG", "MIN", "MAX", "COUNT"],
        )
        self._reference_create_metrics["serialize"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:reference_create",
            "serialize",
            agg_types=["AVG", "MIN", "MAX"],
        )

    def reference_create(
        self,
        *data,
        keys=None,
        serialization: Optional[str] = None,
        serialize: Optional[bool] = None,
        timeout_ms: int = 10000,
    ) -> list[str]:
        """
        Creates one or more expiring references (similar to a pointer) in the
        atom system. This will typically be used when we've gotten a piece of
        data from a stream and we want it to persist past the length of time
        it would live in the stream s.t. we can pass it to other commands /
        elements. The references will simply be cached values in redis and
        will expire after the timeout_ms amount of time.

        Args:
            data (binary or object): one or more data items to be included in
                the reference
            keys (strs, optional): keys to use in reference IDs; defaults to
                None, in which case they will be auto-generated UUIDs.
            timeout_ms (int, optional): How long the reference should persist
                in atom unless otherwise extended/deleted. Set to 0 to have the
                reference never time out (generally a terrible idea)
            serialization (str, optional): Method of serialization to use;
                defaults to None.

            Deprecated:
            serialize (bool, optional): whether or not to serialize the data
                using msgpack before creating the reference

        Return:
            List of references corresponding to the arguments passed
        """
        ref_ids = []

        # Make user keys into list and compare the number to data
        keys = [None] * len(data) if keys is None else keys
        keys = [keys] if type(keys) is not list else keys
        if len(data) != len(keys):
            raise Exception("Different number of objects and keys requested")

        # Initialize metrics
        self._reference_create_init_metrics()

        # Get a metrics pipeline
        with MetricsPipeline(self) as pipeline:

            if serialize is not None:  # check for deprecated legacy mode
                serialization = "msgpack" if serialize else None

            _pipe = self._rpipeline_pool.get()
            px_val = timeout_ms if timeout_ms != 0 else None

            # Serialize
            self.metrics_timing_start(self._reference_create_metrics["serialize"])
            for i, datum in enumerate(data):
                # Get the full key name for the reference to use in redis
                key = self._make_reference_id(keys[i])

                # Now, we can go ahead and do the SET in redis for the key
                # Expire as set by the user
                serialized_datum = ser.serialize(datum, method=serialization)
                key = (
                    key
                    + ":ser:"
                    + (str(serialization) if serialization is not None else "none")
                )
                _pipe.set(key, serialized_datum, px=px_val, nx=True)
                ref_ids.append(key)
            self.metrics_timing_end(
                self._reference_create_metrics["serialize"], pipeline=pipeline
            )

            # Write data
            self.metrics_timing_start(self._reference_create_metrics["data"])
            response = _pipe.execute()
            _pipe = self._release_pipeline(_pipe)
            self.metrics_timing_end(
                self._reference_create_metrics["data"], pipeline=pipeline
            )

        if not all(response):
            raise ValueError(f"Failed to create reference! response {response}")

        # Return the key that was generated for the reference
        return ref_ids

    def _reference_create_from_stream_init_metrics(
        self, element: str, stream: str
    ) -> None:
        """
        Initialize the metrics for creating a reference from a stream

        Args:
            element (str): Element whose stream we'll be reading from
            stream (str): Stream we'll be reading from
        """

        # If we've already created the metrics, just return
        if self._reference_create_from_stream_metrics[element][stream]:
            return

        self._reference_create_from_stream_metrics[element][stream] = {}

        self._reference_create_from_stream_metrics[element][stream][
            "data"
        ] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:reference_create_from_stream",
            "data",
            element,
            stream,
            agg_types=["AVG", "MIN", "MAX", "COUNT"],
        )

    def reference_create_from_stream(
        self, element: str, stream: str, stream_id: str = "", timeout_ms: int = 10000
    ) -> dict:
        """
        Creates an expiring reference (similar to a pointer) in the atom system.
        This API will take an element and a stream and, depending on the value
        of the stream_id field, will create a reference within Atom without
        the data ever having left Redis. This is optimal for performance and
        memory reasons. If the id arg is "" then we will make a reference
        from the most recent piece of data. If it is a particular ID we will
        make a reference from that piece of data.

        Since streams have multiple key:value pairs, one reference per key
        in the stream will be created, and the return type is a dictionary
        mapping stream keys to references.  The references are named so that
        the stream key is also included in the name of the corresponding
        reference.

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
            raise ValueError(
                "Lua script not loaded -- unable to call reference_create_from_stream"
            )

        # Initialize metrics
        self._reference_create_from_stream_init_metrics(element, stream)

        with MetricsPipeline(self) as pipeline:

            # Make the new reference key
            key = self._make_reference_id()

            # Get the stream we'll be reading from
            stream_name = self._make_stream_id(element, stream)

            self.metrics_timing_start(
                self._reference_create_from_stream_metrics[element][stream]["data"]
            )
            # Call the script to make a reference
            _pipe = self._rpipeline_pool.get()
            _pipe.evalsha(
                self._stream_reference_sha, 0, stream_name, stream_id, key, timeout_ms
            )
            data = _pipe.execute()
            _pipe = self._release_pipeline(_pipe)
            self.metrics_timing_end(
                self._reference_create_from_stream_metrics[element][stream]["data"],
                pipeline=pipeline,
            )

        if (type(data) != list) or (len(data) != 1) or (type(data[0]) != list):
            raise ValueError("Failed to make reference!")

        # Make a dictionary to return from the response
        key_dict = {}
        for key in data[0]:
            key_val = key.decode().split(":")[-1]
            key_dict[key_val] = key

        return key_dict

    def _reference_get_init_metrics(self) -> None:
        """
        Initialize metrics for getting references
        """

        # If we've already done this, just return out
        if self._reference_get_metrics:
            return

        self._reference_get_metrics = {}

        self._reference_get_metrics["data"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:reference_get",
            "data",
            agg_types=["AVG", "MIN", "MAX", "COUNT"],
        )
        self._reference_get_metrics["deserialize"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:reference_get",
            "deserialize",
            agg_types=["AVG", "MIN", "MAX"],
        )

    def reference_get(
        self,
        *keys,
        serialization: Optional[str] = None,
        force_serialization: bool = False,
        deserialize: Optional[bool] = None,
    ) -> list:
        """
        Gets one or more reference from the atom system. Reads the key(s) from
        redis and returns the data, performing a serialize/deserialize operation
        on each key as commanded by the user

        Args:
            keys (str): One or more keys of references to get from Atom
            serialization (str, optional): If deserializing, the method of
                serialization to use; defaults to msgpack.
            force_serialization (bool): Boolean to ignore "ser" key if found
                in favor of the user-passed serialization. Defaults to false.

            Deprecated:
            deserialize (bool, optional): Whether or not to deserialize
                reference; defaults to False.
        Return:
            List of items corresponding to each reference key passed as an
                argument
        """

        # Initialize metrics
        self._reference_get_init_metrics()

        # Get a metrics pipeline
        with MetricsPipeline(self) as pipeline:

            # Get the data
            self.metrics_timing_start(self._reference_get_metrics["data"])
            _pipe = self._rpipeline_pool.get()
            for key in keys:
                _pipe.get(key)
            data = _pipe.execute()
            _pipe = self._release_pipeline(_pipe)
            self.metrics_timing_end(
                self._reference_get_metrics["data"], pipeline=pipeline
            )

            if type(data) is not list:
                raise ValueError(f"Invalid response from redis: {data}")

            # Deserialize
            self.metrics_timing_start(self._reference_get_metrics["deserialize"])
            deserialized_data = []
            for key, ref in zip(keys, data):
                # look for serialization method in reference key first; if not
                #   present use user specified method
                key_split = (
                    key.split(":") if type(key) == str else key.decode().split(":")
                )

                # Need to reformat the data into a dictionary with a "ser"
                #   key like it comes in on entries to use the shared logic
                #   function
                get_serialization_data = {}
                if "ser" in key_split:
                    get_serialization_data["ser"] = key_split[
                        key_split.index("ser") + 1
                    ]

                # Use the serialization data to get the method for deserializing
                #   according to the user's preference
                serialization = self._get_serialization_method(
                    get_serialization_data,
                    serialization,
                    force_serialization,
                    deserialize,
                )

                # Deserialize the data
                deserialized_data.append(
                    ser.deserialize(ref, method=serialization)
                    if ref is not None
                    else None
                )
            self.metrics_timing_end(
                self._reference_get_metrics["deserialize"], pipeline=pipeline
            )

        return deserialized_data

    def _redis_key_delete(self, *keys) -> tuple[bool, list[str]]:
        """
        Deletes one or more Redis keys and cleans up their memory

        Args:
            keys (strs): Keys to delete from Atom

        Return:
            success (bool), failed_to_delete (list of key)
        """

        # Unlink the data
        with RedisPipeline(self) as redis_pipeline:
            for key in keys:
                redis_pipeline.unlink(key)
            data = redis_pipeline.execute()

        # Make sure we got a valid response from Redis. It's worthwhile
        #   to raise if this is not the case
        if type(data) is not list:
            raise ValueError(f"Invalid response from redis: {data}")

        # Make sure we successfully deleted all references. It's OK
        #   if we didn't, we just need to know
        success = True
        failed = []
        if all(data) != 1:
            success = False
            failed = [key for i, key in enumerate(keys) if data[i] != 1]

        return success, failed

    def _reference_delete_init_metrics(self) -> None:
        """
        Initialize metrics for getting references
        """

        # If we've already done this, just return out
        if self._reference_delete_metrics:
            return

        self._reference_delete_metrics = {}

        self._reference_delete_metrics["delete"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:reference_delete",
            "delete",
            agg_types=["AVG", "MIN", "MAX", "COUNT"],
        )

        self._reference_delete_metrics["count"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:reference_delete",
            "count",
            agg_types=["SUM"],
        )

    def reference_delete(self, *keys) -> tuple[bool, list[str]]:
        """
        Deletes one or more references from Atom

        Args:
            keys (list of reference string): References to delete

        Return:
            success (bool), list of failed keys (list of reference)
        """

        # Initialize metrics
        self._reference_delete_init_metrics()

        with MetricsPipeline(self) as metrics_pipeline:
            self.metrics_timing_start(self._reference_delete_metrics["delete"])

            success, failed = self._redis_key_delete(*keys)

            self.metrics_timing_end(
                self._reference_delete_metrics["delete"], pipeline=metrics_pipeline
            )
            self.metrics_add(self._reference_delete_metrics["count"], len(keys))

        return success, failed

    def _redis_key_update_timeout_ms(self, key: str, timeout_ms: int) -> None:
        """
        Updates the timeout for an existing redis key. This might want to
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

        # Call pexpire to set the timeout in ms if we got a positive
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
            raise KeyError(f"Key {key} not in redis")

    def reference_update_timeout_ms(self, key: str, timeout_ms: int) -> None:
        """
        Updates the timeout for an existing reference
        """
        return self._redis_key_update_timeout_ms(key, timeout_ms)

    def _redis_key_get_timeout_ms(self, key: str) -> int:
        """
        Get the current amount of ms left on the key. Mainly useful
        for debug. Returns -1 if no timeout, else the timeout in ms.

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
            raise KeyError(f"Key {key} doesn't exist")

        return data[0]

    def reference_get_timeout_ms(self, key: str) -> int:
        """
        Return amount of timeout left on reference
        """
        return self._redis_key_get_timeout_ms(key)

    def _make_counter_key(self, key: str) -> str:
        """
        Prefixes requested key under counter namespace.
        """
        return f"counter:{key}"

    def _counter_init_metrics(self, key: str) -> None:
        """
        Initialize the metrics for using a counter
        """

        # If we've already created the metrics, just return
        if self._counter_metrics[key]:
            return

        self._counter_metrics[key]["set"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:counter",
            key,
            "set",
            agg_types=["AVG", "MIN", "MAX", "COUNT"],
        )

        self._counter_metrics[key]["update"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:counter",
            key,
            "update",
            agg_types=["AVG", "MIN", "MAX", "COUNT"],
        )

        self._counter_metrics[key]["get"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:counter",
            key,
            "get",
            agg_types=["AVG", "MIN", "MAX", "COUNT"],
        )

        self._counter_metrics[key]["delete"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:counter",
            key,
            "delete",
            agg_types=["AVG", "MIN", "MAX", "COUNT"],
        )

        self._counter_metrics[key]["value"] = self.metrics_create(
            MetricsLevel.INFO,
            "atom:counter",
            key,
            "value",
            agg_types=["AVG", "MIN", "MAX", "SUM"],
        )

    def counter_set(self, key: str, value: int, timeout_ms: int = 0) -> int:
        """
        Set the value for a shared, atomic counter directly using SET

        Args:
            key (string): Name of the shared counter
            value (int): Integer value of the shared counter. MUST be int
                for this API, though SET under the hood can indeed take
                any value
            timeout_ms (int, optional): How long the counter should live for.
                Default None, i.e. won't expire, but if set will call PEXPIRE
                under the hood to have the value expire after a certain amount
                of time.

        Return:
            Current integer value of the counter

        Raises:
            AtomError on invalid argument
        """

        # Initialize metrics
        self._counter_init_metrics(key)

        # Make sure we have an integer argument
        if type(value) is not int:
            raise AtomError("Counter value must be int!")

        # Get our pipelines
        with RedisPipeline(self) as redis_pipeline, MetricsPipeline(
            self
        ) as metrics_pipeline:

            self.metrics_timing_start(self._counter_metrics[key]["set"])

            # Perform the set
            redis_pipeline.set(self._make_counter_key(key), value)

            # If we have a timeout, put that in the pipeline as well
            if timeout_ms > 0:
                redis_pipeline.pexpire(self._make_counter_key(key), timeout_ms)

            # Execute the pipeline
            response = redis_pipeline.execute()

            self.metrics_timing_end(
                self._counter_metrics[key]["set"], pipeline=metrics_pipeline
            )

            # Response[0] will be True on success, else False
            if not response[0]:
                raise AtomError("Failed to set counter!")

            self.metrics_add(
                self._counter_metrics[key]["value"], value, pipeline=metrics_pipeline
            )

        return value

    def counter_update(self, key: str, value: int, timeout_ms: int = 0) -> int:
        """
        Increments the counter at key by the integer value specified. If
        value is positive, the counter will atomically increment, if negative
        then it will atomically decrement.

        NOTE: If key does not exist, it will be set to the value here. This
            is how redis handles it and is good enough for now. We don't
            throw/raise an error on updating a counter that wasn't previously
            created.

        Args:
            key (string): Name of the shared counter
            value (int): Integer value of the shared counter. MUST be int
                for this API. Can be positive or negative
            timeout_ms (int, optional): How long the counter should live for.
                Default None, i.e. won't expire, but if set will call PEXPIRE
                under the hood to have the value expire after a certain amount
                of time.

        Return:
            Current value of the counter

        Raises:
            AtomError on invalid argument
        """

        # Initialize metrics
        self._counter_init_metrics(key)

        # Make sure we have an integer argument
        if type(value) is not int:
            raise AtomError("Counter value must be int!")

        # Get our pipelines
        with RedisPipeline(self) as redis_pipeline, MetricsPipeline(
            self
        ) as metrics_pipeline:

            self.metrics_timing_start(self._counter_metrics[key]["update"])

            # Perform the incrby. Incrby decrements on negative values
            redis_pipeline.incrby(self._make_counter_key(key), value)

            # If we have a timeout, put that in the pipeline as well
            if timeout_ms > 0:
                redis_pipeline.pexpire(self._make_counter_key(key), timeout_ms)

            # Execute the pipeline
            response = redis_pipeline.execute()

            self.metrics_timing_end(
                self._counter_metrics[key]["update"], pipeline=metrics_pipeline
            )

            # Response[0] will be return of INCRBY which is the new value of the
            #   counter.
            value = int(response[0])

            self.metrics_add(
                self._counter_metrics[key]["value"], value, pipeline=metrics_pipeline
            )

            return value

    def counter_get(self, key: str) -> Optional[int]:
        """
        Return the value of a shared counter. Returns None if the counter
            does not exist

        Args:
            key (string): Name of the shared counter

        Return:
            Current value of the counter if it exists, else None
        """

        # Initialize metrics
        self._counter_init_metrics(key)

        # Get our pipelines
        with RedisPipeline(self) as redis_pipeline, MetricsPipeline(
            self
        ) as metrics_pipeline:

            self.metrics_timing_start(self._counter_metrics[key]["get"])

            # Perform the incrby. Incrby decrements on negative values
            redis_pipeline.get(self._make_counter_key(key))

            # Execute the pipeline
            response = redis_pipeline.execute()

            self.metrics_timing_end(
                self._counter_metrics[key]["get"], pipeline=metrics_pipeline
            )

            # Response[0] will be the value of GET, which should be NONE if the
            #   key does not exist, else will be a value we'll cast to an int.
            if response[0] is not None:
                return int(response[0])
            else:
                return None

    def counter_delete(self, key: str) -> bool:
        """
        Deletes a shared counter

        Args:
            keys (str): Key of counter to delete from Atom

        Return:
            success (bool)
        """

        # Initialize metrics
        self._counter_init_metrics(key)

        with MetricsPipeline(self) as metrics_pipeline:
            self.metrics_timing_start(self._counter_metrics[key]["delete"])

            success, _ = self._redis_key_delete(self._make_counter_key(key))

            self.metrics_timing_end(
                self._counter_metrics[key]["delete"], pipeline=metrics_pipeline
            )

        return success

    def _make_sorted_set_key(self, key: str) -> str:
        """
        Prefixes requested key under sorted set namespace.
        """
        return f"sorted_set:{key}"

    def _sorted_set_init_metrics(self, key: str) -> None:
        """
        Initialize the metrics for using a sorted set
        """

        # If we've already created the metrics, just return
        if self._sorted_set_metrics[key]:
            return

        self._sorted_set_metrics[key]["add"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:sorted_set",
            key,
            "add",
            agg_types=["AVG", "MIN", "MAX", "COUNT"],
        )

        self._sorted_set_metrics[key]["size"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:sorted_set",
            key,
            "size",
            agg_types=["AVG", "MIN", "MAX", "COUNT"],
        )

        self._sorted_set_metrics[key]["pop"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:sorted_set",
            key,
            "pop",
            agg_types=["AVG", "MIN", "MAX", "COUNT"],
        )

        self._sorted_set_metrics[key]["pop_n"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:sorted_set",
            key,
            "pop_n",
            agg_types=["AVG", "MIN", "MAX", "COUNT"],
        )

        self._sorted_set_metrics[key]["range"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:sorted_set",
            key,
            "range",
            agg_types=["AVG", "MIN", "MAX", "COUNT"],
        )

        self._sorted_set_metrics[key]["read"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:sorted_set",
            key,
            "read",
            agg_types=["AVG", "MIN", "MAX", "COUNT"],
        )

        self._sorted_set_metrics[key]["remove"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:sorted_set",
            key,
            "remove",
            agg_types=["AVG", "MIN", "MAX", "COUNT"],
        )

        self._sorted_set_metrics[key]["delete"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:sorted_set",
            key,
            "delete",
            agg_types=["AVG", "MIN", "MAX", "COUNT"],
        )

        self._sorted_set_metrics[key]["card"] = self.metrics_create(
            MetricsLevel.TIMING,
            "atom:sorted_set",
            key,
            "card",
            agg_types=["AVG", "MIN", "MAX"],
        )

    def sorted_set_add(self, set_key: str, member: str, value: float) -> int:
        """
        Set the value for a shared, atomic counter directly using SET

        Args:
            set_key (string): Name of the sorted set
            member (string): Name of the member to use in the sorted set
            value (float): Value to give to the member in the sorted set

        Return:
            Cardinality of the set, i.e. how many members exist after
                the ADD.

        Raises:
            AtomError on inability to add to set
        """

        # Initialize metrics
        self._sorted_set_init_metrics(set_key)
        redis_key = self._make_sorted_set_key(set_key)

        # Get our pipelines
        with RedisPipeline(self) as redis_pipeline, MetricsPipeline(
            self
        ) as metrics_pipeline:

            # Add to the sorted set
            self.metrics_timing_start(self._sorted_set_metrics[set_key]["add"])

            redis_pipeline.zadd(redis_key, {member: value})
            redis_pipeline.zcard(redis_key)
            response = redis_pipeline.execute()

            self.metrics_timing_end(
                self._sorted_set_metrics[set_key]["add"], pipeline=metrics_pipeline
            )

            if response[0] != 1 and response[0] != 0:
                raise AtomError(
                    f"Failed add member: {member}, value {value} to sorted set {set_key}"
                )

            cardinality = response[1]
            self.metrics_add(
                self._sorted_set_metrics[set_key]["card"],
                cardinality,
                pipeline=metrics_pipeline,
            )

        return cardinality

    def sorted_set_size(self, set_key: str) -> int:
        """
        Get the cardinality/size of a sorted set

        Args:
            set_key (string): Name of the sorted set

        Return:
            Cardinality of the set, i.e. how many members exist after
                the ADD.

        Raises:
            AtomError on inability to add to set
        """
        # Initialize metrics
        self._sorted_set_init_metrics(set_key)
        redis_key = self._make_sorted_set_key(set_key)

        # Get our pipelines
        with RedisPipeline(self) as redis_pipeline, MetricsPipeline(
            self
        ) as metrics_pipeline:

            # Add to the sorted set
            self.metrics_timing_start(self._sorted_set_metrics[set_key]["size"])

            redis_pipeline.zcard(redis_key)
            response = redis_pipeline.execute()

            self.metrics_timing_end(
                self._sorted_set_metrics[set_key]["size"], pipeline=metrics_pipeline
            )

            cardinality = response[0]
            self.metrics_add(
                self._sorted_set_metrics[set_key]["card"],
                cardinality,
                pipeline=metrics_pipeline,
            )

        return cardinality

    def sorted_set_pop(
        self,
        set_key: str,
        maximum: bool = False,
        block: bool = False,
        timeout: float = 0,
    ):
        """
        Pop a value from a sorted set. Minium or maximum (min by default)

        NOTE: We cannot/should not do blocking operations inside of multi/exec
            pipelines since this will block the entire server. If we try to do
            the BZPOP-type operations inside of a traditional multi-exec
            pipeline we'll get an immediate None/Failure type response

        Args:
            set_key (string): Name of the sorted set
            maximum (bool): True to pop maximum, False to pop minimum
            block (bool, optional): True to block and wait for data if none
                exists, False to not block
            timeout (float, optional): Seconds. If block is true, this will
                be how long we wait for data before timing out. Set to 0 for
                infinite block/no timeout.

        Return:
            Tuple of (Tuple of (member, value) that was popped, set cardinality)

        Raises:
            AtomError on error
            SetEmptyError on empty set
        """

        # Initialize metrics
        self._sorted_set_init_metrics(set_key)
        redis_key = self._make_sorted_set_key(set_key)

        # Get our pipelines
        with RedisPipeline(self) as redis_pipeline, MetricsPipeline(
            self
        ) as metrics_pipeline:

            # Add to the sorted set
            self.metrics_timing_start(self._sorted_set_metrics[set_key]["pop"])

            if not maximum:
                if block:
                    redis_pipeline.bzpopmin(redis_key, timeout=timeout)
                else:
                    redis_pipeline.zpopmin(redis_key)
            else:
                if block:
                    redis_pipeline.bzpopmax(redis_key, timeout=timeout)
                else:
                    redis_pipeline.zpopmax(redis_key)
            redis_pipeline.zcard(redis_key)
            response = redis_pipeline.execute()

            self.metrics_timing_end(
                self._sorted_set_metrics[set_key]["pop"], pipeline=metrics_pipeline
            )

            if not response[0]:
                raise SetEmptyError(
                    f"Sorted set {set_key} is empty, block: {block}, timeout: {timeout}"
                )

            cardinality = response[1]
            self.metrics_add(
                self._sorted_set_metrics[set_key]["card"],
                cardinality,
                pipeline=metrics_pipeline,
            )

        # We get slightly different responses based on if it was a blocking
        #   or non-blocking call
        if block:
            data = (response[0][1], response[0][2])
        else:
            data = response[0][0]

        return data, cardinality

    def sorted_set_pop_n(self, set_key: str, n: int, maximum: bool = False):
        """
        Pop at most n values from a sorted set. Items are popped and returned
            in prio order (Minium or maximum (min by default)). Done via a
            single redis call/transaction.

        Will raise SetEmptyError on no data in the set
        Will never block
        Will return at most N items, but only as many items as exist in the
            set <= N.

        Args:
            set_key (string): Name of the sorted set
            n (int): Maximum number of items to pop.
            maximum (bool): True to pop maximum, False to pop minimum

        Return:
            Tuple ([List of (member, value)], set cardinality)

        Raises:
            AtomError on error
            SetEmptyError on empty set
        """

        # Initialize metrics
        self._sorted_set_init_metrics(set_key)
        redis_key = self._make_sorted_set_key(set_key)

        # Get our pipelines
        with RedisPipeline(self) as redis_pipeline, MetricsPipeline(
            self
        ) as metrics_pipeline:

            # Add to the sorted set
            self.metrics_timing_start(self._sorted_set_metrics[set_key]["pop_n"])

            if not maximum:
                redis_pipeline.zpopmin(redis_key, count=n)
            else:
                redis_pipeline.zpopmax(redis_key, count=n)
            redis_pipeline.zcard(redis_key)
            response = redis_pipeline.execute()

            self.metrics_timing_end(
                self._sorted_set_metrics[set_key]["pop_n"], pipeline=metrics_pipeline
            )

            if not response[0]:
                raise SetEmptyError(f"Sorted set {set_key} is empty")

            cardinality = response[1]
            self.metrics_add(
                self._sorted_set_metrics[set_key]["card"],
                cardinality,
                pipeline=metrics_pipeline,
            )

        return response[0], cardinality

    def sorted_set_range(
        self,
        set_key: str,
        start: int,
        end: int,
        maximum: bool = False,
        withvalues: bool = True,
    ):
        """
        Read a range of the sorted set

        Args:
            set_key (string): Name of the sorted set
            start (int): start index of the read
            end (int): End index of the read
            maximum (bool): Read from greatest to least, else least to greatest
            withvalues (bool): Return scores with member.

        Return:
            List of Tuple of (member, value) that was read if withvalues=True.
                Else, will be sorted list of members read.

        Raises:
            AtomError on inability to pop or empty set
        """

        # Initialize metrics
        self._sorted_set_init_metrics(set_key)
        redis_key = self._make_sorted_set_key(set_key)

        # Get our pipelines
        with RedisPipeline(self) as redis_pipeline, MetricsPipeline(
            self
        ) as metrics_pipeline:

            # Add to the sorted set
            self.metrics_timing_start(self._sorted_set_metrics[set_key]["range"])

            if not maximum:
                redis_pipeline.zrange(redis_key, start, end, withscores=withvalues)
            else:
                redis_pipeline.zrevrange(redis_key, start, end, withscores=withvalues)
            response = redis_pipeline.execute()

            self.metrics_timing_end(
                self._sorted_set_metrics[set_key]["range"], pipeline=metrics_pipeline
            )

            if not response[0]:
                raise AtomError(
                    f"Failed to read range {start} to {end} from {'max' if maximum else 'min'} in sorted set {set_key}"
                )

        return response[0]

    def sorted_set_read(self, set_key: str, member: str):
        """
        Read the value of a member from a sorted set

        Args:
            set_key (string): Name of the sorted set
            member (string): Mmeber of the sorted set we want to read

        Return:
            value of member

        Raises:
            AtomError on inability to read member from set
        """

        # Initialize metrics
        self._sorted_set_init_metrics(set_key)
        redis_key = self._make_sorted_set_key(set_key)

        # Get our pipelines
        with RedisPipeline(self) as redis_pipeline, MetricsPipeline(
            self
        ) as metrics_pipeline:

            # Add to the sorted set
            self.metrics_timing_start(self._sorted_set_metrics[set_key]["read"])

            redis_pipeline.zscore(redis_key, member)
            response = redis_pipeline.execute()

            self.metrics_timing_end(
                self._sorted_set_metrics[set_key]["read"], pipeline=metrics_pipeline
            )

            if response[0] is None:
                raise AtomError(
                    f"Failed to read member {member} from sorted set {set_key}"
                )

        return response[0]

    def sorted_set_remove(self, set_key: str, member: str) -> None:
        """
        Remove a member from a sorted set

        Args:
            set_key (string): Name of the sorted set
            member (string): Mmeber of the sorted set we want to remove

        Return:
            None

        Raises:
            AtomError on inability to remove member from set
        """

        # Initialize metrics
        self._sorted_set_init_metrics(set_key)
        redis_key = self._make_sorted_set_key(set_key)

        # Get our pipelines
        with RedisPipeline(self) as redis_pipeline, MetricsPipeline(
            self
        ) as metrics_pipeline:

            # Add to the sorted set
            self.metrics_timing_start(self._sorted_set_metrics[set_key]["remove"])

            redis_pipeline.zrem(redis_key, member)
            redis_pipeline.zcard(redis_key)
            response = redis_pipeline.execute()

            self.metrics_timing_end(
                self._sorted_set_metrics[set_key]["remove"], pipeline=metrics_pipeline
            )

            if response[0] != 1:
                raise AtomError(
                    f"Failed to remove member {member} from sorted set {set_key}"
                )

            self.metrics_add(
                self._sorted_set_metrics[set_key]["card"],
                response[1],
                pipeline=metrics_pipeline,
            )

    def sorted_set_delete(self, set_key: str) -> None:
        """
        Delete a sorted set entirely

        Args:
            set_key (string): Name of the sorted set

        Return:
            None

        Raises:
            AtomError on inability to remove member from set
        """

        # Initialize metrics
        self._sorted_set_init_metrics(set_key)
        redis_key = self._make_sorted_set_key(set_key)

        # Get our pipelines
        with RedisPipeline(self) as redis_pipeline, MetricsPipeline(
            self
        ) as metrics_pipeline:

            # Add to the sorted set
            self.metrics_timing_start(self._sorted_set_metrics[set_key]["delete"])

            redis_pipeline.unlink(redis_key)
            response = redis_pipeline.execute()

            self.metrics_timing_end(
                self._sorted_set_metrics[set_key]["delete"], pipeline=metrics_pipeline
            )

            if not response[0]:
                raise AtomError(f"Failed to delete sorted set {set_key}")

            self.metrics_add(
                self._sorted_set_metrics[set_key]["card"], 0, pipeline=metrics_pipeline
            )

    def metrics_get_pipeline(self) -> RedisTimeSeriesPipeline:
        """
        Get a pipeline for use in metrics.

        Return:
            pipeline: the pipeline itself
        """
        if not self._metrics_enabled:
            return None

        try:
            pipeline = self._mpipeline_pool.get(block=False)
        except QueueEmpty:
            self.logger.error(
                "Failed to get metrics pipeline, something is very wrong!"
            )
            raise AtomError("Ran out of metrics pipelines!")

        return pipeline

    def metrics_write_pipeline(
        self, pipeline: RedisTimeSeriesPipeline, error_ok: Optional[str] = None
    ) -> Optional[list]:
        """
        Release (and perhaps execute) a pipeline that was used for a metrics
        call. If execute is TRUE we will execute the pipeline and return
        it to the general pool. If execute is FALSE we will not execute the
        pipeline and we will put it back into the async pool. Then, it will get
        executed either when someone flushes or opportunistically by
        the next person who releases a pipeline with execute=True.

        Args:
            pipeline: pipeline to release (return value 0 of
                metrics_get_pipeline)
            prev_len: previous length of the pipeline before we got it (return
                value 1 of metrics_get_pipeline)
        """
        if not self._metrics_enabled:
            return None

        data = None

        try:
            data = pipeline.execute()
            pipeline.reset()
            self._mpipeline_pool.put(pipeline)
        #  KNOWN ISSUE WITH NO WORKAROUND: Adding two metrics values with the
        #   same timestamp throws this error. We generally shouldn't hit this,
        #   but if we do we shouldn't crash because of it -- lowing metrics
        #   is not the end of the world here.
        except redis.exceptions.ResponseError as e:
            if error_ok and error_ok in str(e):
                pass
            else:
                self.logger.error(f"Failed to write metrics with exception {e}")

            del pipeline
            self._mpipeline_pool.put(self._mclient.pipeline(transaction=False))

        # Only return the data that we care about (if any)
        return data

    def metrics_create_custom(
        self,
        level: MetricsLevel,
        key: str,
        retention: int = METRICS_DEFAULT_RETENTION,
        labels: Optional[dict] = None,
        rules: Optional[dict] = None,
        update: bool = True,
        duplicate_policy: Literal["block", "first", "last", "min", "max"] = "last",
    ) -> str:
        """
        Create a metric at the given key with retention and labels. This is a
        direct interface to the redis time series API. It's generally not
        recommended to use this and encouraged to stick with the atom system.

        NOTE: not able to be done asynchronously -- there is too much internal
        back and forth with the redis server. This call will always make
        writes out to the metrics redis.

        Args:
            level (MetricsLevel): Severity level of the metric
            key (str): Key to use for the metric
            retention (int, optional): How long to keep data for the metric,
                in milliseconds. Default 60000ms == 1 minute. Be careful with
                this, it will grow unbounded if set to 0.
            labels (dictionary, optional): Optional labels to add to the
                data. Each key should be a string and each value should also
                be a string.
            rules (dictionary, optional): Optional dictionary of rules to apply
                to the metric using TS.CREATERULE
                (https://oss.redislabs.com/redistimeseries/commands/#tscreaterule) # noqa 501
                Each key in the dictionary should be a new time series key and
                the value should be a tuple with the following items:
                    [0]: aggregation type (str, one of: avg, sum, min, max,
                        range, count, first, last, std.p, std.s, var.p, var.s)
                    [1]: aggregation time bucket (int, milliseconds over which
                        to perform aggregation)
                    [2]: aggregation retention, i.e. how long to keep this
                        aggregated stat for
            update (boolean, optional): We will call TS.CREATE to attempt to
                create the key. If this is false and the key exists we'll
                return out. Otherwise we'll update the key.
            duplicate_policy (string, optional): How to handle when there's
                already a sample in the series at the same millisecond. The
                default behavior here, `last`, will overwrite and not throw
                an error. Choices are:
                  - 'block': an error will occur for any out of order sample
                  - 'first': ignore the new value
                  - 'last': override with latest value
                  - 'min': only override if the value is lower than the
                        existing value
                  - 'max': only override if the value is higher than the
                        existing value

        Return:
            key (str): The key used. Can then be passed to metrics timing
                and/or metrics add custom without having to go through the whole
                type/subtype rigamarole.
        """

        if not self._metrics_enabled:
            return None

        # If we don't have labels, make the default empty
        if labels is None:
            labels = {}
        # If we don't have rules, make the default empty
        if rules is None:
            rules = {}

        # If we shouldn't be logging at this level, then just return the key
        #   since it's not added to self._metrics any calls to metrics_add()
        #   will be no-ops.
        if level.value > self._metrics_level.value:
            print(
                f"Ignoring metric {key} with level {level.name} due to active level being {self._metrics_level.name}"
            )
            return key

        # If we've already seen/created the metric once in this program/
        #   thread just skip it. There is a slight race here which we can
        #   handle -- just want to avoid unnecessary pass-throughs if possible
        if key in self._metrics and not update:
            print(f"Already called metrics_create_custom on {key}, skipping")
            return key

        # Validate labels
        self._metrics_validate_labels(labels)

        # Add in the aggregation to the labels we'll be setting
        _labels = {
            METRICS_AGGREGATION_LABEL: "none",
            METRICS_AGGREGATION_TYPE_LABEL: "none",
            **labels,
        }

        # Try to make the key. Need to know if the key already exists in order
        #   to figure out if this will fail
        key_exists = False
        try:
            data = self._mclient.create(
                key,
                retention_msecs=retention,
                labels=_labels,
                duplicate_policy=duplicate_policy,
            )
        # Key already exists
        except redis.exceptions.ResponseError:
            key_exists = True

        # If the key exists, do some updates
        rule_key_exists = []
        if key_exists:

            # If we shouldn't be updating return out
            if not update:
                return None

            # Update the retention milliseconds and labels
            self._mclient.alter(
                key,
                retention_msecs=retention,
                labels=_labels,
                duplicate_policy=duplicate_policy,
            )

            # Need to get info about the key
            data = self._mclient.info(key)

            # If we have any rules, delete them
            if len(data.rules) > 0:
                for rule in data.rules:
                    # Try to delete the rule since we don't need it anymore.
                    #   if this fails we're likely in a race and someone else
                    #   did it, NBD. No need to delete the stream itself. It'll
                    #   age out with time.
                    try:
                        self._mclient.deleterule(key, rule[0])
                    except redis.exceptions.ResponseError:
                        pass

                    # If we want to use the same rule key, note it exists
                    rule_str = rule[0].decode("utf-8")
                    if rule_str in rules:
                        rule_key_exists.append(rule_str)

        # If we have new rules to add, add them
        for rule in rules.keys():

            _rule_labels = {
                METRICS_AGGREGATION_LABEL: f"{rules[rule][1] // (1000 * 60)}m",
                METRICS_AGGREGATION_TYPE_LABEL: rules[rule][0],
                **labels,
            }
            # If we found the rule earlier, make sure its stream matches our
            #   desired retention and labels
            if rule in rule_key_exists:
                self._mclient.alter(
                    rule,
                    retention_msecs=rules[rule][2],
                    labels=_rule_labels,
                    duplicate_policy=duplicate_policy,
                )
            else:
                try:
                    self._mclient.create(
                        rule,
                        retention_msecs=rules[rule][2],
                        labels=_rule_labels,
                        duplicate_policy=duplicate_policy,
                    )
                except redis.exceptions.ResponseError:
                    pass

            # Try to make the aggregation rule. If this fails, we're in a race
            #   with someone else and they beat us to it. NBD
            try:
                self._mclient.createrule(key, rule, rules[rule][0], rules[rule][1])
            except redis.exceptions.ResponseError:
                pass

        # Note we're logging this metric. Will be used for metric level
        #   filtering
        if key not in self._metrics:
            self._metrics.add(key)

        return key

    def metrics_create(
        self,
        level: MetricsLevel,
        m_type: str,
        *m_subtypes,
        retention: int = METRICS_DEFAULT_RETENTION,
        labels: Optional[dict] = None,
        agg_timing: list[tuple[int, int]] = METRICS_DEFAULT_AGG_TIMING,
        agg_types: Optional[list[str]] = None,
        duplicate_policy: Literal["block", "first", "last", "min", "max"] = "last",
    ) -> str:
        """
        Create a metric of the given type and subtypes. All labels you need
        will be auto-generated, though more can be passed. Aggregation will
        be by default not performed, pass agg_types to add aggregation with
        default timing of the types specified

        NOTE: not able to be done asynchronously -- there is too much internal
        back and forth with the redis server. This call will always make
        writes out to the metrics redis.

        Args:
            level (MetricsLevel): Severity level of the metric
            m_type (str): Type of the metric to be used
            m_subtypes (list of anything that can be converted to a string):
                Subtypes for the metric to be used. As long as the object can
                be converted to a string using f-string syntax then it can be
                passed here. This is nice to simplify the API and prevent
                the user from having to do it themselves

            retention (int, optional): How long to keep data for the metric,
                in milliseconds. Default 60000ms == 1 minute. Be careful with
                this, it will grow unbounded if set to 0.
            labels (dictionary, optional): Optional additional labels to add to
                the data. Each key should be a string and each value should also
                be a string. All default atom labels will be added
            agg_timing (list of tuples, optional): List of tuples where
                each tuple has the following fields:
                    [0]: Time bucket
                    [1]: Retention
            agg_types (list of strings, optional): List of strings. For each
                aggregation type in this list, rules will be set up for each
                of the timings in the timing lists.
            update (boolean, optional): We will call TS.CREATE to attempt to
                create the key. If this is false and the key exists we'll
                return out. Otherwise we'll update the key.
            duplicate_policy (string, optional): How to handle when there's
                already a sample in the series at the same millisecond. The
                default behavior here, `last`, will overwrite and not throw
                an error. Choices are:
                  - 'block': an error will occur for any out of order sample
                  - 'first': ignore the new value
                  - 'last': override with latest value
                  - 'min': only override if the value is lower than the
                        existing value
                  - 'max': only override if the value is higher than the
                        existing value

        Return:
            key (str): The key used. Can then be passed to metrics timing
                and/or metrics add custom without having to go through the whole
                type/subtype rigamarole.
        """

        if not self._metrics_enabled:
            return None

        # If we don't have labels, make the default empty
        if labels is None:
            labels = {}
        # If we don't have agg types, make the default empty
        if agg_types is None:
            agg_types = []

        # Get the key to use
        _key = self._make_metric_id(self.name, m_type, *m_subtypes)

        # Validate labels
        self._metrics_validate_labels(labels)

        # Add in the default labels
        _labels = self._metrics_add_default_labels(labels, level, m_type, *m_subtypes)

        # If we want to use the default aggregation rules we just iterate
        #   over the time buckets and apply the aggregation types requested
        _rules = {}

        if self._metrics_use_aggregation:
            for agg in agg_types:
                for timing in agg_timing:
                    _rule_key = self._make_metric_id(
                        self.name, m_type, *m_subtypes, agg
                    )
                    _rules[f"{_rule_key}:{timing[0]//(1000 * 60)}m"] = (
                        agg,
                        timing[0],
                        timing[1],
                    )

        return self.metrics_create_custom(
            level,
            _key,
            retention=retention,
            labels=_labels,
            rules=_rules,
            duplicate_policy=duplicate_policy,
        )

    def metrics_log(
        self,
        stream: str,
        key: str,
        data,
        pipeline: Optional[RedisTimeSeriesPipeline] = None,
        maxlen: int = 100,
    ) -> Optional[list]:
        """
        Logs to a metric/debug stream that can be viewed in Grafana
        """
        if not self._metrics_enabled:
            return None

        if not pipeline:
            _pipe = self.metrics_get_pipeline()
        else:
            _pipe = pipeline

        # We want to log to the debug stream in the metrics
        #   redis about the parameter change. This will make it show up
        #   in the dashboards so we can see what the current/previous
        #   values of parameters have been
        _pipe.xadd(
            f"{self.name}:{stream}",
            {f"{datetime.now()} - {key}": str(data)},
            maxlen=maxlen,
        )

        data = None
        if not pipeline:
            data = self.metrics_write_pipeline(_pipe)

        return data

    def metrics_add(
        self,
        key: str,
        val,
        timestamp=None,
        pipeline: Optional[RedisTimeSeriesPipeline] = None,
        enforce_exists: bool = True,
        retention: int = 86400000,
        labels: Optional[dict] = None,
    ):
        """
        Adds a metric at the given key with the given value. Timestamp
            can be set if desired, leaving at the default of '*' will result
            in using the redis-server's timestamp which is usually good enough.

        NOTE: The metric MUST have been created with metrics_create or
            metrics_create_custom before calling.

        Args:
            key (str): Key to use for the metric
            val (int/float): Value to be adding to the time series
            timestamp (None/str/int, optional): Timestamp to use for the value
                in the time series. Leave at default to use the redis server's
                built-in timestamp. Set to None to have this function take the
                current system time and write it in. Else, pass an integer that
                will be used as the timestamp.
            pipeline (redis pipeline, optional): Leave NONE (default) to send
                the metric to the redis server in this function call. Pass a
                pipeline to just have the data added to the pipeline which you
                will need to flush later
            enforce_exists: If TRUE, enforce that the metric exists before
                writing. RECOMMENDED TO ALWAYS LEAVE THIS TRUE. However, it's
                useful some times if you truly don't know which metrics you'll
                be writing to that you can just call ADD and it'll write it out
                and create the key if it doesn't exist. Use with caution.
            retention (int, optional): Retention for the metric, if it doesn't
                already exist. Only used if enforce_exists=False.
            labels(dict, optional): Label of key, value pairs to be used as
                filters for the metric. Only used if enforce_exists=False

        Return:
            list of integers representing the timestamps created. None on
                failure.
        """

        # If metrics are off or if the key has been filtered due to log level
        if not self._metrics_enabled or (key not in self._metrics and enforce_exists):
            return None

        # If we don't have labels, make the default empty
        if labels is None:
            labels = {}

        if not pipeline:
            _pipe = self.metrics_get_pipeline()
        else:
            _pipe = pipeline

        # Update the timestamp
        if timestamp is None or pipeline is not None:
            timestamp = int(round(time.time() * 1000))

        # Add to the pipeline
        if enforce_exists:
            _pipe.madd(((key, timestamp, val),))
        else:
            _pipe.add(key, timestamp, val, retention_msecs=retention, labels=labels)

        data = None
        if not pipeline:
            data = self.metrics_write_pipeline(_pipe)

        # Since we're using madd instead of add (in order to not auto-create)
        #   we need to extract the outer list here for simplicity.
        return data

    def metrics_add_type(
        self,
        level: MetricsLevel,
        value: Union[int, float],
        m_type: str,
        *m_subtypes,
        timestamp=None,
        pipeline: Optional[RedisTimeSeriesPipeline] = None,
        retention: int = 86400000,
        labels: Optional[dict] = None,
    ):
        """
        Adds a metric at the given key with the given value. Timestamp
            can be set if desired, leaving at the default of '*' will result
            in using the redis-server's timestamp which is usually good enough.

        Args:
            level (MetricsLevel): Severity level of the metric
            val (int/float): Value to be adding to the time series
            m_type (str): Metric's identifying type
            m_subtypes (str): Metric's identifying subtypes
            timestamp (None/str/int, optional): Timestamp to use for the value
                in the time series. Leave at default to use the redis server's
                built-in timestamp. Set to None to have this function take the
                current system time and write it in. Else, pass an integer that
                will be used as the timestamp.
            pipeline (redis pipeline, optional): Leave NONE (default) to send
                the metric to the redis server in this function call. Pass a
                pipeline to just have the data added to the pipeline which you
                will need to flush later
            retention (int, optional): Retention for the metric, if it doesn't
                already exist. Only used if enforce_exists=False.
            labels (dict, optional): Label of key, value pairs to be used as
                filters for the metric. Only used if enforce_exists=False

        Return:
            list of integers representing the timestamps created. None on
                failure.
        """
        if not self._metrics_enabled:
            return None

        # If we don't have labels, make the default empty
        if labels is None:
            labels = {}

        # Get the key to use
        _key = self._make_metric_id(self.name, m_type, *m_subtypes)

        # Get the labels to use. Only need to go through the process of
        #   generating/sending labels the first time we see a new key. They're
        #   ignored each time after anyway
        if _key not in self._metrics_add_type_keys:
            self._metrics_validate_labels(labels)
            _labels = self._metrics_add_default_labels(
                labels, level, m_type, *m_subtypes
            )
            self._metrics_add_type_keys = _key
        else:
            _labels = {}

        # Call the custom API with the key name
        return self.metrics_add(
            _key,
            value,
            timestamp=timestamp,
            pipeline=pipeline,
            retention=retention,
            labels=_labels,
            enforce_exists=False,  # Not having called metrics_create
        )

    def _metrics_get_timing_key(self, key: str) -> str:
        """
        Get a key to be used in the timing lookup dict

        Args:
            key: User-supplied key

        Returns:
            db_key (string): String to use as lookup in the timing dict
        """
        return f"{threading.get_ident()}:{key}"

    def metrics_timing_start(self, key: str) -> None:
        """
        Simple helper function to do the keeping-track-of-time for
        timing-based metrics.

        Args:
            key (string): Key we want to start tracking timing for
        """
        self._active_timing_metrics[
            self._metrics_get_timing_key(key)
        ] = time.monotonic()

    def metrics_timing_end(
        self,
        key: str,
        pipeline: Optional[RedisTimeSeriesPipeline] = None,
        strict: bool = False,
    ) -> None:
        """
        Simple helper function to finish a time that was being kept
        track of and write out the metric

        Args:
            key: (string): Key we want to stop metrics timing on
            pipeline (optional, Redis Pipeline): Pipeline to add the metric to
            strict (optional, bool): If set to TRUE, will raise an AtomError
                on the key not existing, else will just log a warning
        """
        db_key = self._metrics_get_timing_key(key)
        if db_key not in self._active_timing_metrics:
            if strict:
                raise AtomError(f"key {db_key} timer not started!")
            else:
                self.logger.warning(f"Timing key {key} does not exist -- skipping")

        delta = time.monotonic() - self._active_timing_metrics[db_key]
        self.metrics_add(key, delta, pipeline=pipeline)

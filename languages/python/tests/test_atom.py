import os
import time
import gc
import copy
from multiprocessing import Process, Queue
from threading import Thread

from atom import Element
from atom.element import ElementConnectionTimeoutError

import numpy as np
import pytest
import os
import redis

from redistimeseries.client import Client as RedisTimeSeries

from atom import Element, AtomError, MetricsLevel
from atom.config import DEFAULT_REDIS_SOCKET, DEFAULT_REDIS_PORT
from atom.config import ATOM_NO_ERROR, ATOM_COMMAND_NO_ACK, ATOM_COMMAND_UNSUPPORTED
from atom.config import ATOM_COMMAND_NO_RESPONSE, ATOM_CALLBACK_FAILED
from atom.config import ATOM_USER_ERRORS_BEGIN, HEALTHCHECK_RETRY_INTERVAL
from atom.config import HEALTHCHECK_COMMAND, VERSION_COMMAND, LANG, VERSION, \
                        COMMAND_LIST_COMMAND
from atom.messages import Response, StreamHandler, LogLevel
from atom.contracts import RawContract, EmptyContract, BinaryProperty
from msgpack import packb, unpackb

pytest.caller_incrementor = 0
pytest.responder_incrementor = 0

TEST_REDIS_SOCKET = os.getenv('TEST_REDIS_SOCKET', DEFAULT_REDIS_SOCKET)
TEST_REDIS_HOST = os.getenv('TEST_REDIS_HOST', None)
TEST_REDIS_PORT = os.getenv('TEST_REDIS_PORT', DEFAULT_REDIS_PORT)

class TestAtom():
    def _assert_cleaned_up(self, element):
        for s in element.streams:
            private_sn = element._make_stream_id(element.name, s)
            exists_val = element._rclient.exists(private_sn)
            assert not exists_val, "private redis stream key %s should not exist" % (private_sn,)

    def _element_create(self, name, host=TEST_REDIS_HOST, port=TEST_REDIS_PORT, socket_path=TEST_REDIS_SOCKET, conn_timeout_ms=2000, data_timeout_ms=5000):
        return Element(name, host=host, port=port, socket_path=socket_path, conn_timeout_ms=conn_timeout_ms, data_timeout_ms=data_timeout_ms)

    def _element_start(self, element, caller, read_block_ms=500, do_healthcheck=True, healthcheck_interval=0.5):
        element.command_loop(block=False, read_block_ms=read_block_ms)
        if do_healthcheck:
            caller.wait_for_elements_healthy([element.name], retry_interval=healthcheck_interval)

    def _element_cleanup(self, element):
        element.command_loop_shutdown(block=True)
        element._clean_up()

    def _get_redis_client(self):
        if TEST_REDIS_HOST is not None:
            client = redis.StrictRedis(
                host=TEST_REDIS_HOST,
                port=TEST_REDIS_PORT
            )
        else:
            client = redis.StrictRedis(
                unix_socket_path=TEST_REDIS_SOCKET
            )

        return client

    @pytest.fixture(autouse=True)
    def client(self):
        """
        Run at setup, creates a redis client and flushes
        all existing keys in the DB to ensure no interaction
        between the tests and a fresh startup state between the
        tests
        """

        client = self._get_redis_client()
        client.flushall()
        keys = client.keys()
        assert keys == []
        yield client

        del client

    @pytest.fixture
    def caller(self, client, check_redis_end, metrics):
        """
        Sets up the caller before each test function is run.
        Tears down the caller after each test is run.
        """
        caller_name = "test_caller_%s" % (pytest.caller_incrementor,)
        caller = self._element_create(caller_name)
        yield caller, caller_name
        pytest.caller_incrementor += 1

        # Need to manually call the delete method to
        #   clean up the object since garbage collection
        #   won't get to it until all fixtures have run and
        #   then the check_redis_end fixture won't be able
        #   to see how well we cleaned up
        caller._clean_up()

    @pytest.fixture
    def responder(self, client, check_redis_end, metrics):
        """
        Sets up the responder before each test function is run.
        Tears down the responder after each test is run.
        """
        responder_name = "test_responder_%s"  % (pytest.responder_incrementor,)
        responder = self._element_create(responder_name)
        yield responder, responder_name
        pytest.responder_incrementor += 1

        # Need to manually call the delete method to
        #   clean up the object since garbage collection
        #   won't get to it until all fixtures have run and
        #   then the check_redis_end fixture won't be able
        #   to see how well we cleaned up
        responder._clean_up()

    @pytest.fixture(autouse=True)
    def check_redis_end(self):
        """
        Runs at end -- IMPORTANT: must depend on caller and responder
        in order to ensure it runs after the caller and responder
        cleanup.
        """

        client = self._get_redis_client()
        yield client

        keys = client.keys()
        assert (keys == [] or keys == [b'log'])

        del client

    @pytest.fixture
    def metrics(self):
        metrics = RedisTimeSeries(
            unix_socket_path="/shared/metrics.sock"
        )
        metrics.redis.flushall()

        yield metrics

        del metrics

    def test_caller_responder_exist(self, caller, responder):
        """
        Ensures that the caller and responder were created with the proper names.
        """
        caller, caller_name = caller
        responder, responder_name = responder

        print(caller.get_all_elements())
        assert responder_name in caller.get_all_elements()
        assert caller_name in responder.get_all_elements()


    def test_id_generation(self, caller):
        """
        Ensures id generation functions are working with expected input.
        """
        caller, caller_name = caller

        assert caller._make_response_id("abc") == "response:abc"
        assert caller._make_command_id("abc") == "command:abc"
        assert caller._make_stream_id("abc", "123") == "stream:abc:123"

    def test_command_in_redis(self, caller, responder):
        """
        Tests caller sending command and verifies that command was sent properly in Redis.
        """
        caller, caller_name = caller
        responder, responder_name = responder

        proc = Process(target=caller.command_send, args=(responder_name, "test_cmd", 0,))
        proc.start()
        data = caller._rclient.xread({caller._make_command_id(responder_name): "$"}, block=1000)
        proc.join()
        stream, msgs = data[0] #since there's only one stream
        assert stream.decode() == "command:%s" % (responder_name,)
        _id, msg = msgs[0]
        assert msg[b"element"].decode() == caller_name
        assert msg[b"cmd"] == b"test_cmd"
        assert msg[b"data"] == b"0"

    def test_add_entry_and_get_n_most_recent(self, caller, responder):
        """
        Adds 10 entries to the responder's stream and makes sure that the
        proper values are returned from get_n_most_recent.
        """
        caller, caller_name = caller
        responder, responder_name = responder

        for i in range(10):
            responder.entry_write("test_stream", {"data": i})
        entries = caller.entry_read_n(responder_name, "test_stream", 5)
        assert len(entries) == 5
        assert entries[0]["data"] == b"9"
        assert entries[-1]["data"] == b"5"

    def test_add_entry_and_get_n_most_recent_legacy_serialize(self, caller, responder):
        """
        Adds 10 entries to the responder's stream with legacy serialization and makes sure
        that the proper values are returned from get_n_most_recent.
        """
        caller, caller_name = caller
        responder, responder_name = responder

        for i in range(10):
            data = {"data": i}
            responder.entry_write("test_stream_serialized", data, serialize=True)
            # Ensure that serialization keeps the original data in tact
            assert data["data"] == i
        entries = caller.entry_read_n(responder_name, "test_stream_serialized", 5, deserialize=True)
        assert len(entries) == 5
        assert entries[0]["data"] == 9
        assert entries[-1]["data"] == 5

    def test_add_entry_and_get_n_most_recent_arrow_serialized(self, caller, responder):
        """
        Adds 10 entries to the responder's stream with Apache Arrow serialization and makes sure
        that the proper values are returned from get_n_most_recent without specifying deserialization
        method in method call, instead relying on serialization key embedded within entry.
        """
        caller, caller_name = caller
        responder, responder_name = responder

        for i in range(10):
            data = {"data": i}
            responder.entry_write("test_stream_arrow_serialized", data, serialization="arrow")
            # Ensure that serialization keeps the original data in tact
            assert data["data"] == i
        entries = caller.entry_read_n(responder_name,
                                      "test_stream_arrow_serialized",
                                      5)
        assert len(entries) == 5
        assert entries[0]["data"] == 9
        assert entries[-1]["data"] == 5

    def test_add_entry_and_get_n_most_recent_arrow_numpy_serialized(self, caller, responder):
        """
        Adds 10 entries to the responder's stream with Apache Arrow serialization and makes sure
        that the proper values are returned from get_n_most_recent without specifying deserialization
        method in method call, instead relying on serialization key embedded within entry.
        """
        caller, caller_name = caller
        responder, responder_name = responder

        for i in range(10):
            data = {"data":np.ones((3,3)) * i}
            responder.entry_write("test_stream_arrow_numpy_serialized", data, serialization="arrow")
        entries = caller.entry_read_n(responder_name,
                                      "test_stream_arrow_numpy_serialized",
                                      5)
        assert len(entries) == 5
        assert np.array_equal(entries[0]["data"], np.ones((3,3)) * 9)
        assert np.array_equal(entries[-1]["data"], np.ones((3,3)) * 5)

    def test_add_entry_arrow_serialize_custom_type(self, caller, responder):
        """
        Attempts to add an arrow-serialized entry of a custom (not Python built-in) type.
        Ensures that TypeError is raised.
        """
        caller, caller_name = caller
        responder, responder_name = responder

        class CustomClass():
            pass

        inst = CustomClass()

        with pytest.raises(TypeError) as excinfo:
            responder.entry_write("test_arrow_custom_type", {"data": inst}, serialization="arrow")

        print(excinfo.value)
        assert "not serializeable by pyarrow without pickling" in str(excinfo.value)

        #   Test collection containing non-serializeable type
        with pytest.raises(TypeError) as excinfo:
            responder.entry_write("test_arrow_custom_type", {"data": [inst]}, serialization="arrow")

        print(excinfo.value)
        assert "not serializeable by pyarrow without pickling" in str(excinfo.value)

    def test_add_command(self, responder):
        """
        Ensures that a command can be added to a responder.
        """
        responder, responder_name = responder

        responder.command_add("test_command", lambda x: x, timeout=123)
        assert "test_command" in responder.handler_map
        assert responder.timeouts["test_command"] == 123

    def test_clean_up_stream(self, responder):
        """
        Ensures that a stream can be removed from Redis and removed from responder's streams set.
        """
        responder, responder_name = responder

        responder.entry_write("clean_me", {"data": 0})

        assert "stream:%s:clean_me" % (responder_name,) in responder.get_all_streams()
        responder.clean_up_stream("clean_me")

        assert "stream:%s:clean_me" % (responder_name,) not in responder.get_all_streams()
        assert "clean_me" not in responder.streams
        self._assert_cleaned_up(responder)

    def test_clean_up(self, responder):
        """
        Ensures that a responder can be removed from Redis
        """
        responder, responder_name = responder

        new_responder = self._element_create("new_responder")
        assert "new_responder" in responder.get_all_elements()
        del new_responder
        # Explicitly invoke collection after ref count set to 0
        gc.collect()
        assert "new_responder" not in responder.get_all_elements()

    def test_command_response(self, caller, responder):
        """
        Element sends command and responder returns response.
        Tests expected use case of command response.
        """
        caller, caller_name = caller
        responder, responder_name = responder

        responder.command_add("add_1", add_1)
        self._element_start(responder, caller)
        response = caller.command_send(responder_name, "add_1", 42)
        self._element_cleanup(responder)
        assert response["err_code"] == ATOM_NO_ERROR
        assert response["data"] == b"43"

    def test_log_fail_in_command_loop(self, caller, responder):
        caller, caller_name = caller
        responder, responder_name = responder
        def fail(x):
            raise ValueError("oh no")

        responder.command_add("fail", fail)

        # this should be a non-blocking call
        responder.command_loop(n_procs=1, block=False)
        response = caller.command_send(responder_name, "fail", 42)
        responder.command_loop_shutdown()
        del responder

    def test_command_response_n_procs_2_no_fork(self, caller, responder):
        """
        Element sends command and responder returns response.
        Tests expected use case of command response.
        """
        caller, caller_name = caller
        responder, responder_name = responder

        responder.command_add("add_1", add_1)

        # this should be a non-blocking call
        responder.command_loop(n_procs=2, block=False)

        response = caller.command_send(responder_name, "add_1", 42)
        response2 = caller.command_send(responder_name, "add_1", 43)
        response3 = caller.command_send(responder_name, "add_1", 44)

        responder.command_loop_shutdown()

        assert response["err_code"] == ATOM_NO_ERROR
        assert response["data"] == b"43"

        assert response2["err_code"] == ATOM_NO_ERROR
        assert response2["data"] == b"44"

        assert response3["err_code"] == ATOM_NO_ERROR
        assert response3["data"] == b"45"
        time.sleep(0.5)
        del responder

    def test_command_response_n_procs_2_threads(self, caller, responder):
        """
        Element sends command and responder returns response.
        Tests expected use case of command response.
        """
        caller, caller_name = caller
        responder, responder_name = responder

        responder.command_add("add_1", add_1)

        thread = Thread(target=responder.command_loop, kwargs={'n_procs': 2})
        thread.start()

        response = caller.command_send(responder_name, "add_1", 42)
        response2 = caller.command_send(responder_name, "add_1", 43)
        response3 = caller.command_send(responder_name, "add_1", 44)

        responder.command_loop_shutdown()

        thread.join()

        assert response["err_code"] == ATOM_NO_ERROR
        assert response["data"] == b"43"

        assert response2["err_code"] == ATOM_NO_ERROR
        assert response2["data"] == b"44"

        assert response3["err_code"] == ATOM_NO_ERROR
        assert response3["data"] == b"45"

    def test_command_response_n_procs_2(self, caller, responder):
        """
        Element sends command and responder returns response.
        Tests expected use case of command response.
        """
        caller, caller_name = caller
        responder, responder_name = responder

        responder.command_add("add_1", add_1)

        proc = Process(target=responder.command_loop, kwargs={'n_procs': 2})
        proc.start()

        response = caller.command_send(responder_name, "add_1", 42)
        response2 = caller.command_send(responder_name, "add_1", 43)
        response3 = caller.command_send(responder_name, "add_1", 44)

        responder.command_loop_shutdown()

        proc.join()

        assert response["err_code"] == ATOM_NO_ERROR
        assert response["data"] == b"43"

        assert response2["err_code"] == ATOM_NO_ERROR
        assert response2["data"] == b"44"

        assert response3["err_code"] == ATOM_NO_ERROR
        assert response3["data"] == b"45"

    def test_command_response_legacy_serialized(self, caller, responder):
        """
        Element sends command and responder returns response.
        Tests expected use case of command response.
        """
        caller, caller_name = caller
        responder, responder_name = responder

        def add_1_serialized(data):
            return Response(data+1, serialize=True)

        responder.command_add("add_1_3", add_1_serialized, deserialize=True)
        self._element_start(responder, caller)
        response = caller.command_send(responder_name, "add_1_3", 0, serialize=True, deserialize=True)
        self._element_cleanup(responder)
        assert response["err_code"] == ATOM_NO_ERROR
        assert response["data"] == 1

    def test_command_response_mixed_serialization(self, caller, responder):
        """
        Ensures that command and response are serialized correctly based on serialization specified.
        """
        caller, caller_name = caller
        responder, responder_name = responder

        def add_1_arrow_serialized(data):
            return Response(data + 1, serialization="arrow")

        responder.command_add("test_command", add_1_arrow_serialized, serialization="msgpack")
        assert "test_command" in responder.handler_map
        assert responder.handler_map["test_command"]["serialization"] == "msgpack"
        self._element_start(responder, caller)
        response = caller.command_send(responder_name, "test_command", 123, serialization="msgpack")
        self._element_cleanup(responder)
        assert response["err_code"] == ATOM_NO_ERROR
        assert response["data"] == 124

    def test_listen_on_streams(self, caller, responder):
        """
        Creates two responders publishing entries on their respective streams with
        a caller listening on those streams and publishing data to a new stream.
        This test ensures that the new stream contains all the data from the responders.
        """
        caller, caller_name = caller
        responder, responder_name = responder

        responder_0_name = responder_name + '_0'
        responder_1_name = responder_name + '_1'

        responder_0 = self._element_create(responder_0_name)
        responder_1 = self._element_create(responder_1_name)
        entries = set()

        def entry_write_loop(responder, stream_name, data):
            # Wait until both responders and the caller are ready
            while -1 not in entries or -2 not in entries:
                responder.entry_write(stream_name, {"value": data-2}, serialization="msgpack")
            for i in range(10):
                responder.entry_write(stream_name, {"value": data}, serialization="msgpack")
                data += 2

        def add_entries(data):
            entries.add(data["value"])

        proc_responder_0 = Thread(target=entry_write_loop, args=(responder_0, "stream_0", 0,))
        proc_responder_1 = Thread(target=entry_write_loop, args=(responder_1, "stream_1", 1,))

        stream_handlers = [
            StreamHandler(responder_0_name, "stream_0", add_entries),
            StreamHandler(responder_1_name, "stream_1", add_entries),
        ]
        thread_caller = Thread(target=caller.entry_read_loop, args=(stream_handlers, None, 1000, True,), daemon=True)
        thread_caller.start()
        proc_responder_0.start()
        proc_responder_1.start()
        proc_responder_0.join()
        proc_responder_1.join()
        # Wait to give the caller time to handle all the data from the streams
        thread_caller.join(5.0)
        caller._rclient.delete(f"stream:{responder_0_name}:stream_0")
        caller._rclient.delete(f"stream:{responder_1_name}:stream_1")
        for i in range(20):
            assert i in entries

        self._element_cleanup(responder_0)
        self._element_cleanup(responder_1)

    def test_read_since(self, caller, responder):
        """
        Sets the current timestamp as last_id and writes 5 entries to a stream.
        Ensures that we can get 5 entries since the last id using entry_read_since.
        """
        caller, caller_name = caller
        responder, responder_name = responder

        responder.entry_write("test_stream", {"data": None})

        # Sleep so that last_id is later than the first entry
        time.sleep(0.01)
        last_id = responder._get_redis_timestamp()

        # Sleep so that the entries are later than last_id
        time.sleep(0.01)

        for i in range(5):
            responder.entry_write("test_stream", {"data": i})

        # Ensure this doesn't get an entry (because it's waiting for new entries and they never come)
        entries = caller.entry_read_since(responder_name, "test_stream")
        assert(len(entries) == 0)

        # Ensure this gets all entries
        entries = caller.entry_read_since(responder_name, "test_stream",last_id='0')
        assert(len(entries) == 6)

        # Ensure we get the correct number of entries since the last_id
        entries = caller.entry_read_since(responder_name, "test_stream", last_id)
        assert(len(entries) == 5)

        # Ensure that if we pass n, we get the n earliest entries since last_id
        entries = caller.entry_read_since(responder_name, "test_stream", last_id, 2)
        assert(len(entries) == 2)
        assert entries[-1]["data"] == b"1"

        # Ensure that last_id=='$' only gets new entries arriving after the call
        q = Queue()
        def wrapped_read(q):
            q.put(caller.entry_read_since(responder_name, "test_stream", block=500))
        proc = Process(target=wrapped_read, args=(q,))
        proc.start()
        time.sleep(0.1) #sleep to give the process time to start listening for new entries
        responder.entry_write("test_stream", {"data": None})
        entries = q.get()
        responder.command_loop_shutdown()
        proc.join()
        proc.terminate()
        assert(len(entries) == 1)

    def test_parallel_read_write(self, caller, responder):
        """
        Has the same responder class receiving commands on 1 thread,
        while publishing to a stream on a 2nd thread at high volume.
        Meanwhile, a caller quickly sends a series of commands to the responder and verifies
        we get valid results back.
        Ensures that we can safely send and receive using the same element class without concurrency issues.
        """
        caller, caller_name = caller
        responder, responder_name = responder
        responder_0_name = responder_name + '_0'
        responder_0 = self._element_create(responder_0_name)
        # NO_OP command responds with whatever data it receives
        def no_op_serialized(data):
            return Response(data, serialization="msgpack")
        responder_0.command_add("no_op", no_op_serialized, serialization="msgpack")

        # Entry write loop mimics high volume publisher
        def entry_write_loop(responder):
            for i in range(3000):
                responder.entry_write("stream_0", {"value": 0}, serialization="msgpack")
                time.sleep(0.0001)

        # Command loop thread to handle incoming commands
        self._element_start(responder_0, caller)
        # Entry write thread to publish a whole bunch to a stream
        entry_write_thread = Thread(target=entry_write_loop, args=(responder_0,), daemon=True)
        entry_write_thread.start()

        # Send a bunch of commands to responder and you should get valid responses back,
        # even while its busy publishing to a stream
        try:
            for i in range(20):
                response = caller.command_send(responder_0_name, "no_op", 1, serialization="msgpack")
                assert response["err_code"] == ATOM_NO_ERROR
                assert response["data"] == 1
        finally:
            # Cleanup threads
            entry_write_thread.join()
            self._element_cleanup(responder_0)
            del responder_0

    def test_healthcheck_default(self, caller, responder):
        """
        Verify default healthcheck
        """
        caller, caller_name = caller
        responder, responder_name = responder

        self._element_start(responder, caller)
        response = caller.command_send(responder_name, HEALTHCHECK_COMMAND)
        assert response["err_code"] == ATOM_NO_ERROR
        assert response["data"] == b""
        self._element_cleanup(responder)

    def test_healthcheck_success(self, caller, responder):
        """
        Verify a successful response from a custom healthcheck
        """
        caller, caller_name = caller
        responder = self._element_create('healthcheck_success_responder')

        responder.healthcheck_set(lambda: Response(err_code=0, err_str="We're good"))
        self._element_start(responder, caller)
        response = caller.command_send('healthcheck_success_responder', HEALTHCHECK_COMMAND)
        assert response["err_code"] == ATOM_NO_ERROR
        assert response["data"] == b""
        assert response["err_str"] == "We're good"
        self._element_cleanup(responder)

    def test_healthcheck_failure(self, caller, responder):
        """
        Verify a failed response from a custom healthcheck
        """
        responder = self._element_create('healthcheck_failure_responder')
        caller, caller_name = caller

        responder.healthcheck_set(lambda: Response(err_code=5, err_str="Camera is unplugged"))
        self._element_start(responder, caller, do_healthcheck=False)
        response = caller.command_send('healthcheck_failure_responder', HEALTHCHECK_COMMAND)
        assert response["err_code"] == 5 + ATOM_USER_ERRORS_BEGIN
        assert response["data"] == b""
        assert response["err_str"] == "Camera is unplugged"
        self._element_cleanup(responder)

    def test_wait_for_elements_healthy(self, caller, responder):
        """
        Verify wait_for_elements_healthy success/failure cases
        """
        caller, caller_name = caller
        responder, responder_name = responder

        self._element_start(responder, caller)

        def wait_for_elements_check(caller, elements_to_check):
            caller.wait_for_elements_healthy(elements_to_check)

        wait_for_elements_thread = Thread(target=wait_for_elements_check, args=(caller, [responder_name]), daemon=True)
        wait_for_elements_thread.start()
        # If elements reported healthy, call should have returned quickly and thread should exit
        wait_for_elements_thread.join(0.5)
        assert not wait_for_elements_thread.is_alive()

        wait_for_elements_thread = Thread(target=wait_for_elements_check, args=(caller, [responder_name, 'test_responder_2']), daemon=True)
        wait_for_elements_thread.start()
        # 1 of these elements is missing, so thread is busy and this join call should timeout retrying
        wait_for_elements_thread.join(0.5)
        assert wait_for_elements_thread.is_alive()

        try:
            responder_2 = self._element_create("test_responder_2")
            self._element_start(responder_2, caller, do_healthcheck=False)

            # test_responder_2 is alive now, so both healthchecks should succeed and thread should exit roughly within the retry interval
            wait_for_elements_thread.join(HEALTHCHECK_RETRY_INTERVAL + 1.0)
            assert not wait_for_elements_thread.is_alive()
        finally:
            # Cleanup threads
            self._element_cleanup(responder_2)
            del responder_2

        self._element_cleanup(responder)

    def test_version_command(self, caller, responder):
        """
        Verify the response from the get_element_version command
        """
        caller, caller_name = caller
        responder, responder_name = responder

        self._element_start(responder, caller)
        response = caller.command_send(
            responder_name,
            VERSION_COMMAND,
            serialization="msgpack"
        )
        assert response["err_code"] == ATOM_NO_ERROR
        assert response["data"] == {"version": float(".".join(VERSION.split(".")[:-1])), "language": LANG}
        response2 = caller.get_element_version(responder_name)
        assert response == response2
        self._element_cleanup(responder)

    def test_command_list_command(self, caller, responder):
        """
        Verify the response from the COMMAND_LIST_COMMAND command
        """

        caller, caller_name = caller
        responder, responder_name = responder

        # Test with no commands
        no_command_responder = self._element_create('no_command_responder')
        self._element_start(no_command_responder, caller)
        assert caller.command_send(no_command_responder.name, COMMAND_LIST_COMMAND, serialization="msgpack")["data"] == []
        self._element_cleanup(no_command_responder)
        del no_command_responder

        responder = self._element_create('responder_with_commands')
        # Add commands to responder
        responder.command_add('foo_func1', lambda data: data)
        responder.command_add('foo_func2', lambda: None, timeout=500, serialization="msgpack")
        responder.command_add('foo_func3', lambda x, y: x + y, timeout=1, serialization="msgpack")
        self._element_start(responder, caller)

        # Test with three commands
        response = caller.command_send(responder.name, COMMAND_LIST_COMMAND, serialization="msgpack")
        assert response["err_code"] == ATOM_NO_ERROR
        assert response["data"] == ['foo_func1', 'foo_func2', 'foo_func3']

        self._element_cleanup(responder)

    def test_get_all_commands_with_version(self, caller, responder):
        """
        Ensure get_all_commands only queries support elements.
        """
        caller, caller_name = caller
        responder, responder_name = responder

        # Change responder reported version
        responder.handler_map[VERSION_COMMAND]['handler'] = \
            lambda: Response(data={'language': 'Python', 'version': 0.2}, serialization="msgpack")
        # Create element with normal, supported version
        responder2_name = responder_name + '_2'
        responder2 = self._element_create(responder2_name)

        # Add commands to both responders and start command loop
        responder.command_add('foo_func0', lambda data: data)
        responder2.command_add('foo_func0', lambda: None, timeout=500, serialization="msgpack")
        responder2.command_add('foo_func1', lambda x, y: x + y, timeout=1, serialization="msgpack")
        self._element_start(responder, caller)
        self._element_start(responder2, caller)

        # Retrieve commands
        commands = caller.get_all_commands(
            element_name=[responder_name, responder2_name]
        )
        # Do not include responder's commands as the version is too low
        desired_commands = [f'{responder2_name}:foo_func0', f'{responder2_name}:foo_func1']
        assert commands == desired_commands

        self._element_cleanup(responder)
        self._element_cleanup(responder2)
        del responder2

    def test_get_all_commands(self, caller, responder):
        """
        Verify the response from the get_all_commands command
        """
        caller, caller_name = caller
        responder, responder_name = responder

        # Test with no available commands
        assert caller.get_all_commands() == []

        # Set up two responders
        test_name_1, test_name_2 = responder_name + '_1', responder_name + '_2'
        responder1, responder2 = self._element_create(test_name_1), self._element_create(test_name_2)

        proc1_function_data = [('foo_func0', lambda x: x + 3),
                               ('foo_func1', lambda: None, 10, "arrow"),
                               ('foo_func2', lambda x: None)]
        proc2_function_data = [('foo_func0', lambda y: y * 3, 10),
                               ('other_foo0', lambda y: None, 3, "msgpack"),
                               ('other_foo1', lambda: 5)]

        # Add functions
        for data in proc1_function_data:
            responder1.command_add(*data)
        for data in proc2_function_data:
            responder2.command_add(*data)

        self._element_start(responder1, caller)
        self._element_start(responder2, caller)

        # True function names
        responder1_function_names = [f'{test_name_1}:foo_func{i}' for i in range(3)]
        responder2_function_names = [f'{test_name_2}:foo_func0',
                                     f'{test_name_2}:other_foo0',
                                     f'{test_name_2}:other_foo1']

        # Either order of function names is fine for testing all function names
        command_list = caller.get_all_commands()
        assert (command_list == responder1_function_names + responder2_function_names or
                command_list == responder2_function_names + responder1_function_names)

        # Test just functions for 1
        command_list = caller.get_all_commands(test_name_1)
        assert command_list == responder1_function_names

        # Test just functions for 2
        command_list = caller.get_all_commands(test_name_2)
        assert command_list == responder2_function_names

        self._element_cleanup(responder1)
        self._element_cleanup(responder2)
        del responder1
        del responder2

    def test_no_ack(self, caller, responder):
        """
        Element sends command and responder does not acknowledge.
        """
        caller, caller_name = caller
        responder, responder_name = responder

        responder.command_add("add_1", add_1)
        response = caller.command_send(responder_name, "add_1", 0)
        assert response["err_code"] == ATOM_COMMAND_NO_ACK

    def test_unsupported_command(self, caller, responder):
        """
        Element sends command that responder does not have.
        """
        caller, caller_name = caller
        responder, responder_name = responder

        self._element_start(responder, caller)
        response = caller.command_send(responder_name, "add_1", 0)

        self._element_cleanup(responder)
        assert response["err_code"] == ATOM_COMMAND_UNSUPPORTED

    def test_command_timeout(self, caller, responder):
        """
        Element sends command to responder that does not return data within the timeout.
        """
        caller, caller_name = caller
        responder, responder_name = responder

        # Set a timeout of 10 ms
        responder.command_add("sleep_ms", sleep_ms, 10, serialization='msgpack')
        self._element_start(responder, caller)
        response = caller.command_send(responder_name, "sleep_ms", 1000, serialization='msgpack')
        self._element_cleanup(responder)
        assert response["err_code"] == ATOM_COMMAND_NO_RESPONSE

    def test_handler_returns_not_response(self, caller, responder):
        """
        Element calls command from responder that does not return an object of
        type Response.
        """
        caller, caller_name = caller
        responder, responder_name = responder

        responder.command_add("ret_not_response", lambda x: 0)
        self._element_start(responder, caller)
        response = caller.command_send(responder_name, "ret_not_response", None)
        self._element_cleanup(responder)
        assert response["err_code"] == ATOM_CALLBACK_FAILED

    def test_log(self, caller):
        """
        Writes a log with each severity level and ensures that all the logs exist.
        """
        caller, caller_name = caller
        for i, severity in enumerate(LogLevel):
            caller.log(severity, f"severity {i}", stdout=False)
        logs = caller._rclient.xread({"log": 0})[0][1]
        logs = logs[-8:]
        for i in range(8):
            assert logs[i][1][b"msg"].decode() == f"severity {i}"

    def test_contracts(self):
        class RawContractTest(RawContract):
            data = BinaryProperty(required=True)

        class EmptyContractTest(EmptyContract):
            pass

        test_raw = RawContractTest(data=b'test_binary')
        assert test_raw.to_data() == b'test_binary'

        test_raw = RawContractTest(b'test_binary')
        assert test_raw.to_data() == b'test_binary'

        test_raw = RawContractTest('test_binary')
        assert test_raw.to_data() == b'test_binary'

        test_empty = EmptyContractTest()
        assert test_empty.to_data() == ""

    def test_reference_basic(self, caller):
        caller, caller_name = caller
        data = b'hello, world!'
        ref_id = caller.reference_create(data)[0]
        ref_data = caller.reference_get(ref_id)[0]
        assert ref_data == data
        caller.reference_delete(ref_id)

    def test_reference_doesnt_exist(self, caller):
        caller, caller_name = caller
        ref_id = "nonexistent"
        ref_data = caller.reference_get(ref_id)[0]
        assert ref_data is None

    def test_reference_legacy_serialization(self, caller):
        caller, caller_name = caller
        data = {"hello" : "world", "atom" : 123456, "some_obj" : {"references" : "are fun!"} }
        ref_id = caller.reference_create(data, serialize=True)[0]
        ref_data = caller.reference_get(ref_id, deserialize=True)[0]
        assert ref_data == data
        caller.reference_delete(ref_id)

    def test_reference_arrow(self, caller):
        """
        Creates references serialized with Apache Arrow; gets references and deserializes
        based on serialization method embedded within reference key.
        """
        caller, caller_name = caller
        data = {"hello" : "world", "atom" : 123456, "some_obj" : {"references" : "are fun!"} }
        ref_id = caller.reference_create(data, serialization="arrow")[0]
        ref_data = caller.reference_get(ref_id)[0]
        assert ref_data == data
        caller.reference_delete(ref_id)

    def test_reference_msgpack_dne(self, caller):
        caller, caller_name = caller
        ref_id = "nonexistent"
        ref_data = caller.reference_get(ref_id, serialization="msgpack")[0]
        assert ref_data is None

    def test_reference_multiple(self, caller):
        caller, caller_name = caller
        data = [b'hello, world!', b'robots are fun!']
        ref_ids = caller.reference_create(*data)
        ref_data = caller.reference_get(*ref_ids)
        for i in range(len(data)):
            assert ref_data[i] == data[i]
        caller.reference_delete(*ref_ids)

    def test_reference_multiple_msgpack(self, caller):
        caller, caller_name = caller
        data = [{"hello" : "world", "atom" : 123456, "some_obj" : {"references" : "are fun!"}}, True]
        ref_ids = caller.reference_create(*data, serialization="msgpack")
        ref_data = caller.reference_get(*ref_ids)
        for i in range(len(data)):
            assert ref_data[i] == data[i]
        caller.reference_delete(*ref_ids)

    def test_reference_multiple_mixed_serialization(self, caller):
        caller, caller_name = caller
        data = [{"hello": "world"}, b'123456']
        ref_ids = [ ]
        ref_ids.extend(caller.reference_create(data[0], serialization="msgpack"))
        ref_ids.extend(caller.reference_create(data[1], serialization="none"))
        ref_data = caller.reference_get(*ref_ids)
        for ref, orig in zip(ref_data, data):
            assert ref == orig
        caller.reference_delete(*ref_ids)

    def test_reference_get_timeout_ms(self, caller):
        caller, caller_name = caller
        data = b'hello, world!'
        ref_id = caller.reference_create(data, timeout_ms=1000)[0]
        ref_remaining_ms = caller.reference_get_timeout_ms(ref_id)
        assert ref_remaining_ms > 0 and ref_remaining_ms <= 1000
        time.sleep(0.1)
        ref_still_remaining_ms = caller.reference_get_timeout_ms(ref_id)
        assert (ref_still_remaining_ms < ref_remaining_ms) and (ref_still_remaining_ms > 0)
        caller.reference_delete(ref_id)

    def test_reference_update_timeout_ms(self, caller):
        caller, caller_name = caller
        data = b'hello, world!'
        ref_id = caller.reference_create(data, timeout_ms=1000)[0]
        ref_remaining_ms = caller.reference_get_timeout_ms(ref_id)
        assert ref_remaining_ms > 0 and ref_remaining_ms <= 1000

        caller.reference_update_timeout_ms(ref_id, 10000)
        ref_updated_ms = caller.reference_get_timeout_ms(ref_id)
        assert (ref_updated_ms > 1000) and (ref_updated_ms <= 10000)
        caller.reference_delete(ref_id)

    def test_reference_remove_timeout(self, caller):
        caller, caller_name = caller
        data = b'hello, world!'
        ref_id = caller.reference_create(data, timeout_ms=1000)[0]
        ref_remaining_ms = caller.reference_get_timeout_ms(ref_id)
        assert ref_remaining_ms > 0 and ref_remaining_ms <= 1000

        caller.reference_update_timeout_ms(ref_id, 0)
        ref_updated_ms = caller.reference_get_timeout_ms(ref_id)
        assert ref_updated_ms == -1
        caller.reference_delete(ref_id)

    def test_reference_delete(self, caller):
        caller, caller_name = caller
        data = b'hello, world!'
        ref_id = caller.reference_create(data, timeout_ms=0)[0]
        ref_data = caller.reference_get(ref_id)[0]
        assert ref_data == data

        ref_ms = caller.reference_get_timeout_ms(ref_id)
        assert ref_ms == -1

        caller.reference_delete(ref_id)
        del_data = caller.reference_get(ref_id)[0]
        assert del_data is None

    def test_reference_delete_multiple(self, caller):
        caller, caller_name = caller

        data = [b'hello, world!', b'test']
        ref_ids = caller.reference_create(*data, timeout_ms=0)
        ref_data = caller.reference_get(*ref_ids)
        assert ref_data[0] == data[0]
        assert ref_data[1] == data[1]

        ref_ms = caller.reference_get_timeout_ms(ref_ids[0])
        assert ref_ms == -1
        ref_ms = caller.reference_get_timeout_ms(ref_ids[1])
        assert ref_ms == -1

        caller.reference_delete(*ref_ids)
        del_data = caller.reference_get(*ref_ids)
        assert del_data[0] is None
        assert del_data[1] is None

    def test_reference_delete_msgpack(self, caller):
        caller, caller_name = caller

        data = {"msgpack" : "data"}
        ref_id = caller.reference_create(data, timeout_ms=0, serialization="msgpack")[0]
        ref_data = caller.reference_get(ref_id)[0]
        assert ref_data == data

        ref_ms = caller.reference_get_timeout_ms(ref_id)
        assert ref_ms == -1

        caller.reference_delete(ref_id)
        del_data = caller.reference_get(ref_id)[0]
        assert del_data is None

    def test_reference_expire(self, caller):
        caller, caller_name = caller

        data = {"msgpack" : "data"}
        ref_id = caller.reference_create(data, serialization="msgpack", timeout_ms=500)[0]
        ref_data = caller.reference_get(ref_id)[0]
        assert ref_data == data

        time.sleep(0.5)
        expired_data = caller.reference_get(ref_id)[0]
        assert expired_data is None

    def test_reference_create_from_stream_single_key(self, caller):
        caller, caller_name = caller

        stream_name = "test_ref"
        stream_data = {"data": b"test reference!"}
        caller.entry_write(stream_name, stream_data)
        key_dict = caller.reference_create_from_stream(caller.name, stream_name, timeout_ms=0)
        ref_data = caller.reference_get(key_dict["data"])[0]
        assert ref_data == stream_data["data"]
        caller.reference_delete(key_dict["data"])

    def test_reference_create_from_stream_multiple_keys(self, caller):
        caller, caller_name = caller

        stream_name = "test_ref_multiple_keys"
        stream_data = {"key1": b"value 1!", "key2" : b"value 2!"}
        caller.entry_write(stream_name, stream_data)
        key_dict = caller.reference_create_from_stream(caller.name, stream_name, timeout_ms=0)
        for key in key_dict:
            ref_data = caller.reference_get(key_dict[key])[0]
            assert ref_data == stream_data[key]
        caller.reference_delete(*key_dict.values())

    def test_reference_create_from_stream_multiple_keys_legacy_serialization(self, caller):
        caller, caller_name = caller

        stream_name = "test_ref_multiple_keys"
        stream_data = {"key1": {"nested1": "val1"}, "key2" : {"nested2": "val2"}}
        orig_stream_data = copy.deepcopy(stream_data)
        caller.entry_write(stream_name, stream_data, serialize=True)
        key_dict = caller.reference_create_from_stream(caller.name, stream_name, timeout_ms=0)
        for key in key_dict:
            ref_data = caller.reference_get(key_dict[key], deserialize=True)[0]
            assert ref_data == orig_stream_data[key]
        caller.reference_delete(*key_dict.values())

    def test_reference_create_from_stream_multiple_keys_arrow(self, caller):
        caller, caller_name = caller

        stream_name = "test_ref_multiple_keys"
        stream_data = {"key1": {"nested1": "val1"}, "key2" : {"nested2": "val2"}}
        orig_stream_data = copy.deepcopy(stream_data)
        caller.entry_write(stream_name, stream_data, serialization="arrow")
        key_dict = caller.reference_create_from_stream(caller.name, stream_name, timeout_ms=0)
        for key in key_dict:
            ref_data = caller.reference_get(key_dict[key])[0]
            assert ref_data == orig_stream_data[key]
        caller.reference_delete(*key_dict.values())

    def test_reference_create_from_stream_multiple_keys_persist(self, caller):
        caller, caller_name = caller

        stream_name = "test_ref_multiple_keys"
        stream_data = {"key1": b"value 1!", "key2" : b"value 2!"}
        caller.entry_write(stream_name, stream_data)
        key_dict = caller.reference_create_from_stream(caller.name, stream_name, timeout_ms=0)
        for key in key_dict:
            assert caller.reference_get_timeout_ms(key_dict[key]) == -1
        caller.reference_delete(*key_dict.values())

    def test_reference_create_from_stream_multiple_keys_timeout(self, caller):
        caller, caller_name = caller

        stream_name = "test_ref_multiple_keys"
        stream_data = {"key1": b"value 1!", "key2" : b"value 2!"}
        caller.entry_write(stream_name, stream_data)
        key_dict = caller.reference_create_from_stream(caller.name, stream_name, timeout_ms=500)
        for key in key_dict:
            ref_data = caller.reference_get(key_dict[key])[0]
            assert ref_data == stream_data[key]
        time.sleep(0.5)
        for key in key_dict:
            assert caller.reference_get(key_dict[key])[0] is None

    def test_reference_create_from_stream_multiple_keys_latest(self, caller):
        caller, caller_name = caller

        def get_data(i):
            return {"key1": f"value {i}!", "key2" : f"value {i}!"}

        stream_name = "test_ref_multiple_keys"

        # Write all of the keys and get IDs back
        ids = []
        for i in range(10):
            stream_data = get_data(i)
            ids.append(caller.entry_write(stream_name, stream_data, serialization="msgpack"))

        # Check that we can get each of them individually
        for i, id_val in enumerate(ids):

            # Make the reference to the particular ID
            key_dict = caller.reference_create_from_stream(caller.name, stream_name, stream_id=id_val, timeout_ms=0)

            # Loop over the references and check the data
            for key in key_dict:

                ref_data = caller.reference_get(key_dict[key])[0]
                correct_data = get_data(i)
                assert ref_data == correct_data[key]
            caller.reference_delete(*key_dict.values())

        # Now, check the final piece and make sure it's the most recent
        key_dict = caller.reference_create_from_stream(caller.name, stream_name, timeout_ms=0)

        # Loop over the references and check the data
        for key in key_dict:

            ref_data = caller.reference_get(key_dict[key])[0]
            correct_data = get_data(9)
            assert ref_data == correct_data[key]

        caller.reference_delete(*key_dict.values())

    def test_entry_read_n_ignore_serialization(self, caller):
        caller, caller_name = caller

        test_data = {"some_key" : "some_val"}
        caller.entry_write("test_stream", {"data": test_data}, serialization="msgpack")
        entries = caller.entry_read_n(
            caller_name,
            "test_stream",
            1,
            serialization=None,
            force_serialization=True
        )
        assert test_data == unpackb(entries[0]["data"], raw=False)

    def test_entry_read_since_ignore_serialization(self, caller):
        caller, caller_name = caller

        test_data_1 = {"some_key" : "some_val"}
        test_data_2 = {"some_other_key" : "some_other_val"}
        data_1_id = caller.entry_write("test_stream", {"data": test_data_1}, serialization="msgpack")
        data_2_id = caller.entry_write("test_stream", {"data": test_data_2}, serialization="msgpack")

        entries = caller.entry_read_since(caller_name, "test_stream", last_id=data_1_id, serialization=None, force_serialization=True)
        assert test_data_2 == unpackb(entries[0]["data"], raw=False)

    def test_reference_ignore_serialization(self, caller):
        caller, caller_name = caller

        data = [{"hello" : "world", "atom" : 123456, "some_obj" : {"references" : "are fun!"}}, True]
        ref_ids = caller.reference_create(*data, serialization="msgpack")
        ref_data = caller.reference_get(*ref_ids, serialization=None, force_serialization=True)
        for i in range(len(data)):
            assert unpackb(ref_data[i], raw=False) == data[i]
        caller.reference_delete(*ref_ids)

    def test_command_response_wrong_n_procs(self, caller, responder):
        """
        Element sends command and responder returns response.
        Tests expected use case of command response.
        """
        caller, caller_name = caller
        responder, responder_name = responder

        responder.command_add("add_1", add_1)
        # this should be a non-blocking call
        with pytest.raises(ValueError):
            responder.command_loop(n_procs=-1)

    def test_timeout_ms(self):
        then = time.time()

        with pytest.raises(ElementConnectionTimeoutError):
            e = self._element_create('timeout-element-1', host='10.255.255.1', conn_timeout_ms=2000)
            assert e._redis_connetion_timeout == 2.
            e._rclient.keys()

        now = time.time()
        diff = now - then

        assert int(round(diff, 2)) == 2

    def test_metrics_create_basic(self, caller, metrics):
        caller, caller_name = caller
        data = caller.metrics_create_custom(MetricsLevel.INFO, "some_metric", retention=10000)
        assert data == "some_metric"

        data = metrics.info("some_metric")
        assert data.retention_msecs == 10000

    def test_metrics_create_label(self, caller, metrics):
        caller, caller_name = caller
        label_dict = {"single" : "label"}
        data = caller.metrics_create_custom(MetricsLevel.INFO, "some_metric", labels=label_dict)
        assert data == "some_metric"

        data = metrics.info("some_metric")
        assert data.labels == {**label_dict, **{"agg": "none", "agg_type" : "none"}}

    def test_metrics_create_labels(self, caller, metrics):
        caller, caller_name = caller
        label_dict = {"label1" : "hello", "label2" : "world"}
        data = caller.metrics_create_custom(MetricsLevel.INFO, "some_metric", labels=label_dict)
        assert data == "some_metric"

        data = metrics.info("some_metric")
        assert data.labels == {**label_dict, **{"agg": "none", "agg_type" : "none"}}

    def test_metrics_create_rule(self, caller, metrics):
        caller, caller_name = caller
        rule_dict = {"some_metric_sum" : ("sum", 10000, 200000)}
        data = caller.metrics_create_custom(MetricsLevel.INFO, "some_metric", rules=rule_dict)
        assert data == "some_metric"

        data = metrics.info("some_metric")
        assert len(data.rules) == 1
        assert data.rules[0][0] == b'some_metric_sum'
        assert data.rules[0][1] == 10000
        assert data.rules[0][2] == b'SUM'

        data = metrics.info("some_metric_sum")
        assert data.retention_msecs == 200000

    def test_metrics_create_rules(self, caller, metrics):
        caller, caller_name = caller
        rule_dict = {"some_metric_sum" : ("sum", 10000, 200000), "some_metric_avg" : ("avg", 86400, 604800)}

        data = caller.metrics_create_custom(MetricsLevel.INFO, "some_metric", rules=rule_dict)
        assert data == "some_metric"

        data = metrics.info("some_metric")
        assert len(data.rules) == 2
        sum_idx = 0 if data.rules[0][0] == b'some_metric_sum' else 1
        avg_idx = 1 if sum_idx == 0 else 0
        assert data.rules[sum_idx][0] == b'some_metric_sum'
        assert data.rules[sum_idx][1] == 10000
        assert data.rules[sum_idx][2] == b'SUM'
        assert data.rules[avg_idx][0] == b'some_metric_avg'
        assert data.rules[avg_idx][1] == 86400
        assert data.rules[avg_idx][2] == b'AVG'

        data = metrics.info("some_metric_sum")
        assert data.retention_msecs == 200000

        data = metrics.info("some_metric_avg")
        assert data.retention_msecs == 604800

    def test_metrics_create_already_created(self, caller, metrics):
        caller, caller_name = caller
        data = caller.metrics_create_custom(MetricsLevel.INFO, "some_metric", retention=10000)
        assert data == "some_metric"
        data = caller.metrics_create_custom(MetricsLevel.INFO, "some_metric", retention=10000)
        assert data == "some_metric"

    def test_metrics_create_update(self, caller, metrics):
        caller, caller_name = caller
        rule_dict = {"some_metric_sum" : ("sum", 10000, 200000), "some_metric_avg" : ("avg", 86400, 604800)}
        label_dict = {"label1" : "hello", "label2" : "world"}
        data = caller.metrics_create_custom(MetricsLevel.INFO, "some_metric", rules=rule_dict, labels=label_dict)
        assert data == "some_metric"

        data = metrics.info("some_metric")
        assert data.labels == {**label_dict, **{"agg": "none", "agg_type" : "none"}}
        assert len(data.rules) == 2
        sum_idx = 0 if data.rules[0][0] == b'some_metric_sum' else 1
        avg_idx = 1 if sum_idx == 0 else 0
        assert data.rules[sum_idx][0] == b'some_metric_sum'
        assert data.rules[sum_idx][1] == 10000
        assert data.rules[sum_idx][2] == b'SUM'
        assert data.rules[avg_idx][0] == b'some_metric_avg'
        assert data.rules[avg_idx][1] == 86400
        assert data.rules[avg_idx][2] == b'AVG'

        data = caller.metrics_create_custom(MetricsLevel.INFO, "some_metric", rules=rule_dict, labels=label_dict, update=True)
        assert data == "some_metric"
        rule_dict = {"some_metric_min" : ("min", 6000, 1000), "some_metric_max" : ("max", 5000, 10000)}
        label_dict = {"label1" : "elementary", "label2" : "robotics"}
        data = caller.metrics_create_custom(MetricsLevel.INFO, "some_metric", rules=rule_dict, labels=label_dict)
        assert data == "some_metric"
        data = caller.metrics_create_custom(MetricsLevel.INFO, "some_metric", rules=rule_dict, labels=label_dict, update=True)
        assert data == "some_metric"
        data = metrics.info("some_metric")
        assert data.labels == {**label_dict, **{"agg": "none", "agg_type" : "none"}}
        assert len(data.rules) == 2
        max_idx = 0 if data.rules[0][0] == b'some_metric_max' else 1
        min_idx = 1 if max_idx == 0 else 0
        assert data.rules[max_idx][0] == b'some_metric_max'
        assert data.rules[max_idx][1] == 5000
        assert data.rules[max_idx][2] == b'MAX'
        assert data.rules[min_idx][0] == b'some_metric_min'
        assert data.rules[min_idx][1] == 6000
        assert data.rules[min_idx][2] == b'MIN'


    def test_metrics_add(self, caller, metrics):
        caller, caller_name = caller
        data = caller.metrics_create_custom(MetricsLevel.INFO, "some_metric", retention=10000)
        assert data == "some_metric"

        data = caller.metrics_add("some_metric", 42)
        print(data)
        assert len(data) == 1 and type(data[0]) == list and len(data[0]) == 1 and type(data[0][0]) == int

        # make a metric and have the timestamp auto-created
        data = metrics.get("some_metric")
        assert data[1] == 42
        # Make sure the auto-generated timestamp is within 1s of the unix time
        assert ((time.time() * 1000) - data[0] <= 1000)

    def test_metrics_add_set_timestamp_int(self, caller, metrics):
        caller, caller_name = caller

        data = caller.metrics_create_custom(MetricsLevel.INFO, "some_metric", retention=10000)
        assert data == "some_metric"

        data = caller.metrics_add("some_metric", 42, timestamp=1)
        assert len(data) == 1 and type(data[0]) == list and len(data[0]) == 1 and type(data[0][0]) == int

        # make a metric and have the timestamp auto-created
        data = metrics.get("some_metric")
        assert data[1] == 42
        assert data[0] == 1

    def test_metrics_add_set_timestamp_time(self, caller, metrics):
        caller, caller_name = caller
        curr_time = int(time.time() * 1000)
        data = caller.metrics_create_custom(MetricsLevel.INFO, "some_metric", retention=10000)
        assert data == "some_metric"

        data = caller.metrics_add("some_metric", 42, timestamp=curr_time)
        assert len(data) == 1 and type(data[0]) == list and len(data[0]) == 1 and type(data[0][0]) == int

        # make a metric and have the timestamp auto-created
        data = metrics.get("some_metric")
        assert data[1] == 42
        assert data[0] == curr_time

    def test_metrics_add_multiple(self, caller, metrics):
        caller, caller_name = caller
        curr_time = int(time.time() * 1000)
        data = caller.metrics_create_custom(MetricsLevel.INFO, "some_metric", retention=10000)
        assert data == "some_metric"

        data = caller.metrics_add("some_metric", 42)
        assert len(data) == 1 and type(data[0]) == list and len(data[0]) == 1 and type(data[0][0]) == int

        time.sleep(0.001)
        data = caller.metrics_add("some_metric", 2020)
        assert len(data) == 1 and type(data[0]) == list and len(data[0]) == 1 and type(data[0][0]) == int

        # make a metric and have the timestamp auto-created
        data = metrics.range("some_metric", 0, -1)
        assert data[0][1] == 42
        assert data[1][1] == 2020

    def test_metrics_add_multiple_handle_same_timestamp(self, caller, metrics):
        caller, caller_name = caller
        curr_time = int(time.time() * 1000)
        data = caller.metrics_create_custom(MetricsLevel.INFO, "some_metric", retention=10000)
        assert data == "some_metric"
        data = caller.metrics_add("some_metric", 42, timestamp=1234)
        assert len(data) == 1 and type(data[0]) == list and len(data[0]) == 1 and type(data[0][0]) == int

        data = caller.metrics_add("some_metric", 2020, timestamp=1234)
        assert len(data) == 1 and type(data[0]) == list and data[0][0] == None

        # make a metric and have the timestamp auto-created
        data = metrics.range("some_metric", 0, -1)
        assert len(data) == 1
        assert data[0][1] == 42
        assert data[0][0] == 1234

    def test_metrics_async(self, caller, metrics):
        caller, caller_name = caller
        data = caller.metrics_create_custom(MetricsLevel.INFO, "some_metric", retention=10000)
        assert data == "some_metric"
        pipeline = caller.metrics_get_pipeline()
        assert pipeline != None
        pipeline = caller.metrics_get_pipeline()
        assert pipeline != None
        data = caller.metrics_add("some_metric", 42, pipeline=pipeline)
        assert data == None

        data = metrics.get("some_metric")
        assert data == None
        data = caller.metrics_write_pipeline(pipeline)
        assert data != None
        data = metrics.get("some_metric")
        assert type(data[0]) == int and data[1] == 42

    def test_metrics_add_multiple_simultaneous(self, caller, metrics):
        caller, caller_name = caller
        curr_time = int(time.time() * 1000)
        data = caller.metrics_create_custom(MetricsLevel.INFO, "some_metric", retention=10000)
        assert data == "some_metric"
        data = caller.metrics_create_custom(MetricsLevel.INFO, "some_other_metric", retention=10000)
        assert data == "some_other_metric"
        data = caller.metrics_add("some_metric", 42)
        assert data != None
        data = caller.metrics_add("some_other_metric", 2020)
        assert data != None

        # make a metric and have the timestamp auto-created
        data = metrics.range("some_metric", 0, -1)
        assert len(data) == 1 and data[0][1] == 42
        data = metrics.range("some_other_metric", 0, -1)
        assert len(data) == 1 and data[0][1] == 2020

    def test_metrics_add_multiple_simultaneous_async(self, caller, metrics):
        caller, caller_name = caller
        curr_time = int(time.time() * 1000)
        data = caller.metrics_create_custom(MetricsLevel.INFO, "some_metric", retention=10000)
        assert data == "some_metric"
        data = caller.metrics_create_custom(MetricsLevel.INFO, "some_other_metric", retention=10000)
        assert data == "some_other_metric"
        pipeline = caller.metrics_get_pipeline()
        assert pipeline != None
        data = caller.metrics_add("some_metric", 42, pipeline=pipeline)
        assert data == None
        data = caller.metrics_add("some_other_metric", 2020, pipeline=pipeline)
        assert data == None

        time.sleep(0.001)
        data = caller.metrics_write_pipeline(pipeline)
        assert data != None

        # make a metric and have the timestamp auto-created
        data = metrics.range("some_metric", 0, -1)
        assert len(data) == 1 and data[0][1] == 42
        data = metrics.range("some_other_metric", 0, -1)
        assert len(data) == 1 and data[0][1] == 2020

    def test_metrics_add_multiple_async(self, caller, metrics):
        caller, caller_name = caller
        curr_time = int(time.time() * 1000)
        data = caller.metrics_create_custom(MetricsLevel.INFO, "some_metric", retention=10000)
        assert data == "some_metric"
        pipeline = caller.metrics_get_pipeline()
        assert pipeline != None
        pipeline = caller.metrics_get_pipeline()
        assert pipeline != None
        data = caller.metrics_add("some_metric", 42, pipeline=pipeline)
        assert data == None
        time.sleep(0.001)
        data = caller.metrics_add("some_metric", 2020, pipeline=pipeline)
        assert data == None
        data = caller.metrics_write_pipeline(pipeline)
        assert data != None
        # make a metric and have the timestamp auto-created
        data = metrics.range("some_metric", 0, -1)
        assert len(data) == 2 and data[0][1] == 42 and data[1][1] == 2020

    def test_metrics_add_multiple_async_handle_same_timestamp(self, caller, metrics):
        caller, caller_name = caller
        curr_time = int(time.time() * 1000)
        data = caller.metrics_create_custom(MetricsLevel.INFO, "some_metric", retention=10000)
        assert data == "some_metric"
        pipeline = caller.metrics_get_pipeline()
        assert pipeline != None
        data = caller.metrics_add("some_metric", 42, timestamp=1234, pipeline=pipeline)
        assert data == None
        data = caller.metrics_add("some_metric", 2020, timestamp=1234, pipeline=pipeline)
        assert data == None

        data = metrics.get("some_metric")
        assert data == None

        data = caller.metrics_write_pipeline(pipeline)
        assert data != None

        # make a metric and have the timestamp auto-created
        data = metrics.range("some_metric", 0, -1)

        # There's a super-slim chance this makes it through if the
        #   calls are on a millisecond boundary
        assert len(data) == 1 or (len(data) == 2)

        # Make sure the first piece is there
        assert data[0][1] == 42

    def test_metrics_async_timestamp_no_jitter(self, caller, metrics):
        caller, caller_name = caller
        data = caller.metrics_create_custom(MetricsLevel.INFO, "some_metric", retention=10000)
        assert data == "some_metric"
        pipeline = caller.metrics_get_pipeline()
        assert pipeline != None
        data = caller.metrics_add("some_metric", 42, pipeline=pipeline)
        assert data == None
        add_time = time.time()

        data = metrics.get("some_metric")
        assert data == None

        time.sleep(2.0)
        flush_time = time.time()

        data = caller.metrics_write_pipeline(pipeline)
        assert data != None

        data = metrics.get("some_metric")
        assert data[1] == 42

        # Make sure the timestamp gets set at the flush and
        #   not the add
        assert (int(1000 * add_time) - data[0]) <= 1000
        assert (int(1000 * flush_time) - data[0]) >= 2000

    def test_metrics_remote(self, caller, metrics):
        my_elem = Element('test_metrics_no_redis', metrics_host="127.0.0.1", metrics_port=6380)
        assert my_elem != None

        data = my_elem.metrics_create_custom(MetricsLevel.INFO, "some_metric", retention=10000)
        assert data == "some_metric"

        my_elem._clean_up()

    def test_metrics_remote_nonexist(self, caller, metrics):
        my_elem = Element('test_metrics_no_redis', metrics_host="127.0.0.1", metrics_port=6381)
        assert my_elem != None

        data = my_elem.metrics_create_custom(MetricsLevel.INFO, "some_metric", retention=10000)
        assert data == None

        my_elem._clean_up()

    def test_metrics_remote_nonexist_enforced(self, caller, metrics):
        enforced = False

        try:
            my_elem = Element('test_metrics_no_redis', metrics_host="127.0.0.1", metrics_port=6381, enforce_metrics=True)
        except AtomError as e:
            print(e)
            enforced = True

        assert enforced == True

    def test_metrics_socket_nonexist(self, caller, metrics):
        my_elem = Element('test_metrics_no_redis', metrics_socket_path="/shared/nonexistent.sock")
        assert my_elem != None

        data = my_elem.metrics_create_custom(MetricsLevel.INFO, "some_metric", retention=10000)
        assert data == None

        my_elem._clean_up()

    def test_metrics_socket_nonexist_enforced(self, caller, metrics):
        enforced = False

        try:
            my_elem = Element('test_metrics_no_redis', metrics_socket_path="/shared/nonexistent.sock", enforce_metrics=True)
        except AtomError as e:
            print(e)
            enforced = True

        assert enforced == True

    def test_metrics_turned_off(self, caller, metrics):
        os.environ["ATOM_USE_METRICS"] = "FALSE"
        my_elem = Element('test_metrics_turned_off')
        assert my_elem != None

        pipeline = my_elem.metrics_get_pipeline()
        assert pipeline == None
        data = my_elem.metrics_create_custom(MetricsLevel.INFO, "some_metric", retention=10000)
        assert data == None
        data = my_elem.metrics_add("some_metric", 42)
        assert data == None
        data = my_elem.metrics_write_pipeline(pipeline)
        assert data == None

        my_elem._clean_up()

def add_1(x):
    return Response(int(x)+1)

def sleep_ms(x):
    time.sleep(x / 1000.0)

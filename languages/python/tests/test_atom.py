import pytest
import time
import gc
from atom import Element
from multiprocessing import Process
from threading import Thread, Lock
from atom.config import ATOM_NO_ERROR, ATOM_COMMAND_NO_ACK, ATOM_COMMAND_UNSUPPORTED
from atom.config import ATOM_COMMAND_NO_RESPONSE, ATOM_CALLBACK_FAILED
from atom.config import ATOM_USER_ERRORS_BEGIN, HEALTHCHECK_RETRY_INTERVAL
from atom.config import HEALTHCHECK_COMMAND, VERSION_COMMAND, LANG, VERSION, COMMAND_LIST_COMMAND
from atom.messages import Response, StreamHandler, LogLevel
from atom.contracts import RawContract, EmptyContract, BinaryProperty


class TestAtom:

    @pytest.fixture
    def caller(self):
        """
        Sets up the caller before each test function is run.
        Tears down the caller after each test is run.
        """
        caller = Element("test_caller")
        yield caller
        del caller
        gc.collect()


    @pytest.fixture
    def responder(self):
        """
        Sets up the responder before each test function is run.
        Tears down the responder after each test is run.
        """
        responder = Element("test_responder")
        yield responder
        del responder
        gc.collect()

    def test_caller_responder_exist(self, caller, responder):
        """
        Ensures that the caller and responder were created with the proper names.
        """
        print(caller.get_all_elements())
        assert "test_responder" in caller.get_all_elements()
        assert "test_caller" in responder.get_all_elements()

    def test_id_generation(self, caller):
        """
        Ensures id generation functions are working with expected input.
        """
        assert caller._make_response_id("abc") == "response:abc"
        assert caller._make_command_id("abc") == "command:abc"
        assert caller._make_stream_id("abc", "123") == "stream:abc:123"

    def test_command_in_redis(self, caller):
        """
        Tests caller sending command and verifies that command was sent properly in Redis.
        """
        proc = Process(target=caller.command_send, args=("test_responder", "test_cmd", 0,))
        proc.start()
        data = caller._rclient.xread(block=10, **{caller._make_command_id("test_responder"): "$"})
        proc.join()

        assert "command:test_responder" in data
        data = data["command:test_responder"][0][1]
        assert data[b"element"] == b"test_caller"
        assert data[b"cmd"] == b"test_cmd"
        assert data[b"data"] == b"0"

    def test_add_entry_and_get_n_most_recent(self, caller, responder):
        """
        Adds 10 entries to the responder's stream and makes sure that the
        proper values are returned from get_n_most_recent.
        """
        for i in range(10):
            responder.entry_write("test_stream", {"data": i})
        entries = caller.entry_read_n("test_responder", "test_stream", 5)
        assert len(entries) == 5
        assert entries[0]["data"] == b"9"
        assert entries[-1]["data"] == b"5"

    def test_add_entry_and_get_n_most_recent_serialized(self, caller, responder):
        """
        Adds 10 entries to the responder's stream and makes sure that the
        proper values are returned from get_n_most_recent.
        """
        for i in range(10):
            responder.entry_write("test_stream_serialized", {"data": i}, serialize=True)
        entries = caller.entry_read_n("test_responder", "test_stream_serialized", 5, deserialize=True)
        assert len(entries) == 5
        assert entries[0]["data"] == 9
        assert entries[-1]["data"] == 5

    def test_add_command(self, responder):
        """
        Ensures that a command can be added to a responder.
        """
        responder.command_add("test_command", lambda x: x, timeout=123)
        assert "test_command" in responder.handler_map
        assert responder.timeouts["test_command"] == 123

    def test_clean_up_stream(self, responder):
        """
        Ensures that a stream can be removed from Redis and removed from responder's streams set.
        """
        responder.entry_write("clean_me", {"data": 0})
        assert "stream:test_responder:clean_me" in responder.get_all_streams()
        responder.clean_up_stream("clean_me")
        assert "stream:test_responder:clean_me" not in responder.get_all_streams()
        assert "clean_me" not in responder.streams

    def test_clean_up(self, responder):
        """
        Ensures that a responder can be removed from Redis
        """
        new_responder = Element("new_responder")
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
        responder.command_add("add_1", add_1)
        proc = Process(target=responder.command_loop)
        proc.start()
        response = caller.command_send("test_responder", "add_1", 0)
        proc.terminate()
        proc.join()
        assert response["err_code"] == ATOM_NO_ERROR
        assert response["data"] == b"1"

    def test_command_response_serialized(self, caller, responder):
        """
        Element sends command and responder returns response.
        Tests expected use case of command response.
        """
        def add_1_serialized(data):
            return Response(data+1, serialize=True)

        responder.command_add("add_1", add_1_serialized, deserialize=True)
        proc = Process(target=responder.command_loop)
        proc.start()
        response = caller.command_send("test_responder", "add_1", 0, serialize=True, deserialize=True)
        proc.terminate()
        proc.join()
        assert response["err_code"] == ATOM_NO_ERROR
        assert response["data"] == 1

    def test_listen_on_streams(self, caller):
        """
        Creates two responders publishing entries on their respective streams with
        a caller listening on those streams and publishing data to a new stream.
        This test ensures that the new stream contains all the data from the responders.
        """
        responder_0 = Element("responder_0")
        responder_1 = Element("responder_1")
        entries = set()

        def entry_write_loop(responder, stream_name, data):
            # Wait until both responders and the caller are ready
            while -1 not in entries or -2 not in entries:
                responder.entry_write(stream_name, {"value": data-2}, serialize=True)
            for i in range(10):
                responder.entry_write(stream_name, {"value": data}, serialize=True)
                data += 2

        def add_entries(data):
            entries.add(data["value"])

        proc_responder_0 = Thread(target=entry_write_loop, args=(responder_0, "stream_0", 0,))
        proc_responder_1 = Thread(target=entry_write_loop, args=(responder_1, "stream_1", 1,))

        stream_handlers = [
            StreamHandler("responder_0", "stream_0", add_entries),
            StreamHandler("responder_1", "stream_1", add_entries),
        ]
        thread_caller = Thread(target=caller.entry_read_loop, args=(stream_handlers, None, 1000, True,), daemon=True)
        thread_caller.start()
        proc_responder_0.start()
        proc_responder_1.start()
        proc_responder_0.join()
        proc_responder_1.join()
        # Wait to give the caller time to handle all the data from the streams
        thread_caller.join(0.5)
        caller._rclient.delete("stream:responder_0:stream_0")
        caller._rclient.delete("stream:responder_1:stream_1")
        for i in range(20):
            assert i in entries

    def test_read_since(self, caller, responder):
        """
        Sets the current timestamp as last_id and writes 5 entries to a stream.
        Ensures that we can get 5 entries since the last id using entry_read_since.
        """
        responder.entry_write("test_stream", {"data": None})

        # Sleep so that last_id is later than the first entry
        time.sleep(0.01)
        last_id = responder._get_redis_timestamp()

        # Sleep so that the entries are later than last_id
        time.sleep(0.01)

        for i in range(5):
            responder.entry_write("test_stream", {"data": i})

        # Ensure this gets all entries
        entries = caller.entry_read_since("test_responder", "test_stream")
        assert(len(entries) == 6)

        # Ensure we get the correct number of entries since the last_id
        entries = caller.entry_read_since("test_responder", "test_stream", last_id)
        assert(len(entries) == 5)

        # Ensure that if we pass n, we get the n earliest entries since last_id
        entries = caller.entry_read_since("test_responder", "test_stream", last_id, 2)
        assert(len(entries) == 2)
        assert entries[-1]["data"] == b"1"

    def test_parallel_read_write(self, caller, responder):
        """
        Has the same responder class receiving commands on 1 thread,
        while publishing to a stream on a 2nd thread at high volume.
        Meanwhile, a caller quickly sends a series of commands to the responder and verifies
        we get valid results back.
        Ensures that we can safely send and receive using the same element class without concurrency issues.
        """
        responder_0 = Element("responder_0")
        # NO_OP command responds with whatever data it receives
        def no_op_serialized(data):
            return Response(data, serialize=True)
        responder_0.command_add("no_op", no_op_serialized, deserialize=True)

        # Entry write loop mimics high volume publisher
        def entry_write_loop(responder):
            for i in range(3000):
                responder.entry_write("stream_0", {"value": 0}, serialize=True)
                time.sleep(0.0001)

        # Command loop thread to handle incoming commands
        command_loop_thread = Thread(target=responder_0.command_loop, daemon=True)
        # Entry write thread to publish a whole bunch to a stream
        entry_write_thread = Thread(target=entry_write_loop, args=(responder_0,), daemon=True)
        command_loop_thread.start()
        entry_write_thread.start()

        # Send a bunch of commands to responder and you should get valid responses back,
        # even while its busy publishing to a stream
        try:
            for i in range(20):
                response = caller.command_send("responder_0", "no_op", 1, serialize=True, deserialize=True)
                assert response["err_code"] == ATOM_NO_ERROR
                assert response["data"] == 1
        finally:
            # Cleanup threads
            entry_write_thread.join()
            responder.command_loop_shutdown()
            command_loop_thread.join(0.5)
            responder_0._rclient.delete("stream:responder_0:stream_0")
            responder_0._rclient.delete("command:responder_0")
            responder_0._rclient.delete("response:responder_0")

    def test_healthcheck_default(self, caller, responder):
        """
        Verify default healthcheck
        """
        proc = Process(target=responder.command_loop)
        proc.start()
        response = caller.command_send("test_responder", HEALTHCHECK_COMMAND)
        assert response["err_code"] == ATOM_NO_ERROR
        assert response["data"] == b""
        proc.terminate()
        proc.join()

    def test_healthcheck_success(self, caller, responder):
        """
        Verify a successful response from a custom healthcheck
        """
        responder.healthcheck_set(lambda: Response(err_code=0, err_str="We're good"))
        proc = Process(target=responder.command_loop)
        proc.start()
        response = caller.command_send("test_responder", HEALTHCHECK_COMMAND)
        assert response["err_code"] == ATOM_NO_ERROR
        assert response["data"] == b""
        assert response["err_str"] == "We're good"
        proc.terminate()
        proc.join()

    def test_healthcheck_failure(self, caller, responder):
        """
        Verify a failed response from a custom healthcheck
        """
        responder.healthcheck_set(lambda: Response(err_code=5, err_str="Camera is unplugged"))
        proc = Process(target=responder.command_loop)
        proc.start()
        response = caller.command_send("test_responder", HEALTHCHECK_COMMAND)
        assert response["err_code"] == 5 + ATOM_USER_ERRORS_BEGIN
        assert response["data"] == b""
        assert response["err_str"] == "Camera is unplugged"
        proc.terminate()
        proc.join()

    def test_wait_for_elements_healthy(self, caller, responder):
        """
        Verify wait_for_elements_healthy success/failure cases
        """
        proc = Process(target=responder.command_loop)
        proc.start()

        def wait_for_elements_check(caller, elements_to_check):
            caller.wait_for_elements_healthy(elements_to_check)

        wait_for_elements_thread = Thread(target=wait_for_elements_check, args=(caller, ['test_responder']), daemon=True)
        wait_for_elements_thread.start()
        # If elements reported healthy, call should have returned quickly and thread should exit
        wait_for_elements_thread.join(0.5)
        assert not wait_for_elements_thread.is_alive()

        wait_for_elements_thread = Thread(target=wait_for_elements_check, args=(caller, ['test_responder', 'test_responder_2']), daemon=True)
        wait_for_elements_thread.start()
        # 1 of these elements is missing, so thread is busy and this join call should timeout retrying
        wait_for_elements_thread.join(0.5)
        assert wait_for_elements_thread.is_alive()

        try:
            responder_2 = Element("test_responder_2")
            command_loop_thread = Thread(target=responder_2.command_loop, daemon=True)
            command_loop_thread.start()

            # test_responder_2 is alive now, so both healthchecks should succeed and thread should exit roughly within the retry interval
            wait_for_elements_thread.join(HEALTHCHECK_RETRY_INTERVAL + 1.0)
            assert not wait_for_elements_thread.is_alive()
        finally:
            # Cleanup threads
            responder_2.command_loop_shutdown()
            command_loop_thread.join(0.5)
            responder._rclient.delete("command:test_responder_2")
            responder._rclient.delete("response:test_responder_2")

        proc.terminate()
        proc.join()

    def test_version_command(self, caller, responder):
        """
        Verify the response from the get_element_version command
        """
        proc = Process(target=responder.command_loop)
        proc.start()
        response = caller.command_send("test_responder", VERSION_COMMAND, deserialize=True)
        assert response["err_code"] == ATOM_NO_ERROR
        assert response["data"] == {"version": float(".".join(VERSION.split(".")[:-1])), "language": LANG}
        response2 = caller.get_element_version("test_responder")
        assert response == response2
        proc.terminate()
        proc.join()

    def test_command_list_command(self, caller, responder):
        """
        Verify the response from the COMMAND_LIST_COMMAND command
        """
        # Test with no commands
        no_command_responder = Element('no_command_responder')
        command_loop_process = Process(target=no_command_responder.command_loop)
        command_loop_process.start()
        assert caller.command_send(no_command_responder.name, COMMAND_LIST_COMMAND, deserialize=True)["data"] == []
        command_loop_process.terminate()
        command_loop_process.join()
        del no_command_responder

        # Add commands to responder
        responder.command_add('foo_func1', lambda data: data)
        responder.command_add('foo_func2', lambda: None, timeout=500, deserialize=True)
        responder.command_add('foo_func3', lambda x, y: x + y, timeout=1, deserialize=True)
        command_loop_process = Process(target=responder.command_loop)
        command_loop_process.start()

        # Test with three commands
        response = caller.command_send(responder.name, COMMAND_LIST_COMMAND, deserialize=True)
        assert response["err_code"] == ATOM_NO_ERROR
        assert response["data"] == ['foo_func1', 'foo_func2', 'foo_func3']

        command_loop_process.terminate()
        command_loop_process.join()

    def test_get_all_commands_with_version(self, caller, responder):
        """
        Ensure get_all_commands only queries support elements.
        """
        # Change responder reported version
        responder.handler_map[VERSION_COMMAND]['handler'] = \
            lambda: Response(data={'language': 'Python', 'version': 0.2}, serialize=True)
        # Create element with normal, supported version
        responder2 = Element('responder2')

        # Add commands to both responders and start command loop
        responder.command_add('foo_func0', lambda data: data)
        responder2.command_add('foo_func0', lambda: None, timeout=500, deserialize=True)
        responder2.command_add('foo_func1', lambda x, y: x + y, timeout=1, deserialize=True)
        cl_process_1 = Process(target=responder.command_loop)
        cl_process_2 = Process(target=responder2.command_loop)
        cl_process_1.start()
        cl_process_2.start()

        # Retrieve commands
        commands = caller.get_all_commands()
        # Do not include responder's commands as the version is too low
        desired_commands = ['responder2:foo_func0', 'responder2:foo_func1']
        assert commands == desired_commands

        cl_process_1.terminate()
        cl_process_2.terminate()
        cl_process_1.join()
        cl_process_2.join()
        del responder2

    def test_get_all_commands(self, caller, responder):
        """
        Verify the response from the get_all_commands command
        """
        # Test with no available commands
        assert caller.get_all_commands() == []

        # Set up two responders
        test_name_1, test_name_2 = 'responder1', 'responder2'
        responder1, responder2 = Element(test_name_1), Element(test_name_2)

        proc1_function_data = [('foo_func0', lambda x: x + 3),
                               ('foo_func1', lambda: None, 10, True),
                               ('foo_func2', lambda x: None)]
        proc2_function_data = [('foo_func0', lambda y: y * 3, 10),
                               ('other_foo0', lambda y: None, 3, True),
                               ('other_foo1', lambda: 5)]

        # Add functions
        for data in proc1_function_data:
            responder1.command_add(*data)
        for data in proc2_function_data:
            responder2.command_add(*data)

        command_loop_1 = Process(target=responder1.command_loop)
        command_loop_2 = Process(target=responder2.command_loop)
        command_loop_1.start()
        command_loop_2.start()

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

        # Cleanup
        command_loop_1.terminate()
        command_loop_2.terminate()
        command_loop_1.join()
        command_loop_2.join()
        del responder1, responder2

    def test_no_ack(self, caller, responder):
        """
        Element sends command and responder does not acknowledge.
        """
        responder.command_add("add_1", add_1)
        response = caller.command_send("test_responder", "add_1", 0)
        assert response["err_code"] == ATOM_COMMAND_NO_ACK

    def test_unsupported_command(self, caller, responder):
        """
        Element sends command that responder does not have.
        """
        proc = Process(target=responder.command_loop)
        proc.start()
        response = caller.command_send("test_responder", "add_1", 0)
        proc.terminate()
        proc.join()
        assert response["err_code"] == ATOM_COMMAND_UNSUPPORTED

    def test_command_timeout(self, caller, responder):
        """
        Element sends command to responder that does not return data within the timeout.
        """
        # Set a timeout of 10 ms
        responder.command_add("loop", loop, 10)
        proc = Process(target=responder.command_loop)
        proc.start()
        response = caller.command_send("test_responder", "loop", None)
        proc.terminate()
        proc.join()
        assert response["err_code"] == ATOM_COMMAND_NO_RESPONSE

    def test_handler_returns_not_response(self, caller, responder):
        """
        Element calls command from responder that does not return an object of type Response.
        """
        responder.command_add("ret_not_response", lambda x: 0)
        proc = Process(target=responder.command_loop)
        proc.start()
        response = caller.command_send("test_responder", "ret_not_response", None)
        proc.terminate()
        proc.join()
        assert response["err_code"] == ATOM_CALLBACK_FAILED

    def test_log(self, caller):
        """
        Writes a log with each severity level and ensures that all the logs exist.
        """
        for i, severity in enumerate(LogLevel):
            caller.log(severity, f"severity {i}", stdout=False)
        logs = caller._rclient.xread(
            **{"log": 0})["log"]
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



def add_1(x):
    return Response(int(x)+1)

def loop(x):
    while True:
        time.sleep(0.1)

import pytest
import time
from atom import Element
from multiprocessing import Process
from atom.config import ATOM_NO_ERROR, ATOM_COMMAND_NO_ACK, ATOM_COMMAND_UNSUPPORTED
from atom.config import ATOM_COMMAND_NO_RESPONSE, ATOM_CALLBACK_FAILED
from atom.messages import Response, StreamHandler


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

    @pytest.fixture
    def responder(self):
        """
        Sets up the responder before each test function is run.
        Tears down the responder after each test is run.
        """
        responder = Element("test_responder")
        yield responder
        del responder

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

    def test_listen_on_streams(self, caller):
        """
        Creates two responders publishing entries on their respective streams with
        a caller listening on those streams and publishing data to a new stream.
        This test ensures that the new stream contains all the data from the responders.
        """
        test_stream_id = caller._make_stream_id("test_stream", "test_stream")
        responder_0 = Element("responder_0")
        responder_1 = Element("responder_1")

        def entry_write_loop(responder, stream_name, data):
            for i in range(10):
                responder.entry_write(stream_name, {"data": data})
                data += 2

        def add_to_redis(data):
            data = {"data": data[b"data"], "timestamp": data[b"timestamp"]}
            caller._pipe.xadd(test_stream_id, maxlen=50, **data)
            caller._pipe.execute()

        proc_responder_0 = Process(target=entry_write_loop, args=(responder_0, "stream_0", 0,))
        proc_responder_1 = Process(target=entry_write_loop, args=(responder_1, "stream_1", 1,))

        stream_handlers = [
            StreamHandler("responder_0", "stream_0", add_to_redis),
            StreamHandler("responder_1", "stream_1", add_to_redis),
        ]
        proc_caller = Process(target=caller.entry_read_loop, args=(stream_handlers,))
        proc_caller.start()
        # Sleep so the caller can start listening to the streams before data is published
        time.sleep(0.5)
        proc_responder_0.start()
        proc_responder_1.start()
        proc_responder_0.join()
        proc_responder_1.join()
        # Sleep to give the caller time to handle all the data from the streams
        time.sleep(0.5)
        proc_caller.terminate()
        proc_caller.join()
        entries = caller.entry_read_n("test_stream", "test_stream", 50)
        caller._rclient.delete("stream:responder_0:stream_0")
        caller._rclient.delete("stream:responder_1:stream_1")
        caller._rclient.delete(test_stream_id)
        assert len(entries) == 20

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


def add_1(x):
    return Response(int(x)+1)

def loop(x):
    while True:
        time.sleep(0.1)

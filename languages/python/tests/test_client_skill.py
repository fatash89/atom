import pytest
import time
from skills.client import Client
from multiprocessing import Process
from skills.skill import Skill
from skills.messages import Response, StreamHandler


class TestClientSkill:

    @pytest.fixture
    def client(self):
        """
        Sets up the client before each test function is run.
        Tears down the client after each test is run.
        """
        client = Client("test_client")
        yield client
        del client

    @pytest.fixture
    def skill(self):
        """
        Sets up the skill before each test function is run.
        Tears down the skill after each test is run.
        """
        skill = Skill("test_skill")
        yield skill
        del skill

    def test_client_skill_exist(self, client, skill):
        """
        Ensures that the client and skill were created with the proper names.
        """
        assert b"skill:test_skill" in client.get_all_skills()
        assert b"client:test_client" in skill.get_all_clients()

    def test_id_generation(self, client):
        """
        Ensures id generation functions are working with expected input.
        """
        assert client._make_client_id("abc") == "client:abc"
        assert client._make_skill_id("abc") == "skill:abc"
        assert client._make_stream_id("abc", "123") == "stream:abc:123"

    def test_command_in_redis(self, client):
        """
        Tests client sending command and verifies that command was sent properly in Redis.
        """
        proc = Process(target=client.send_command, args=("test_skill", "test_cmd", 0,))
        proc.start()
        data = client._rclient.xread(block=10, **{client._make_skill_id("test_skill"): "$"})
        proc.join()

        assert "skill:test_skill" in data
        data = data["skill:test_skill"][0][1]
        assert data[b"client"] == b"test_client"
        assert data[b"cmd"] == b"test_cmd"
        assert data[b"data"] == b"0"

    def test_add_droplet_and_get_n_most_recent(self, client, skill):
        """
        Adds 10 droplets to the skill's stream and makes sure that the 
        proper values are returned from get_n_most_recent.
        """
        for i in range(10):
            skill.add_droplet("test_stream", i)
        data = client.get_n_most_recent("test_skill", "test_stream", 5)
        assert len(data) == 5
        assert data[0]["data"] == b"9"
        assert data[-1]["data"] == b"5"

    def test_add_command(self, skill):
        """
        Ensures that a command can be added to a skill.
        """
        skill.add_command("test_command", lambda x: x, timeout=123)
        assert "test_command" in skill.handler_map
        assert skill.timeouts["test_command"] == 123

    def test_clean_up_stream(self, skill):
        """
        Ensures that a stream can be removed from Redis and removed from skill's streams set.
        """
        skill.add_droplet("clean_me", 0)
        assert b"stream:test_skill:clean_me" in skill.get_all_streams()
        skill.clean_up_stream("clean_me")
        assert b"stream:test_skill:clean_me" not in skill.get_all_streams()
        assert "clean_me" not in skill.streams

    def test_clean_up(self, skill):
        """
        Ensures that a skill can be removed from Redis
        """
        new_skill = Skill("new_skill")
        assert b"skill:new_skill" in skill.get_all_skills()
        del new_skill
        assert b"skill:new_skill" not in skill.get_all_skills()

    def test_command_response(self, client, skill):
        """
        Client sends command and skill returns response.
        Tests expected use case of command response.
        """
        skill.add_command("add_1", lambda x: Response(int(x)+1))
        proc = Process(target=skill.run_command_loop)
        proc.start()
        response = client.send_command("test_skill", "add_1", 0)
        proc.terminate()
        proc.join()
        assert response["err_code"] == 0
        assert response["data"] == b"1"

    def test_listen_on_streams(self, client):
        """
        Creates two skills publishing data on their respective streams with
        a client listening on those streams and publishing data to a new stream.
        This test ensures that the new stream contains all the data from the skills.
        """
        test_stream_id = client._make_stream_id("test_stream", "test_stream")
        skill_0 = Skill("skill_0")
        skill_1 = Skill("skill_1")

        def add_droplet_loop(skill, stream_name, data):
            for i in range(10):
                skill.add_droplet(stream_name, data)
                data += 2

        def add_to_redis(data):
            data = {"data": data[b"data"], "timestamp": data[b"timestamp"]}
            client._pipe.xadd(test_stream_id, maxlen=50, **data)
            client._pipe.execute()

        proc_skill_0 = Process(target=add_droplet_loop, args=(skill_0, "stream_0", 0,))
        proc_skill_1 = Process(target=add_droplet_loop, args=(skill_1, "stream_1", 1,))

        stream_handlers = [
            StreamHandler("skill_0", "stream_0", add_to_redis),
            StreamHandler("skill_1", "stream_1", add_to_redis),
        ]
        proc_client = Process(target=client.listen_on_streams, args=(stream_handlers,))
        proc_client.start()
        # Sleep so the client can start listening to the streams before data is published
        time.sleep(0.5)
        proc_skill_0.start()
        proc_skill_1.start()
        proc_skill_0.join()
        proc_skill_1.join()
        # Sleep to give the client time to handle all the data from the streams
        time.sleep(0.5)
        proc_client.terminate()
        proc_client.join()
        droplets = client.get_n_most_recent("test_stream", "test_stream", 50)
        client._rclient.delete("stream:skill_0:stream_0")
        client._rclient.delete("stream:skill_1:stream_1")
        client._rclient.delete(test_stream_id)
        assert len(droplets) == 20

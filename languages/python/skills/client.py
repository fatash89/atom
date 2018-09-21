import redis
import sys
import time
from skills.config import LANG, VERSION, ACK_TIMEOUT, STREAM_LEN, SLEEP_TIME
from collections import namedtuple
from skills.messages import Cmd, Response


class Client:
    def __init__(self, name, host="localhost", port=6379, db=0, socket_path="/tmp/redis.sock"):
        self.name = name
        self._rclient = redis.StrictRedis(host=host, port=port, db=db, unix_socket_path=socket_path)
        self._pipe = self._rclient.pipeline()

        self._pipe.xadd(self._make_client_id(self.name), maxlen=STREAM_LEN, **{"language": LANG, "version": VERSION})
        # Keep track of response_last_id to know last time the client's response stream was read from
        self.response_last_id = self._pipe.execute()[-1].decode()

    def __repr__(self):
        return f"{self.__class__.__name__}({self.name})"

    def __del__(self):
        """
        Removes all clients and skills with the same name.
        """
        self._rclient.delete(self._make_client_id(self.name))
        self._rclient.delete(self._make_skill_id(self.name))

    def _make_client_id(self, client_name):
        return f"client:{client_name}"

    def _make_skill_id(self, skill_name):
        return f"skill:{skill_name}"

    def _make_stream_id(self, skill_name, stream_name):
        return f"stream:{skill_name}:{stream_name}"

    def _get_redis_timestamp(self):
        secs, msecs = self._rclient.time()
        timestamp = str(secs) + str(msecs)[:3]
        return timestamp

    def get_all_clients(self):
        clients = self._rclient.keys(self._make_client_id("*"))
        return clients

    def get_all_skills(self):
        skills = self._rclient.keys(self._make_skill_id("*"))
        return skills

    def get_all_streams(self, skill_name="*"):
        streams = self._rclient.keys(self._make_stream_id(skill_name, "*"))
        return streams

    def send_command(self, skill_name, cmd_name, data, block=True):
        """
        Sends command to skill and waits for acknowledge.
        When acknowledge is received, waits for time from acknowledge or until response is received.
        Returns response with unnecessary data stripped away.
        """
        # Send command to skill's command stream
        cmd = Cmd(self.name, cmd_name, data)
        self._pipe.xadd(self._make_skill_id(skill_name), maxlen=STREAM_LEN, **vars(cmd))
        cmd_id = self._pipe.execute()[-1].decode()
        timeout = None

        # Receive acknowledge from skill
        responses = self._rclient.xread(block=ACK_TIMEOUT, **{self._make_client_id(self.name): self.response_last_id})
        if responses is None:
            return vars(Response(err_code=2, err_str="Did not receive acknowledge from skill."))
        for self.response_last_id, response in responses[self._make_client_id(self.name)]:
            if response[b"skill"].decode() == skill_name and \
            response[b"cmd_id"].decode() == cmd_id and b"timeout" in response:
                timeout = int(response[b"timeout"].decode())
                break

        if timeout is None:
            return vars(Response(err_code=2, err_str="Did not receive acknowledge from skill."))

        # Receive response from skill
        responses = self._rclient.xread(block=timeout, **{self._make_client_id(self.name): self.response_last_id})
        if responses is None:
            return vars(Response(err_code=3, err_str="Did not receive response from skill."))
        for self.response_last_id, response in responses[self._make_client_id(self.name)]:
            if response[b"skill"].decode() == skill_name and \
            response[b"cmd_id"].decode() == cmd_id and b"data" in response:
                err_code = int(response[b"err_code"].decode())
                err_str = response[b"err_str"].decode()
                return vars(Response(data=response[b"data"], err_code=err_code, err_str=err_str))

        # Proper response was not in responses
        return vars(Response(err_code=3, err_str="Did not receive response from skill."))

    def listen_on_streams(self, stream_handlers):
        """
        Listen to streams from stream handler map and pass any received data to corresponding handler.
        
        Args:
            stream_handlers: List of messages.stream_handler
        """
        streams = {}
        stream_handler_map = {}
        for stream_handler in stream_handlers:
            stream_id = self._make_stream_id(stream_handler.skill, stream_handler.stream)
            streams[stream_id] = self._get_redis_timestamp()
            stream_handler_map[stream_id] = stream_handler.handler
        while True:
            stream_droplets = self._rclient.xread(block=sys.maxsize, **streams)
            if stream_droplets is None:
                time.sleep(SLEEP_TIME)
                continue
            for stream, droplets in stream_droplets.items():
                for uid, droplet in droplets:
                    streams[stream] = uid
                    stream_handler_map[stream](droplet)

    def get_n_most_recent(self, skill, stream, n):
        uid_droplets = self._rclient.xrevrange(self._make_stream_id(skill, stream), count=n)
        droplets = []
        # Convert the bytestring fields of the droplet to string
        for _, droplet in uid_droplets:
            droplets.append({
                "timestamp": droplet[b"timestamp"].decode(),
                "data": droplet[b"data"],
            })
        return droplets

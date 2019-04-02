# atombot.py
from atom import Element
from atom.messages import Response
from threading import Thread
import pdb
import time

PUBLISH_FREQUENCY = 100
TIME_FOR_WAVEFORM = 5

if __name__ == "__main__":

    element = Element("voice_wave")

    data = {
        "name": "example",
        "t": TIME_FOR_WAVEFORM,
        "perm": False,
        "e": "waveform",
        "s": "serialized"
    }
    res = element.command_send("record", "start", data, serialize=True)
    time.sleep(TIME_FOR_WAVEFORM + 2)

    sinx_strings = ["sinex", "sinx"]
    cosx_strings = ["cosx"]
    tanx_strings = ["tanx", "10x", "tonics"]

    while True:
        print("listening..")
        last_id = element._get_redis_timestamp()

        while True:
            entries = element.entry_read_since(
                "voice", "string", last_id=last_id, block=1000)
            if entries:
                last_id = entries[0]["id"]
                #voice_string = entries[0]["data"].decode().strip().lower().replace("-", "").split(" ")
                voice_string = entries[0]["data"].decode()

                if any(x in voice_string for x in sinx_strings):

                    print("Plotting sinx")
                    data = {
                        "name": "example",
                        "msgpack": True,
                        "plots": [{
                            "data": [["x", ["sin"], "value"]]
                        }]
                    }
                    res = element.command_send(
                        "record", "plot", data, serialize=True)

                if any(x in voice_string for x in cosx_strings):

                    print("Plotting cosx")
                    data = {
                        "name": "example",
                        "msgpack": True,
                        "plots": [{
                            "data": [["x", ["cos"], "value"]]
                        }]
                    }

                    res = element.command_send(
                        "record", "plot", data, serialize=True)

                if any(x in voice_string for x in tanx_strings):
                    print("Plotting tanx")
                    data = {
                        "name": "example",
                        "msgpack": True,
                        "plots": [{
                            "data": [["x", ["tan"], "value"]]
                        }]
                    }
                    res = element.command_send(
                        "record", "plot", data, serialize=True)

                time.sleep(1 / PUBLISH_FREQUENCY)

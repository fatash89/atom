# atombot.py
from atom import Element
from atom.messages import Response
from threading import Thread
import pdb
import time

PUBLISH_FREQUENCY = 100
TIME_FOR_WAVEFORM = 5

if __name__ == "__main__":

    element = Element("voice_demo")

    # Wait for the record element to start up and launch the VNC.
    #   this can and should be fixed with a heartbeat!
    time.sleep(10)

    # Start the recording and wait for 5s
    data = {
        "name": "example",
        "t": TIME_FOR_WAVEFORM,
        "perm": False,
        "e": "waveform",
        "s": "serialized"
    }
    res = element.command_send("record", "start", data, serialize=True)
    time.sleep(TIME_FOR_WAVEFORM + 2)

    # Strings we'll recognize for the plotting commands. This is pretty
    #   rudimentary and can be improved with some better parsing/processing/NLP
    sinx_strings = ["show sin", "show sign", "show sine"]
    cosx_strings = ["show cos", "show cosine", "show coast", "show coats", "show cosign"]
    tanx_strings = ["show tan", "showtime"]

    print("listening..")
    last_id = element._get_redis_timestamp()

    while True:
        entries = element.entry_read_since(
            "voice", "string", last_id=last_id, block=1000)
        if entries:
            last_id = entries[0]["id"]
            #voice_string = entries[0]["data"].decode().strip().lower().replace("-", "").split(" ")
            voice_string = entries[0]["data"].decode().lower()
            print("Got voice string {}".format(voice_string))

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

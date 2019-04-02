# atombot.py
from atom import Element
from atom.messages import Response
from threading import Thread
import pdb
import time

if __name__ == "__main__":

    element = Element("voice_wave")
    ## Write entries to the same stream to clear
    voice_element = Element("voice")
    voice_element.entry_write("string", {"data" : "clear"})
    
    ## Start recording.
    data = {"name":"example", "t":5, "perm":False, "e":"waveform", "s":"serialized"}
    res = element.command_send("record", "start", data, serialize=True)
    time.sleep(7)
    
    sinx_strings = ["sinex","sinx"]
    cosx_strings = ["cosx"]
    tanx_strings = ["tanx","10x","tonics"]

    while True:
        ### get voice_string
        print("listening..")
        entry = element.entry_read_n("voice", "string", 1)
        voice_string = entry[0]['data'].decode()

        if any(x in voice_string for x in sinx_strings):
            print("Plotting sinx")
            data  = { "name":"example", "msgpack":True, "plots":[ { "data": [[ "x", ["sin"], "value" ]] } ] }
            res = element.command_send("record", "plot", data, serialize=True)
            voice_element.entry_write("string", {"data" : "clear"})

        if any(x in voice_string for x in cosx_strings):
            print("Plotting cosx")
            data  = { "name":"example", "msgpack":True, "plots":[ { "data": [[ "x", ["cos"], "value" ]] } ] }
            res = element.command_send("record", "plot", data, serialize=True)
            voice_element.entry_write("string", {"data" : "clear"})
        
        if any(x in voice_string for x in tanx_strings):
            print("Plotting tanx")
            data  = { "name":"example", "msgpack":True, "plots":[ { "data": [[ "x", ["tan"], "value" ]] } ] }
            res = element.command_send("record", "plot", data, serialize=True)
            voice_element.entry_write("string", {"data" : "clear"})

        time.sleep(0.01)

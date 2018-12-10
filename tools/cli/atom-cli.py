#!/usr/bin/python3
import json
import shlex
import time
import sys
from atom import Element
from inspect import cleandoc
from prompt_toolkit import prompt, HTML, PromptSession
from prompt_toolkit import print_formatted_text as print
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style
from pyfiglet import Figlet


class AtomCLI:
    def __init__(self):
        self.element = Element("atom-cli")
        self.indent = 2
        self.style = Style.from_dict({
            "logo_color": "#6039C8",
            "completion-menu.completion": "bg:#000000 #ffffff",
            "completion-menu.completion.current": "bg:#555555 #ffffff",
            "scrollbar.background": "bg:#000000",
            "scrollbar.button": "bg:#000000",
        })

        self.session = PromptSession(style=self.style)
        self.cmd_map = {
            "help": self.cmd_help,
            "list": self.cmd_list,
            "records": self.cmd_records,
            "command": self.cmd_command,
            "read": self.cmd_read,
            "exit": self.cmd_exit,
        }
        self.print_atom_os_logo()

        self.usage = {
            "cmd_help": cleandoc("""
                Usage: 
                  help [<command>]"""),

            "cmd_list": cleandoc("""
                Usage: 
                  list elements
                  list streams [<stream_name>]"""),

            "cmd_records": cleandoc("""
                Usage: 
                  records log [<last_N_seconds>] [<element>...]
                  records cmdres [<last_N_seconds>] <element>..."""),

            "cmd_command": cleandoc("""
                Usage: 
                  command <element> <element_command> [<data>]"""),

            "cmd_read": cleandoc("""
                Usage: 
                  read <element> <stream> [<rate_hz>]"""),

            "cmd_exit": cleandoc("""
                Usage: 
                  exit"""),
        }

    def run(self):
        while True:
            try:
                inp = shlex.split(
                    self.session.prompt("\n> ", auto_suggest=AutoSuggestFromHistory()))
                if not inp:
                    continue
                command, args = inp[0], inp[1:]
                if command not in self.cmd_map.keys():
                    print("Invalid command. Type 'help' for valid commands.")
                else:
                    self.cmd_map[command](*args)
            except KeyboardInterrupt:
                pass
            except EOFError:
                self.cmd_exit()

    def print_atom_os_logo(self):
        f = Figlet(font="slant")
        logo = f.renderText("ATOM OS")
        print(HTML(f"<logo_color>{logo}</logo_color>"), style=self.style)

    def cmd_help(self, *args):
        usage = self.usage["cmd_help"]
        if len(args) > 1:
            print(usage)
            print("\nToo many arguments to 'help'.")
            return
        if args:
            if args[0] in self.cmd_map.keys():
                print(self.usage[f"cmd_{args[0]}"])
            else:
                print(f"Command {args[0]} does not exist.")
        else:
            print("Available commands:")
            for command in self.cmd_map.keys():
                print(command)

    def cmd_list(self, *args):
        usage = self.usage["cmd_list"]
        mode_map = {
            "elements": self.element.get_all_elements,
            "streams": self.element.get_all_streams,
        }
        if not args:
            print(usage)
            print("\n'list' must have an argument.")
            return
        mode = args[0]
        if mode not in mode_map.keys():
            print(usage)
            print("\nInvalid argument to 'list'.")
            return
        if len(args) > 1 and mode != "streams":
            print(usage)
            print(f"\nInvalid number of arguments for command 'list {mode}'.")
            return
        if len(args) > 2:
            print(usage)
            print("\n'list' takes at most 2 arguments.")
            return
        items = mode_map[mode](*args[1:])
        if not items:
            print(f"No {mode} exist.")
            return
        for item in items:
            print(item)

    def cmd_records(self, *args):
        usage = self.usage["cmd_records"]
        if not args:
            print(usage)
            print("\n'records' must have an argument.")
            return
        mode = args[0]

        # Check for start time
        if len(args) > 1 and args[1].isdigit():
            ms = int(args[1]) * 1000
            start_time = str(int(self.element._get_redis_timestamp()) - ms)
            elements = set(args[2:])
        else:
            # If no start time, go from the very beginning
            start_time = "-"
            elements = set(args[1:])

        if mode == "log":
            records = self.mode_log(start_time, elements)
        elif mode == "cmdres":
            if not elements:
                print(usage)
                print("\nMust provide elements from which to get command response streams from.")
                return
            records = self.mode_cmdres(start_time, elements)
        else:
            print(usage)
            print("\nInvalid argument to 'records'.")
            return

        if not records:
            print("No records.")
            return
        for record in records:
            print(self.format_record(record))

    def mode_log(self, start_time, elements):
        records = []
        all_records = self.element._rclient.xrange("log", start=start_time)
        for timestamp, content in all_records:
            if not elements or content[b"element"].decode() in elements:
                content["timestamp"] = timestamp.decode()
                records.append(content)
        return records

    def mode_cmdres(self, start_time, elements):
        streams, records = [], []
        for element in elements:
            streams.append(self.element._make_response_id(element))
            streams.append(self.element._make_command_id(element))
        for stream in streams:
            cur_records = self.element._rclient.xrange(stream, start=start_time)
            for timestamp, content in cur_records:
                content["type"], content["element"] = stream.split(":")
                content["timestamp"] = timestamp.decode()
                records.append((timestamp.decode(), content))
        # Sort records by timestamp
        # If the timestamps are the same, put commands before responses
        return [record[1] for record in sorted(records, key=lambda x: (x[0], x[1]["type"]))]

    def format_record(self, record):
        formatted_record = {}
        for k, v in record.items():
            if type(k) is bytes:
                k = k.decode()
            try:
                v = v.decode()
            except:
                v = str(v)
            formatted_record[k] = v
        sorted_record = {k: v for k, v in sorted(formatted_record.items(), key=lambda x: x[0])}
        return json.dumps(sorted_record, indent=self.indent)

    def cmd_command(self, *args):
        usage = self.usage["cmd_read"]
        if len(args) < 2:
            print(usage)
            print("\nToo few arguments.")
            return
        if len(args) > 3:
            print(usage)
            print("\nToo many arguments.")
            return
        element_name = args[0]
        command_name = args[1]
        if len(args) == 3:
            data = args[2]
        else:
            data = ""
        resp = self.element.command_send(element_name, command_name, data)
        print(self.format_record(resp))

    def cmd_read(self, *args):
        usage = self.usage["cmd_read"]
        if len(args) < 1:
            print(usage)
            print("\nToo few arguments.")
            return
        if len(args) > 2:
            print(usage)
            print("\nToo many arguments.")
            return
        element_name, stream_name = args[0].split(":")
        if len(args) == 2:
            try:
                rate = float(args[1])
                if rate < 0:
                    raise ValueError()
            except ValueError:
                print("rate must be an float greater than 0.")
                return
        else:
            rate = None

        last_timestamp = None
        while True:
            start_time = time.time()
            entries = self.element.entry_read_n(element_name, stream_name, 1)
            if not entries:
                print(f"No data from {element_name}:{stream_name}.")
                return
            entry = entries[0]
            timestamp = entry["timestamp"]
            if timestamp != last_timestamp:
                last_timestamp = timestamp
                print(self.format_record(entry))
            if rate:
                time.sleep(max(1 / rate - (time.time() - start_time), 0))

    def cmd_exit(*args):
        print("Exiting.")
        sys.exit()


if __name__ == "__main__":
    # TODO REMOVE TESTING STUFF
    import threading
    from atom.messages import Response

    def add_1(x):
        return Response(int(x) + 1)

    elem1 = Element("element1")
    elem1.command_add("add_1", add_1)

    def loop():
        i = 0
        while True:
            elem1.entry_write("stream1", {"data": i})
            i += 1
            time.sleep(1)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    t1 = threading.Thread(target=elem1.command_loop, daemon=True)
    t1.start()
    # elem1.log(7, "element1 log 1", stdout=False)
    # elem1.log(7, "element1 log 2", stdout=False)

    elem2 = Element("element2")
    # elem2.log(7, "element2 log 1", stdout=False)
    # elem2.log(7, "element2 log 2", stdout=False)
    ############################

    atom_cli = AtomCLI()
    atom_cli.run()

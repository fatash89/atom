#!/usr/bin/python3
import json
import time
import sys
from atom import Element
from inspect import cleandoc
from os import uname
from prompt_toolkit import prompt, HTML, PromptSession
from prompt_toolkit import print_formatted_text as print
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style
from msgpack.exceptions import ExtraData
from pyfiglet import Figlet
from uuid import uuid4


class AtomCLI:

    def __init__(self):
        self.element = Element(f"atom-cli_{uname().nodename}_{uuid4().hex}")
        self.indent = 2
        self.style = Style.from_dict({
            "logo_color": "#6039C8",
        })
        self.session = PromptSession(style=self.style)
        self.print_atom_os_logo()
        self.use_msgpack = True
        self.cmd_map = {
            "help": self.cmd_help,
            "list": self.cmd_list,
            "records": self.cmd_records,
            "command": self.cmd_command,
            "read": self.cmd_read,
            "exit": self.cmd_exit,
            "msgpack": self.cmd_msgpack,
        }
        self.usage = {
            "cmd_help": cleandoc("""
                Displays available commands and shows usage for commands.

                Usage:
                  help [<command>]"""),

            "cmd_list": cleandoc("""
                Displays available elements or streams.
                Can filter streams based on element.

                Usage:
                  list elements
                  list streams [<element>]"""),

            "cmd_records": cleandoc("""
                Displays log records or command and response records.
                Can filter records from the last N seconds or from certain elements.

                Usage:
                  records log [<last_N_seconds>] [<element>...]
                  records cmdres [<last_N_seconds>] <element>..."""),

            "cmd_command": cleandoc("""
                Sends a command to an element and displays the response.

                Usage:
                  command <element> <element_command> [<data>]"""),

            "cmd_read": cleandoc("""
                Displays the entries of an element's stream.
                Can provide a rate to print the entries for ease of reading.

                Usage:
                  read <element> <stream> [<rate_hz>]"""),

            "cmd_exit": cleandoc("""
                Exits the atom-cli tool.
                Can also use the shortcut CTRL+D.

                Usage:
                  exit"""),

            "cmd_msgpack": cleandoc("""
                Turns on/off msgpack serialization and deserialization.
                Pass True to use msgpack, False to turn off. Default False.

                Usage:
                  msgpack True/False"""),
        }

    def run(self):
        """
        The main loop of the CLI.
        Reads the user input, verifies the command exists and calls the command.
        """
        while True:
            try:
                inp = self.session.prompt(
                    "\n> ", auto_suggest=AutoSuggestFromHistory()).split(" ")
                if not inp:
                    continue
                command, args = inp[0], inp[1:]
                if command not in self.cmd_map.keys():
                    print("Invalid command. Type 'help' for valid commands.")
                else:
                    self.cmd_map[command](*args)
            # Handle CTRL+C so user can break loops without exiting
            except KeyboardInterrupt:
                pass
            # Exit on CTRL+D
            except EOFError:
                self.cmd_exit()
            except Exception as e:
                print(str(type(e)) + " " + str(e))

    def print_atom_os_logo(self):
        f = Figlet(font="slant")
        logo = f.renderText("ATOM OS")
        print(HTML(f"<logo_color>{logo}</logo_color>"), style=self.style)

    def format_record(self, record):
        """
        Takes a record out of Redis, decodes the keys and values (if possible)
        and returns a formatted json string sorted by keys.
        """
        formatted_record = {}
        for k, v in record.items():
            if type(k) is bytes:
                k = k.decode()
            if not self.use_msgpack:
                try:
                    v = v.decode()
                except:
                    v = str(v)
            formatted_record[k] = v
        sorted_record = {k: v for k, v in sorted(
            formatted_record.items(), key=lambda x: x[0])}
        try:
            ret = json.dumps(sorted_record, indent=self.indent)
        except TypeError as te:
            print("Cannot Print This Log Item, Sorry :(")

    def cmd_help(self, *args):
        usage = self.usage["cmd_help"]
        if len(args) > 1:
            print(usage)
            print("\nToo many arguments to 'help'.")
            return
        if args:
            # Prints the usage of the command
            if args[0] in self.cmd_map.keys():
                print(self.usage[f"cmd_{args[0]}"])
            else:
                print(f"Command {args[0]} does not exist.")
        else:
            print("Try 'help <command>' for usage on a command")
            print("Available commands:")
            for command in self.cmd_map.keys():
                print(f"  {command}")

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
        # If no start time, go from the very beginning
        else:
            start_time = "0"
            elements = set(args[1:])

        if mode == "log":
            records = self.mode_log(start_time, elements)
        elif mode == "cmdres":
            if not elements:
                print(usage)
                print(
                    "\nMust provide elements from which to get command response streams from.")
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
        """
        Reads the logs from Atom's log stream.

        Args:
            start_time (str): The time from which to start reading logs.
            elements (list): The elements on which to filter the logs for.
        """
        records = []
        all_records = self.element.entry_read_since(
            None, "log", start_time, deserialize=False)
        for record in all_records:
            if not elements or record["element"].decode() in elements:
                record = {key: (value if isinstance(value, str) else value.decode(
                )) for key, value in record.items()}  # Decode strings only which are required to
                records.append(record)
        return records

    def mode_cmdres(self, start_time, elements):
        """
        Reads the command and response records from the provided elements.

        Args:
            start_time (str): The time from which to start reading logs.
            elements (list): The elements to get the command and response records from.
        """
        streams, records = [], []
        for element in elements:
            streams.append(self.element._make_response_id(element))
            streams.append(self.element._make_command_id(element))
        for stream in streams:
            try:
                cur_records = self.element.entry_read_since(
                    None, stream, start_time, deserialize=self.use_msgpack)
            except ExtraData as ea:
                cur_records = self.element.entry_read_since(
                    None, stream, start_time, deserialize=(not self.use_msgpack))
            for record in cur_records:
                try:
                    record = {key: (value if isinstance(value, str) else value.decode(
                    )) for key, value in record.items()}  # Decode strings only which are required to
                except UnicodeError as e:
                    record = {key: value for key, value in record.items()}
                finally:
                    record["type"], record["element"] = stream.split(":")
                    records.append(record)
        return sorted(records, key=lambda x: (x["id"], x["type"]))

    def cmd_command(self, *args):
        usage = self.usage["cmd_command"]
        if len(args) < 2:
            print(usage)
            print("\nToo few arguments.")
            return
        element_name = args[0]
        command_name = args[1]
        if len(args) >= 3:
            data = str(" ".join(args[2:]))
            if self.use_msgpack:
                try:
                    data = json.loads(data)
                except:
                    print("Received improperly formatted data!")
                    return
        else:
            data = ""
        resp = self.element.command_send(
            element_name, command_name, data, serialize=self.use_msgpack, deserialize=self.use_msgpack)
        print(self.format_record(resp))

    def cmd_read(self, *args):
        usage = self.usage["cmd_read"]
        if len(args) < 2:
            print(usage)
            print("\nToo few arguments.")
            return
        if len(args) > 3:
            print(usage)
            print("\nToo many arguments.")
            return
        if len(args) == 3:
            try:
                rate = float(args[2])
                if rate < 0:
                    raise ValueError()
            except ValueError:
                print("rate must be an float greater than 0.")
                return
        else:
            rate = None
        element_name, stream_name = args[:2]

        last_timestamp = None
        while True:
            start_time = time.time()
            entries = self.element.entry_read_n(
                element_name, stream_name, 1, deserialize=self.use_msgpack)
            if not entries:
                print(f"No data from {element_name} {stream_name}.")
                return
            entry = entries[0]
            timestamp = entry["id"]
            # Only print the entry if it is different from the previous one
            if timestamp != last_timestamp:
                last_timestamp = timestamp
                print(self.format_record(entry))
            if rate:
                time.sleep(max(1 / rate - (time.time() - start_time), 0))

    def cmd_msgpack(self, *args):
        usage = self.usage["cmd_msgpack"]
        if (len(args) != 1):
            print(usage)
            print("\nPass one argument: True or False to turn on/off msgpack.")
            return

        # Otherwise try to get the new msgpack valud
        if (args[0].lower() == "true"):
            self.use_msgpack = True
        elif (args[0].lower() == "false"):
            self.use_msgpack = False
        else:
            print("\nArgument must be True or False.")

        print("Current msgpack status is {}".format(self.use_msgpack))

    def cmd_exit(*args):
        print("Exiting.")
        sys.exit()


if __name__ == "__main__":
    atom_cli = AtomCLI()
    atom_cli.run()

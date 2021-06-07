#!/usr/bin/env python3
import json
import sys
import time
from inspect import cleandoc
from os import uname
from uuid import uuid4

import atom.serialization as ser
from atom import Element
from prompt_toolkit import HTML, PromptSession
from prompt_toolkit import print_formatted_text as print
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.styles import Style
from pyfiglet import Figlet


class AtomCLI:
    def __init__(self):
        self.element = Element(f"atom-cli_{uname().nodename}_{uuid4().hex}")
        self.indent = 2
        self.style = Style.from_dict(
            {
                "logo_color": "#6039C8",
            }
        )
        self.session = PromptSession(style=self.style)
        self.print_atom_os_logo()
        self.serialization: ser.SerializationMethod = "msgpack"
        self.cmd_map = {
            "help": self.cmd_help,
            "list": self.cmd_list,
            "records": self.cmd_records,
            "command": self.cmd_command,
            "read": self.cmd_read,
            "exit": self.cmd_exit,
            "serialization": self.cmd_serialization,
        }
        self.usage = {
            "cmd_help": cleandoc(
                """
                Displays available commands and shows usage for commands.

                Usage:
                  help [<command>]"""
            ),
            "cmd_list": cleandoc(
                """
                Displays available elements, streams, or commands.
                Can filter streams and commands based on element.

                Usage:
                  list elements
                  list streams [<element>]
                  list commands [<element>]"""
            ),
            "cmd_records": cleandoc(
                """
                Displays log records or command and response records.
                Can filter records from the last N seconds or from certain elements.

                Usage:
                  records cmdres [<last_N_seconds>] <element>..."""
            ),
            "cmd_command": cleandoc(
                """
                Sends a command to an element and displays the response.

                Usage:
                  command <element> <element_command> [<data>]"""
            ),
            "cmd_read": cleandoc(
                """
                Displays the entries of an element's stream.
                Can provide a rate to print the entries for ease of reading.

                Usage:
                  read <element> <stream> [<rate_hz>]"""
            ),
            "cmd_exit": cleandoc(
                """
                Exits the atom-cli tool.
                Can also use the shortcut CTRL+D.

                Usage:
                  exit"""
            ),
            "cmd_serialization": cleandoc(
                """
                Sets serialization/deserialization setting to either use msgpack,
                Apache arrow, or no (de)serialization. Defaults to msgpack serialization.
                This setting is overriden by deserialization keys received in stream.

                Usage:
                  serialization (msgpack | arrow | none)"""
            ),
        }

    def run(self):
        """
        The main loop of the CLI.
        Reads the user input, verifies the command exists and calls the command.
        """
        while True:
            try:
                inp = self.session.prompt(
                    "\n> ", auto_suggest=AutoSuggestFromHistory()
                ).split(" ")
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
            if not self.serialization:
                try:
                    v = v.decode()
                except Exception:
                    v = str(v)
            formatted_record[k] = v

        sorted_record = {
            k: v for k, v in sorted(formatted_record.items(), key=lambda x: x[0])
        }
        try:
            ret = json.dumps(sorted_record, indent=self.indent)
        except TypeError:
            ret = sorted_record
        finally:
            return ret

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
            "commands": self.element.get_all_commands,
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
        if len(args) > 1 and mode == "elements":
            print(usage)
            print("\nInvalid number of arguments for command 'list elements'.")
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

        if mode == "cmdres":
            if not elements:
                print(usage)
                print(
                    "\nMust provide elements from which to get command response streams from."
                )
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

    def mode_cmdres(self, start_time: str, elements: "set[str]"):
        """
        Reads the command and response records from the provided elements.
        Args:
            start_time (str): The time from which to start reading logs.
            elements (list): The elements to get the command and response
                records from.
        """
        streams, entries = {}, []
        for element in elements:
            streams[self.element._make_response_id(element)] = start_time
            streams[self.element._make_command_id(element)] = start_time

        # Read data
        stream_entries = self.element._rclient.xread(streams)

        # Deserialize
        for key, msgs in stream_entries:
            print("stream entry key:", key)
            key = key.decode()
            for uid, entry in msgs:
                entry = self.element._decode_entry(entry)
                serialization = self.element._get_serialization_method(
                    entry, None, False
                )
                entry = self.element._deserialize_entry(entry, method=serialization)
                entry["id"] = uid.decode()
                entries.append(entry)

                for entry_key, entry_value in entry.items():
                    try:
                        if not isinstance(entry_value, str):
                            entry_value = entry_value.decode()
                    except Exception:
                        try:
                            entry_value = ser.deserialize(
                                entry_value, method=self.serialization
                            )
                        except Exception:
                            pass
                    finally:
                        entry[entry_key] = entry_value
                entry["type"], entry["element"] = str(key).split(":")
                print("Final print:", entry["type"], entry["element"])
        return sorted(entries, key=lambda x: (x["id"], x["type"]))

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
            if self.serialization:
                try:
                    data = json.loads(data)
                except Exception:
                    print("Received improperly formatted data!")
                    return
        else:
            data = ""
        resp = self.element.command_send(
            element_name,
            command_name,
            data,
            serialize=(self.serialization is not None),
            deserialize=(self.serialization is not None),
            serialization=self.serialization,
        )  # shouldn't be used if it's None
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
                element_name,
                stream_name,
                1,
                deserialize=(self.serialization is not None),
                serialization=self.serialization,
            )  # shouldn't be used if it's None
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

    def cmd_serialization(self, *args):
        usage = self.usage["cmd_serialization"]
        if len(args) != 1:
            print(usage)
            print(f"\nPass one argument: {ser.Serializations.print_values()}.")
            return

        # Otherwise try to get the new setting
        if ser.is_valid_serialization(args[0].lower()):
            self.serialization = args[0].lower() if args[0].lower() != "none" else None
        else:
            print(f"\nArgument must be one of {ser.Serializations.print_values()}.")

        print("Current serialization status is {}".format(self.serialization))

    def cmd_exit(*args):
        print("Exiting.")
        sys.exit()


if __name__ == "__main__":
    atom_cli = AtomCLI()
    atom_cli.run()

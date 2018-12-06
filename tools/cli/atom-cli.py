#!/usr/bin/python3
import json
import shlex
from atom import Element
from prompt_toolkit import prompt, HTML, PromptSession
from prompt_toolkit import print_formatted_text as print
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import InMemoryHistory
from pyfiglet import Figlet


class AtomCLI:
    def __init__(self):
        self.element = Element("atom-cli")
        self.print_atom_os_logo()
        self.session = PromptSession()
        self.cmd_map = {
            "help": self.cmd_help,
            "list": self.cmd_list,
            "logs": self.cmd_logs,
            "command": self.cmd_command,
        }
        self.command_completer = WordCompleter(self.cmd_map.keys())
        self.indent = 2

    def run(self):
        while True:
            inp = shlex.split(self.session.prompt(
                "\n> ", auto_suggest=AutoSuggestFromHistory(),
                completer=self.command_completer))
            if not inp:
                continue
            command, args = inp[0], inp[1:]
            if command not in self.cmd_map.keys():
                print("Invalid command. Type 'help' for valid commands.")
            else:
                self.cmd_map[command](*args)

    def print_atom_os_logo(self):
        f = Figlet(font="slant")
        logo = f.renderText("ATOM OS")
        print(HTML(f"<purple>{logo}</purple>"))

    def cmd_help(self, *args):
        print("Available commands")
        for command in self.cmd_map.keys():
            print(command)

    def cmd_list(self, *args):
        mode_map = {
            "elements": self.element.get_all_elements,
            "streams": self.element.get_all_streams,
        }
        if not args:
            print("'list' must have an argument.")
            return
        mode = args[0]
        if mode not in mode_map.keys():
            print("Invalid argument to 'list'.")
            return
        if len(args) > 1 and mode != "streams":
            print(f"Invalid number of arguments for command 'list {mode}'.")
            return
        if len(args) > 2:
            print("'list' takes at most 2 arguments.")
            return
        items = mode_map[mode](*args[1:])
        if not items:
            print(f"No {mode} exist.")
            return
        for item in items:
            print(item)

    def cmd_logs(self, *args):
        if args and args[0].isdigit():
            ms = int(args[0]) * 1000
            start_time = str(int(self.element._get_redis_timestamp()) - ms)
            elements = set(args[1:])
        else:
            start_time = "-"
            elements = set(args)

        if elements:
            all_logs = self.element._rclient.xrange("log", start=start_time)
            logs = []
            for timestamp, content in all_logs:
                if content[b"element"].decode() in elements:
                    logs.append((timestamp, content))
        else:
            logs = self.element._rclient.xrange("log", start=start_time)

        if not logs:
            print("No logs.")
            return
        for log in self.format_logs(logs):
            print(log)

    def format_logs(self, logs):
        formatted_logs = []
        for timestamp, content in logs:
            formatted_log = json.dumps({
                "element": content[b"element"].decode(),
                "timestamp": timestamp.decode(),
                "level": content[b"level"].decode(),
                "msg": content[b"msg"].decode(),
            }, indent=self.indent)
            formatted_logs.append(formatted_log)
        return formatted_logs

    def cmd_command(self, *args):
        if len(args) < 2:
            print("Too few arguments.")
            return
        if len(args) > 3:
            print("Too many arguments.")
            return
        element_name = args[0]
        command_name = args[1]
        if len(args) == 3:
            data = args[2]
        else:
            data = ""
        resp = self.element.command_send(element_name, command_name, data)
        formatted_resp = json.dumps({
            "err_code": resp["err_code"],
            "err_str": resp["err_str"],
            "data": repr(resp["data"]),
        }, indent=self.indent)
        print(formatted_resp)


if __name__ == "__main__":
    # TODO REMOVE TESTING STUFF
    import threading
    from atom.messages import Response
    def add_1(x):
        return Response(int(x)+1)

    elem1 = Element("element1")
    elem1.command_add("add_1", add_1)
    t = threading.Thread(target=elem1.command_loop, daemon=True)
    t.start()
    # elem1.log(7, "element1 log 1", stdout=False)
    # elem1.log(7, "element1 log 2", stdout=False)

    elem2 = Element("element2")
    # elem2.log(7, "element2 log 1", stdout=False)
    # elem2.log(7, "element2 log 2", stdout=False)
    ############################

    atom_cli = AtomCLI()
    atom_cli.run()

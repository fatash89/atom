#!/usr/bin/python3
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
        }
        self.command_completer = WordCompleter(self.cmd_map.keys())

    def run(self):
        while True:
            inp = self.session.prompt("\n> ",
                auto_suggest=AutoSuggestFromHistory(),
                completer=self.command_completer).split()
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
        if not args:
            print("'logs' must have an argument.")
            return
        element_name = args[0]
        log_id = self.element._make_log_id(element_name)
        logs = self.element._rclient.xrange(log_id)
        if not logs:
            print(f"No logs for {element_name}.")
            return
        for log in self.format_logs(logs):
            print(log)

    def format_logs(self, logs):
        formatted_logs = []
        for timestamp, content in logs:
            formatted_log = {
                "timestamp": timestamp.decode(),
                "level": content[b"level"].decode(),
                "msg": content[b"msg"].decode(),
            }
            formatted_logs.append(formatted_log)
        return formatted_logs


if __name__ == "__main__":
    # TODO REMOVE TESTING STUFF
    elem1 = Element("element1")
    elem1.log(7, "element1 log 1", stdout=False)
    elem1.log(7, "element1 log 2", stdout=False)

    elem2 = Element("element2")
    elem2.log(7, "element2 log 1", stdout=False)
    elem2.log(7, "element2 log 2", stdout=False)
    ############################

    atom_cli = AtomCLI()
    atom_cli.run()

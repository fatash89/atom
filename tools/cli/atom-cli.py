#!/usr/bin/python3
from atom import Element
from prompt_toolkit import prompt, HTML, PromptSession
from prompt_toolkit import print_formatted_text as print
from pyfiglet import Figlet


class AtomCLI:
    def __init__(self):
        self.element = Element("atom-cli")
        self.print_atom_os()
        self.session = PromptSession()
        self.cmd_map = {
            "help": self.cmd_help,
            "list": self.cmd_list,
        }

    def run(self):
        while True:
            inp = self.session.prompt("> ").split()
            if not inp:
                continue
            command, args = inp[0], inp[1:]
            if command not in self.cmd_map.keys():
                print("Invalid command. Type help for valid commands.")
            else:
                self.cmd_map[command](*args)

    def print_atom_os(self):
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
        if not args or args[0] not in mode_map.keys():
            print("Invalid argument to list.")
            return
        items = mode_map[args[0]]()
        if not items:
            print(f"No {args[0]} exist.")
            return
        for item in items:
            print(item)


if __name__ == "__main__":
    atom_cli = AtomCLI()
    atom_cli.run()

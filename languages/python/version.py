"""
Script for setting library version configuration used in installation.
Automatically called when running setup.py.
Version can be either dynamically determined through git information, or
passed in as an argument.
"""

from pathlib import Path
import subprocess
import argparse

CONFIG_FILE = Path(__file__).parent / "atom/config.py"


def call_git_describe(abbrev):
    p = subprocess.run(['git', 'describe', '--tags', '--abbrev=%d' % abbrev],
                       stdout=subprocess.PIPE)
    line = str(p.stdout, 'utf-8').strip()
    line = line[1:] if line[0] == 'v' else line
    return line.strip('\n')


def is_dirty():
    # check if there are commits since last tag
    try:
        p = subprocess.run(["git", "diff-index", "--name-only", "HEAD"],
                           stdout=subprocess.PIPE)
        return len(str(p.stdout)) > 0
    except Exception:
        return False


def get_git_version(abbrev=7):
    # try to get the current version using “git describe”.
    version = call_git_describe(abbrev)
    if is_dirty():
        version += "-dirty"

    return version


def replace_version_config(file, replacement):
    with open(CONFIG_FILE, "r") as file:
        configs = file.readlines()

    version_bools = [x.startswith("VERSION =") for x in configs]
    # replace existing configuration or add it if its not present
    try:
        version_index = version_bools.index(True)
        configs[version_index] = replacement
    except ValueError:
        configs.append(replacement)

    with open(CONFIG_FILE, "w") as file:
        file.writelines(configs)


def main(version=None):
    # use version argument if it is passed in; else find version from .git
    version = version if version else get_git_version()

    # replace version config if there's a new one
    if version:
        version_str = f"VERSION = \"{version}\"\n"
        replace_version_config(CONFIG_FILE, version_str)

    return version


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Replace library version config')
    parser.add_argument('--version', type=str,
                        help='library version')

    args = parser.parse_args()

    main(version=args.version)

"""
Script for setting library version configuration used in installation.
Automatically called when running setup.py.
Version can be either dynamically determined through git information, or
passed in as an argument.
"""

import argparse
import os
import subprocess

CONFIG_FILE = os.path.join(os.path.abspath(os.path.dirname(__file__)), "atom/config.py")


def call_git_describe(abbrev):
    """
    Returns latest git tag if available.
    """
    p = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=%d" % abbrev], stdout=subprocess.PIPE
    )
    line = str(p.stdout, "utf-8").strip()
    line = line[1:] if line[0] == "v" else line
    return line.strip("\n")


def is_dirty():
    """
    Returns True/False if there are commits since the last tag.
    """
    try:
        p = subprocess.run(
            ["git", "diff-index", "--name-only", "HEAD"], stdout=subprocess.PIPE
        )
        return len(str(p.stdout)) > 0
    except Exception:
        return False


def get_git_version(abbrev=7):
    """
    Calls "git describe" to get current version; adds "dirty" if there have
    been extra commits since the latest tag. Will return empty list if no
    .git information is available.
    """
    version = call_git_describe(abbrev)
    if is_dirty():
        version += "-dirty"

    return version


def get_existing_config_line():
    """
    Returns configs and line of version in config.py;
    Returns None if version not present in config.py.
    """
    with open(CONFIG_FILE, "r") as file:
        configs = file.readlines()

    version_bools = [x.startswith("VERSION =") for x in configs]

    try:
        return configs, version_bools.index(True)
    except Exception:
        return configs, None


def replace_version_config(replacement):
    """
    Replace existing configuration or add it if its not present
    """
    configs, line_num = get_existing_config_line()

    if line_num:
        configs[line_num] = replacement
    else:
        configs.append(replacement)

    with open(CONFIG_FILE, "w") as file:
        file.writelines(configs)


def main(version=None):
    # use version argument if it is passed in; else find version from .git
    version = version if version else get_git_version()

    # replace version config if there's a new one
    if version:
        version_str = '\nVERSION = "{}"\n'.format(version)
        replace_version_config(version_str)

    return version


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replace library version config")
    parser.add_argument("--version", type=str, help="library version")

    args = parser.parse_args()

    main(version=args.version)

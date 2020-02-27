from pathlib import Path
from subprocess import Popen, PIPE

CONFIG_FILE = Path(__file__).parent / "atom/config.py"


def call_git_describe(abbrev):
    p = Popen(['git', 'describe', '--tags', '--abbrev=%d' % abbrev],
              stdout=PIPE, stderr=PIPE)
    p.stderr.close()
    line = str(p.stdout.readlines()[0], 'utf-8').strip()
    line = line[1:] if line[0] == 'v' else line
    return line.strip('\n')


def is_dirty():
    # check if there are commits since last tag
    try:
        p = Popen(["git", "diff-index", "--name-only", "HEAD"],
                  stdout=PIPE, stderr=PIPE)
        p.stderr.close()
        lines = p.stdout.readlines()
        return len(lines) > 0
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
        configs[version_index] = version_str
    except ValueError:
        configs.append(version_str)

    with open(CONFIG_FILE, "w") as file:
        file.writelines(configs)


if __name__ == "__main__":
    version = get_git_version()

    # replace version config if there's a new one
    if version:
        version_str = f"VERSION = \"{version}\"\n"
        replace_version_config(CONFIG_FILE, version_str)

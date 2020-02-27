# Calculates the current version number from the
# output of “git describe”, modified to conform to the versioning
# scheme that setuptools uses.

from subprocess import Popen, PIPE


def call_git_describe(abbrev):
    p = Popen(['git', 'describe', '--tags', '--abbrev=%d' % abbrev],
              stdout=PIPE, stderr=PIPE)
    p.stderr.close()
    line = str(p.stdout.readlines()[0], 'utf-8')
    return line.strip().strip('\n')


def is_dirty():
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


if __name__ == "__main__":
    print(get_git_version())

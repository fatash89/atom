### Requirements
- Python 3.7+
- Redis

### Bumping version

Update the version manually in the following files:

- `languages/python/setup.py`
- `languages/python/setup_local.py`
- `languages/python/atom/config.py`
- `docker-compose-dev.yml`

### Publishing on PyPI

__All of the following should be done on the host, not in the Docker container__.

We use `twine` to package Atom to upload it to PyPI. Make sure you have `twine` installed on your host: `pip install twine`.

First `cd languages/python`. If you have a `dist` folder in there from a previous install, remove its contents with `rm dist/*`.

Then `python setup.py sdist && twine upload -r pypi dist/*`.

You'll need a username/password to upload the package to PyPI; get these from Dan/Kyle.

### Setup

```
pip install -r requirements.txt
```

```
python setup_local.py install
```

#### `pyright` for type checking and code completion in your text editor

[See wiki](https://github.com/elementary-robotics/wiki/wiki/Python-Code-Completion-and-Type-Checking-in-Text-Editors)

Note: `pyright` can't resolve `atom` imports like `from atom.config import ...`, unless it's run in the `languages/python` directory (this one).

Also, `pyright` can has trouble with these imports if the `pyrightconfig.json` file isn't in the same directory from which pyright is run. We could either change the `atom` imports to be relative imports, or we can just run `pyright` from this directory.

If you want type checking in your text editor, you probably want this directory at the root of your "project".

### Testing

Make sure the Redis server is running, then run pytest

```
pytest
```

### Logging

Logging environment variables:
- ATOM_LOG_DIR: Directory where the log files will be written, default is the current directory
- ATOM_LOG_FILE_SIZE: Maximum byte size of a log file before it will be rotated, default 2000
- ATOM_LOG_LEVEL: Python log level, default INFO

Element log files are written to the directory specified by the ATOM_LOG_DIR environment variable. The log files in this directory are separated by element name. To tail all of the log files in the log directory in one stream, from your container, run `tail -qF $ATOM_LOG_DIR/*.log`.

To copy the logs from the container onto your local machine, run `docker cp {CONTAINER}:{ATOM_LOG_DIR}/ .` where CONTAINER is the docker container id and ATOM_LOG_DIR is the log file directory.

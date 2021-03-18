### Requirements
- Python 3.7+
- Redis

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

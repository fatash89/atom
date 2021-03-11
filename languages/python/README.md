### Requirements
- Python 3.6+
- Redis

### Setup
```
pip install -r requirements.txt
```
```
python setup_local.py install
```

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

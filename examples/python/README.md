## atombot


### Overview
Atombot is a simple robot that can be commanded to move left and right in addition to publishing its state to a stream.


### Commands
| Command | Data | Response |
| ------- | ---- | -------- |
| move_left | num_steps (int) | str |
| move_right | num_steps (int) | str |
| transform | None | str |


### Streams
| Stream | Format |
| ------ | ------ |
| pos | int |
| pos_map | str |


### docker-compose configuration
```
  atombot:
    build:
      context: .
      dockerfile: Dockerfile
    volumes:
      - type: volume
        source: shared
        target: /shared
        volume:
          nocopy: true
    depends_on:
      - "nucleus"
```

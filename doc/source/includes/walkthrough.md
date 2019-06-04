# Atom Walkthrough

Now that we have a basic understanding of atom, docker, and docker-compose we can go ahead and make a simple element!

Here's what we'll cover in this walkthrough.

- Setting up your project
- Creating a simple element
- Setting up your Dockerfile
- Modifying your launch script
- Launching the system with docker-compose
- Interacting and debugging with atom-cli

<aside class="notice">
This example is written in Python, please switch over to the `python` tab at right.
</aside>

## Project Template

Download the files below and put them into a new folder named `atombot` on your system. These files are taken from the [template](https://github.com/elementary-robotics/atom/tree/master/template) from the Atom OS repo.

| File | Description |
|------|-------------|
| <a href="/walkthrough/Dockerfile" download>`Dockerfile`</a> | Specifies how to build the element into a Docker container. Installs everything the element needs and copies the code. |
| <a href="/walkthrough/launch.sh" download>`launch.sh`</a> | Runs when the element is booted, invokes the proper commands/sequence to get the element up and running. |
| <a href="/walkthrough/docker-compose.yml" download>`docker-compose.yml`</a> | Specifies which elements to launch and how to link them. At the very least needs the `nucleus` element as well as our element! |

## Creating a simple element
```c
// Please switch to python tab
```

```cpp
// Please switch to python tab
```

```python
# atombot.py
# atombot.py
from atom import Element
from atom.messages import Response
from threading import Thread, Lock
from time import sleep

class AtomBot:

    def __init__(self):
        # This defines atombot's current position
        self.pos = 2
        # We allow 5 different positions that atombot can move to
        self.max_pos = 5
        # An ascii representation of atombot!
        self.atombot = "o"
        # Lock on updates to robot position
        self.pos_lock = Lock()
        # Lock on updates to robot representation
        self.bot_lock = Lock()

    def move_left(self, steps):
        """
        Command for moving AtomBot in left for a number of steps.

        Args:
            steps: Number of steps to move.
        """
        # Note that we are responsible for converting the data type from the sent command
        steps = int(steps)
        if steps < 0 or steps > self.max_pos:
            # If we encounter an error, we can send an error code and error string in the response of the command
            return Response(err_code=1, err_str=f"Steps must be between 0 and {self.max_pos}")

        # Update the position
        try:
            self.pos_lock.acquire()
            self.pos = max(0, self.pos - steps)
        finally:
            self.pos_lock.release()

        # If successful, we simply return a success string
        return Response(data=f"Moved left {steps} steps.", serialize=True)

    def move_right(self, steps):
        """
        Command for moving AtomBot in right for a number of steps.

        Args:
            steps: Number of steps to move.
        """
        # Note that we are responsible for converting the data type from the sent command
        steps = int(steps)
        if steps < 0 or steps > self.max_pos:
            # If we encounter an error, we can send an error code and error string in the response of the command
            return Response(err_code=1, err_str=f"Steps must be between 0 and {self.max_pos}")

        # Update the position
        try:
            self.pos_lock.acquire()
            self.pos = min(self.max_pos, self.pos + steps)
        finally:
            self.pos_lock.release()

        # If successful, we simply return a success string
        return Response(data=f"Moved right {steps} steps.", serialize=True)

    def transform(self, _):
        """
        Command for transforming AtomBot!
        """
        # Notice that we must have a single parameter to a command, even if we aren't using it.

        # Update bot ascii representation
        try:
            self.bot_lock.acquire()
            if self.atombot == "o":
                self.atombot = "O"
            else:
                self.atombot = "o"
        finally:
            self.bot_lock.release()

        return Response(data=f"Transformed to {self.atombot}!", serialize=True)

    def get_pos(self):
        try:
            self.pos_lock.acquire()
            return self.pos
        finally:
            self.pos_lock.release()

    def get_pos_map(self):
        """
        Returns the current position of AtomBot as a visual.
        """
        pos_map = ["-"] * self.max_pos
        cur_pos = self.get_pos()
        try:
            self.bot_lock.acquire()
            pos_map[cur_pos] = self.atombot
            return_str = " ".join(pos_map)
            return return_str
        finally:
            self.bot_lock.release()

if __name__ == "__main__":
    print("Launching...")
    # Create our element and call it "atombot"
    element = Element("atombot")

    # Instantiate our AtomBot class
    atombot = AtomBot()

    # This registers the relevant AtomBot methods as a command in the atom system
    # We set the timeout so the caller will know how long to wait for the command to execute
    element.command_add("move_left", atombot.move_left, timeout=50, deserialize=True)
    element.command_add("move_right", atombot.move_right, timeout=50, deserialize=True)
    # Transform takes no inputs, so there's nothing to deserialize
    element.command_add("transform", atombot.transform, timeout=50)

    # We create a thread and run the command loop which will constantly check for incoming commands from atom
    # We use a thread so we don't hang on the command_loop function because we will be performing other tasks
    thread = Thread(target=element.command_loop, daemon=True)
    thread.start()

    # Create an infinite loop that publishes the position of atombot to a stream as well as a visual of its position
    while True:
        # We write our position data and the visual of atombot's position to their respective streams
        # The maxlen parameter will determine how many entries atom stores
        # This data is serialized using msgpack
        element.entry_write("pos", {"data": atombot.get_pos()}, maxlen=10, serialize=True)
        element.entry_write("pos_map", {"data": atombot.get_pos_map()}, maxlen=10, serialize=True)
        # We can also choose to write binary data directly without serializing it
        element.entry_write("pos_binary", {"data": atombot.get_pos()}, maxlen=10)

        # Sleep so that we aren't consuming all of our CPU resources
        sleep(0.01)
```

Download the `atombot.py` file <a href="/walkthrough/atombot.py" download>here</a>. The file is also shown at right for reference. This file implements the `AtomBot` element using the Python3 language client of the Atom OS. It exposes several commands as well as publishes some data.

## Setting up your Dockerfile

```
# Dockerfile

FROM elementaryrobotics/atom

# Want to copy over the contents of this repo to the code
#	section so that we have the source
ADD . /code

# Here, we'll build and install the code s.t. our launch script,
#	now located at /code/launch.sh, will launch our element/app

#
# TODO: build code
#

# Finally, specify the command we should run when the app is launched
WORKDIR /code
# If you had a requirements file you could uncomment the line below
# RUN pip3 install -r requirements.txt
RUN chmod +x launch.sh
CMD ["/bin/bash", "launch.sh"]
```

Nothing to do in this case, as the default `Dockerfile` should work for us.
However, if you needed to install any Python dependencies through pip or run a Makefile, `Dockerfile` would have to be modified.


## Modifying your launch script

> <button class="copy-button" onclick='copyText(this, "# launch.sh\r\n#!\/bin\/bash\r\n\r\npython3 atombot.py\r\n")'>Copy</button> Launch Script

```shell
# launch.sh
#!/bin/bash

python3 atombot.py
```

Modify the launch script `launch.sh` by copying the content on the right, to run your atombot executable.
Your docker container will run any commands in this script upon launch.

## Launching the system with docker-compose

```yaml
# docker-compose.yml

version: "3.2"

services:

  nucleus:
    container_name: nucleus
    image: elementaryrobotics/nucleus
    volumes:
      - type: volume
        source: shared
        target: /shared
        volume:
          nocopy: true
    command: ./launch.sh

  my_element:
    container_name: my_element
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
    command: tail -f /dev/null

volumes:
  shared:
    driver_opts:
      type: tmpfs
      device: tmpfs
```

> <button class="copy-button" onclick='copyText(this, "docker-compose build")'>Copy</button> Build element

```shell_session
$ docker-compose build
```

> <button class="copy-button" onclick='copyText(this, "docker-compose up -d")'>Copy</button> Start app

```shell_session
$ docker-compose up -d
```

Rename the `my_element` service and `container_name` to `atombot`, so that our docker container is appropriately named.

Remove the line that contains `tail -f /dev/null` in the `atombot` service.
This line is useful for development purposes as it keeps a container alive when the launch script is empty. However, since we have already modified the launch script, we no longer need this command.

<aside class="notice">If there are errors in your program that prevent it from running, the docker container will automatically shutdown. In this case, you may want to use the tail command as in the template's docker-compose file.</aside>

While in the `atombot` directory, run the following commands:

- Build the docker container for your element
    - `docker-compose build`
- Start the docker containers needed to run your element
    - `docker-compose up -d`

Congratulations! Your element is now running.


## Interacting and debugging with atom-cli

> <button class="copy-button" onclick='copyText(this, "docker container list")'>Copy</button> Print Container Info

```shell_session
$ docker container list
```

> <button class="copy-button" onclick='copyText(this, "docker exec -it atombot atom-cli")'>Copy</button> Launch Command-Line Interface (CLI)

```shell_session
$ docker exec -it atombot atom-cli
```

> <button class="copy-button" onclick='copyText(this, "help")'>Copy</button> (CLI) Print help information

```shell_session
> help
```

> <button class="copy-button" onclick='copyText(this, "Turn Msgpack Off")'>Copy</button> (CLI) Turn off Msgpack
```msgpack_off
> msgpack false
```



> <button class="copy-button" onclick='copyText(this, "help read")'>Copy</button> (CLI) Print help for a given option

```shell_session
> help read
```

> <button class="copy-button" onclick='copyText(this, "list elements")'>Copy</button> (CLI) List all running elements

```shell_session
> list elements
```

> <button class="copy-button" onclick='copyText(this, "list streams atombot")'>Copy</button> (CLI) List all streams for `atombot`

```shell_session
> list streams atombot
```

> <button class="copy-button" onclick='copyText(this, "read atombot pos_map")'>Copy</button> (CLI) Read `atombot` `pos_map` stream

```shell_session
> read atombot pos_map
```

> <button class="copy-button" onclick='copyText(this, "command atombot move_left 2")'>Copy</button> (CLI) Move `atombot` to the left

```shell_session
> command atombot move_left 2
```

> <button class="copy-button" onclick='copyText(this, "read atombot pos_map 1")'>Copy</button> (CLI) Read `atombot` `pos_map` stream at 1Hz

```shell_session
> read atombot pos_map 1
```

> <button class="copy-button" onclick='copyText(this, "records cmdres atombot")'>Copy</button> (CLI) See history of all commands to `atombot`

```shell_session
> records cmdres atombot
```

> <button class="copy-button" onclick='copyText(this, "records log")'>Copy</button> (CLI) See all log messages

```shell_session
> records log
```

> <button class="copy-button" onclick='copyText(this, "exit")'>Copy</button> (CLI) Exit CLI

```shell_session
> exit
```

> <button class="copy-button" onclick='copyText(this, "docker-compose down -t 1")'>Copy</button> Shut down app

```shell_session
$ docker-compose down -t 0 -v
```

Now that our atombot element is running, let's interact with it using `atom-cli`.
`atom-cli` is a tool used for debugging elements that comes installed in every element's container.

- Find the name of your element's container
    - `docker container list`
    - You will see an `atombot` container if you successfully modified the `docker-compose` file.
- Launch `atom-cli` in the container
    - `docker exec -it <CONTAINER_NAME> atom-cli`

<aside class="notice">If you would like to use a bash shell to debug your element's container you can run bash intead of atom-cli.</aside>

- You can list all of the available commands in `atom-cli` using the `help` command.
- You can view the usage of any command by typing `help <COMMAND>`
- Let's see if our atombot element is running
    - `list elements`
    - You should see `atombot` listed
- Let's see what streams atombot has
    - `list streams atombot`
- Let's read from the `pos_map` stream
    - `read atombot pos_map`
    - Great! We can see that atombot is in the center of the map
    - The read command will continually read from any element's stream until the user press CTRL+C
- Let's move atombot to the left
    - `command atombot move_left 2`
- We can control the rate at which the messages are printed by passing in the rate value (hz)
    - `read atombot pos_map 1`
- By default, atom-cli automatically msgpacks the data that is sent/received
- If you wish, you can override this with the `msgpack` command
    - `msgpack False`
    - Now if you try `read atombot pos_map 1`, you should see the raw binary data sent to this stream.
    - Do `msgpack True` to re-enable msgpack serialization
- We can see the history of our commands by using the `records` command
    - `records cmdres atombot`
- We can also see all of the logs that have been written so far
    - `records log`
- You can exit atom-cli by either
    - `exit`
    - CTRL+D
- Finally, you can shut down your element by running the following command on your host machine
    - `docker-compose down -t 0 -v`

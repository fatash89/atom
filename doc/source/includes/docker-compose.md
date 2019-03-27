# Docker Compose

With the basics of Docker understood, we can now learn about Docker Compose and how it's used in the Atom OS. Docker Compose is a tool that orchestrates launching and connecting multiple docker containers in a programmatic fashion. This is important because in the Atom OS we try to build elements that are small and reusable, each in its own container. There is a container for redis, one for the camera driver, one for viewing data, etc. We need to be able to easily launch all of the containers simultaneously, note any dependencies, and link them together.

## Installing Docker Compose

See the instructions [on the Docker site](https://docs.docker.com/compose/install/) for information on installing `docker-compose`.

## Docker-Compose file

> Example `docker-compose.yml` file

```yaml
version: "3.2"

services:

  nucleus:
    image: elementaryrobotics/nucleus
    volumes:
      - type: volume
        source: shared
        target: /shared
        volume:
          nocopy: true

  atom:
    image: elementaryrobotics/atom
    volumes:
      - type: volume
        source: shared
        target: /shared
        volume:
          nocopy: true
    depends_on:
      - "nucleus"
    command: "tail -f /dev/null"

volumes:
  shared:
    driver_opts:
      type: tmpfs
      device: tmpfs
```

### Overview

The core of Docker Compose is the `docker-compose.yml` file. This is a file with [YAML](https://yaml.org/) syntax. It specifies which containers to launch and volumes to create. In the example at right we'll launch two containers: one which contains the "nucleus" of the atom system and one which contains the Atom OS and client libraries. We'll also create a shared volume and mount it in both containers. This is essentially a shared folder between the containers which we use for communication between them.

### Reference

The official docker-compose file syntax and reference can be found [on the Docker site](https://docs.docker.com/compose/compose-file/).

### Detail

Within the `docker-compose.yml` file we're mainly concerned with the `services` and `volumes` sections. In the `services` section we will list each container we want docker compose to launch for us. The first indentation level for a service is the name that we'd like to call it. This field can be whatever you'd like, but for clarity it's recommended to have it match the image name.

Within each named service then there's a few key items:

| Keyword | Description |
|---------|-------------|
| `image` | which docker image to launch the container from |
| `volumes` | Contains information about shared volumes to mount in the container. We'll typically leave this section as in the default |
| `depends_on` | Notes a dependency. In the `atom` service we see that we depend on the `nucleus`. This will then cause `docker-compose` to wait for the `nucleus` to launch before launching the `atom` container |
| `command` | Overrides the default command for a container. When a container is started it will typically have some default command that launches the necessary processes. If the container doesn't have a default command or you want to override the default you can use this field. Here, the `tail -f /dev/null` command basically causes the container to just stay up and running so that we can go into it |

The `volumes` section describes any volumes to create and how they can be shared between containers. Again, this will pretty much always be left as it is. This section just creates a shared temporary filesystem that can be used for communication between the containers.

## Launching

> <button class="copy-button" onclick='copyText(this, "docker-compose up -d")'>Copy</button> Launch app

```shell_session
$ docker-compose up -d
```

> <button class="copy-button" onclick='copyText(this, "docker container list")'>Copy</button> List Containers

```shell_session
$ docker container list
CONTAINER ID        IMAGE                        COMMAND                  CREATED             STATUS              PORTS                    NAMES
edddb661e021        elementaryrobotics/atom      "tail -f /dev/null"      45 minutes ago      Up 45 minutes                                docker_walkthrough_atom_1
3f7df592f06e        elementaryrobotics/nucleus   "docker-entrypoint.s…"   About an hour ago   Up About an hour    6379/tcp                 docker_walkthrough_nucleus_1
```

Download the <a href="/docker-compose/docker-compose.yml" download>example `docker-compose.yml` file here</a>. Move the file into the same directory as the `Dockerfile` from the [Docker](#docker) section.

Now that we have a docker-compose file, we want to go ahead and launch the configuration that it specifies. We can do this with `docker-compose up -d` as shown to the right. After doing this, we can go ahead and list the running containers and see that we indeed have two running containers.

Note that the containers' name will be a combination of (1) the current folder name and (2) the service name. In newer versions of `docker-compose` there's also a hash value added onto the container name.

## Pulling up a shell

> <button class="copy-button" onclick='copyText(this, "docker exec -it atom /bin/bash")'>Copy</button> Enter shell in container

```shell_session
$ docker exec -it atom /bin/bash
root@edddb661e021:#
```

Now that we have our system up and launched, the most common thing we'll want to do is open up a shell in one of the containers. We'll go into the atom container so that we can test our first atom commands! Note that you'll need to replace `docker_walkthrough_atom_1` with your container name from `docker container list` as it will differ. You should typically be able to tab-complete the name which helps a bit.

## Creating an element

> <button class="copy-button" onclick='copyText(this, "python3")'>Copy</button> Launch `python3`

```shell_session
root@edddb661e021:# python3
Python 3.6.6 (default, Sep 12 2018, 18:26:19)
[GCC 8.0.1 20180414 (experimental) [trunk revision 259383]] on linux
Type "help", "copyright", "credits" or "license" for more information.
```
> <button class="copy-button" onclick='copyText(this, "from atom import Element")'>Copy</button> Import Atom

```shell_session
>>> from atom import Element
```
> <button class="copy-button" onclick='copyText(this, "my_element = Element(\"my_element\")")'>Copy</button> Create an element

```shell_session
>>> my_element = Element("my_element")
```

Now that we're in an active atom container we can use the python3 atom API to create an element.

## Using the Command-line Interface

> <button class="copy-button" onclick='copyText(this, "docker exec -it atom atom-cli")'>Copy</button> Launch Atom CLI

```shell_session
$ docker exec -it atom atom-cli
    ___  __________  __  ___   ____  _____
   /   |/_  __/ __ \/  |/  /  / __ \/ ___/
  / /| | / / / / / / /|_/ /  / / / /\__ \
 / ___ |/ / / /_/ / /  / /  / /_/ /___/ /
/_/  |_/_/  \____/_/  /_/   \____//____/



> list elements
my_element
atom-cli_edddb661e021
```

Atom also comes with a command-line interface  (CLI) that can be useful for testing/debugging. In a new terminal on your host computer (don't exit the terminal that created the element!) we can launch the `atom-cli` in the `atom` container. We can then ask it to list all elements that it sees, and lo and behold there's our new element! There's also an element listed for the CLI itself. This lets us know that the system is up and running and working.

## Shutting down

> <button class="copy-button" onclick='copyText(this, "docker-compose down -t 0 -v")'>Copy</button> Shut Down

```shell_session
$ docker-compose down -t 0 -v
```

Once we're done with the system that we launched we can go ahead and shut it all down. This will stop and remove all containers and shared volumes. The elements and data that we created will be lost.

## Cleaning Up

> <button class="copy-button" onclick="copyText(this, 'docker-compose down -t 0 -v --rmi all')">Copy</button> Cleaning up by deleting all the docker images

```shell_session
$ docker-compose down -t 0 -v --rmi all
```

To remove all the docker images downloaded by `docker-compose up` we could pass additional arguments to shut down command. Please follow this step only when you are finished running the demo as it will remove all of the docker containers that were downloaded from your system. This means that the next time you run the demo you will have to re-download all of the containers which might cause it to take slightly longer.
## Building

> Docker-Compose service built from Dockerfile

```yaml
  example:
    container_name: example
    build:
      context: .
      dockerfile: Dockerfile
    volumes:
      - type: volume
        source: shared
        target: /shared
        volume:
          nocopy: true
    command: "tail -f /dev/null"
```

> <button class="copy-button" onclick='copyText(this, "docker-compose build")'>Copy</button> Build everything in Docker-Compose file

```shell_session
$ docker-compose build

...

Successfully built 079202c53510
Successfully tagged docker_walkthrough_example:latest
nucleus uses an image, skipping
atom uses an image, skipping
```

> <button class="copy-button" onclick='copyText(this, "docker-compose up -d")'>Copy</button> Launch

```shell_session
$ docker-compose up -d
```

> <button class="copy-button" onclick='copyText(this, "docker exec -it docker_walkthrough_example_1 neofetch")'>Copy</button> Test `example` image

```shell_session
$ docker exec -it docker_walkthrough_example_1 neofetch

            .-/+oossssoo+/-.               root@1e34b88c2ebd
        `:+ssssssssssssssssss+:`           -----------------
      -+ssssssssssssssssssyyssss+-         OS: Ubuntu 18.04.1 LTS bionic x86_64
    .ossssssssssssssssssdMMMNysssso.       Host: XPS 15 9570
   /ssssssssssshdmmNNmmyNMMMMhssssss/      Kernel: 4.15.0-43-generic
  +ssssssssshmydMMMMMMMNddddyssssssss+     Uptime: 1 day, 3 hours, 33 mins
 /sssssssshNMMMyhhyyyyhmNMMMNhssssssss/    Packages: 255
.ssssssssdMMMNhsssssssssshNMMMdssssssss.   Shell: bash 4.4.19
+sssshhhyNMMNyssssssssssssyNMMMysssssss+   CPU: Intel i7-8750H (12) @ 4.100GHz
ossyNMMMNyMMhsssssssssssssshmmmhssssssso   Memory: 7438MiB / 31813MiB
ossyNMMMNyMMhsssssssssssssshmmmhssssssso
+sssshhhyNMMNyssssssssssssyNMMMysssssss+
.ssssssssdMMMNhsssssssssshNMMMdssssssss.
 /sssssssshNMMMyhhyyyyhdNMMMNhssssssss/
  +sssssssssdmydMMMMMMMMddddyssssssss+
   /ssssssssssshdmNNNNmyNMMMMhssssss/
    .ossssssssssssssssssdMMMNysssso.
      -+sssssssssssssssssyyyssss+-
        `:+ssssssssssssssssss+:`
            .-/+oossssoo+/-.
```

> <button class="copy-button" onclick='copyText(this, "docker-compose down -t 0 -v")'>Copy</button> Shut Down

```shell_session
$ docker-compose down -t 0 -v
```

So far we've only used Docker Compose to launch prebuilt images, but we can also use it to build from a dockerfile. In the `services` section of your docker-compose file, add the configuration at right.

Then, go ahead and run `docker-compose build` which tells docker-compose to build all of the images that it needs. It won't build the `atom` or `nucleus` since they come from prebuilt images, but it will go and recompile your `Dockerfile`.

We can then launch the compose configuration, test the example image by running the `neofetch` command from before, and shut everything down.

## Configuration Detail

> Basic element (built from Dockerfile) configuration

```yaml
  $element:
    container_name: $element
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

> Basic element (from image) configuration

```yaml
  $element:
    container_name: $element
    image: $image
    volumes:
      - type: volume
        source: shared
        target: /shared
        volume:
          nocopy: true
    depends_on:
      - "nucleus"
```

> Element with link between current folder and `/development` in container

```yaml
  $element:
    container_name: $element
    image: $image
    volumes:
      - type: volume
        source: shared
        target: /shared
        volume:
          nocopy: true
      - ".:/development"
    depends_on:
      - "nucleus"
```

> Element requiring USB

```yaml
  $element:
    container_name: $element
    image: $image
    volumes:
      - type: volume
        source: shared
        target: /shared
        volume:
          nocopy: true
    depends_on:
      - "nucleus"
    privileged: true
```

> Element requiring graphics support

```yaml
  $element:
    container_name: $element
    image: $image
    volumes:
      - type: volume
        source: shared
        target: /shared
        volume:
          nocopy: true
    depends_on:
      - "nucleus"
    environment:
      - "GRAPHICS=1"
    ports:
      - 6081:6080
```

For most elements built using the Atom OS, the default `docker-compose.yml` configuration (either built from Dockerfile or from an image), shown to the right, will suffice.

A quite useful configuration to add to your `docker-compose` is in the `volumes` section where you can set up a link between files on your host machine and a location in the container. This is super-useful for development/debug as you can make code changes locally and then test them in the container where all of the dependencies are installed.

Elements that want to show graphics will do so through two steps:

1. Set the `GRAPHICS` environment variable to `1`.
2. Map port `6080` within the container to some external port. Note that in the `ports` configuration the order is `HOST:CONTAINER`. The image will run a virtual display and forwards its graphics to `localhost:$HOST_PORT` which can then be seen in a browser. In the example, we've mapped the VNC on port `6080` in the container to `localhost:6081`.

Elements that use your computer's USB ports will need to have the `privileged` flag set.

<aside class="notice">
USB support is primarily tested/working on linux host computers for now, though USB 2.0 funcntionality is generally well-supported by Virtualbox. Using USB 3.0 functionality inside of a virtualbox container should theoretically work but has not been exhaustively tested on Windows and/or Mac.
</aside>

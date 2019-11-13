# Docker

The Atom OS is built atop docker. Docker gives us many benefits, with the primary ones being:

1. Ship code + all dependencies in a single package. No install required.
2. Multi-platform support. Write an element once and it will run on any OS.
3. Simple element versioning + deployment through dockerhub.
4. Deployment and monitoring through docker-compose.

This section will cover all of the general concepts of Docker as well as dive into detail in how we use it.

## Overview

Docker is a containerization technology. When you create an empty docker container it's similar to creating a brand-new computer with a fresh installation of linux. This is similar to installing a virtual machine, however Docker is much more performant than a virtual machine (VM). Rather than running an entirely virtual second operating system (OS), Docker shares the core of the linux operating system using a feature called `kernel namespaces`. This allows a single computer to have no issues running hundreds of docker containers while it would struggle to run more than a few VMs at once.

## Installation

> <button class="copy-button" onclick='copyText(this, "docker run hello-world")'>Copy</button> Test install

```shell_session
$ docker run hello-world

To generate this message, Docker took the following steps:
 1. The Docker client contacted the Docker daemon.
 2. The Docker daemon pulled the "hello-world" image from the Docker Hub.
    (amd64)
 3. The Docker daemon created a new container from that image which runs the
    executable that produces the output you are currently reading.
 4. The Docker daemon streamed that output to the Docker client, which sent it
    to your terminal.

To try something more ambitious, you can run an Ubuntu container with:
 $ docker run -it ubuntu bash

Share images, automate workflows, and more with a free Docker ID:
 https://hub.docker.com/

For more examples and ideas, visit:
 https://docs.docker.com/engine/userguide/
```

The official [Docker Site](https://docs.docker.com/install/) contains good instructions for installing docker on your system.  When running on Linux be sure to also follow these [post-install instructions](https://docs.docker.com/install/linux/linux-postinstall/). You'll want to install the docker community edition, with the exception of Docker Toolbox being currently recommeded for Windows and Mac users who wish to use Atom with USB-connected hardware such as the realsense camera.

<aside class="notice">
If you use Windows or Mac as your OS, and you plan on using hardware connected via USB (such as the realsense camera), it is recommended to install the <strong>Docker Toolbox</strong> version instead of (or alongside) the Docker CE version. See the <a href="https://docs.docker.com/toolbox/toolbox_install_windows">Docker Toolbox Install Instructions</a> instead of the general Docker install instructions.
</aside>

Once docker is installed on your machine you can test the installation by running the command at right and verifying that the printout looks as seen below it.

## Test a Container

> <button class="copy-button" onclick='copyText(this, "docker run -it ubuntu:18.04 /bin/bash")'>Copy</button> Launch Container

```shell_session
$ docker run -it ubuntu:18.04 /bin/bash
```

> <button class="copy-button" onclick='copyText(this, "cat /etc/os-release")'>Copy</button> Check OS Version

```shell_session
root@af7a6eb1b36f:/# cat /etc/os-release
NAME="Ubuntu"
VERSION="18.04.1 LTS (Bionic Beaver)"
ID=ubuntu
ID_LIKE=debian
PRETTY_NAME="Ubuntu 18.04.1 LTS"
VERSION_ID="18.04"
HOME_URL="https://www.ubuntu.com/"
SUPPORT_URL="https://help.ubuntu.com/"
BUG_REPORT_URL="https://bugs.launchpad.net/ubuntu/"
PRIVACY_POLICY_URL="https://www.ubuntu.com/legal/terms-and-policies/privacy-policy"
VERSION_CODENAME=bionic
UBUNTU_CODENAME=bionic
```

> <button class="copy-button" onclick='copyText(this, "python3")'>Copy</button> Try to run Python3

```
root@af7a6eb1b36f:/# python3
bash: python3: command not found
```

Now that we have docker installed, we want to go ahead and take it for a spin. We'll launch a container based off of Ubuntu 18.04 and bring up a basic terminal in the container. We can then check the version of Linux we're running with `cat /etc/os-release` and we see that indeed we are running Ubuntu 18.04!

Now, let's try to run Python3 and play around... and we see that Python3 isn't installed! Ubuntu 18.04 doesn't come with Python3 installed, so we'll go ahead and make our own Docker image that's based off of Ubuntu 18.04 but contains Python3.

## Dockerfile

> Example Dockerfile

```
FROM ubuntu:18.04

#
# Install anything needed in the system
#
RUN apt-get update -y
RUN apt-get install -y --no-install-recommends apt-utils
RUN apt-get install -y git python3-minimal python3-pip
```

> <button class="copy-button" onclick='copyText(this, "docker build -f Dockerfile -t my_image .")'>Copy</button> Build Dockerfile

```shell_session
$ docker build -f Dockerfile -t my_image .

...

Successfully built a406b2ba741b
Successfully tagged my_image:latest
```

To build a Docker container which supports Python3, we begin with the `Dockerfile` which specifies which version of linux to use and what to install in the container. Generally this will be your code and any of the dependencies that it requires.

An example `Dockerfile` can be seen at right and can be downloaded <a href="/docker/Dockerfile" download>here</a>.

This `Dockerfile` does the following:

1. Starts from the [base Ubuntu 18.04 image published on Dockerhub](https://hub.docker.com/_/ubuntu/)
2. Runs `apt-get update` to update everything already installed on the system.
3. Installs a few other things such as git and python

Once we have this dockerfile we can use the command at right to build it into an image named `my_image`. After a few minutes the command should complete and you should see the success messages at right.

## List Images

> <button class="copy-button" onclick='copyText(this, "docker image list")'>Copy</button> List all images

```shell_session
$ docker image list

REPOSITORY                                          TAG                                                       IMAGE ID            CREATED             SIZE
my_image                                            latest                                                    a406b2ba741b        2 minutes ago      541MB
...
```

Once we've built our Dockerfile into an image we can go ahead and list the images that we've built on our system. You should see that we just recently built the `my_image` image.

## Launch Container

> <button class="copy-button" onclick='copyText(this, "docker run --name my_container -it my_image /bin/bash")'>Copy</button> Launch Container

```shell_session
$ docker run --name my_container -it my_image /bin/bash
root@5e97fa9b1025:/#
```

With a built image we can go ahead and launch a **container** from that image. A container is just an instance of an image. To launch a container we use `docker run`. The command at right does the following:

1. Creates a new container from image `my_image`
2. Runs a new process, `/bin/bash` in the new container. This allows you to pull up a command line in the new container.

Once you've run the above command you should see that you're now logged in as root within the container. Each container has a unique ID so that you can address them individually. Here, the container ID is `5e97fa9b1025`. We'll address the container by its name, though, `my_container`, which is much easier than needing to know/remember the container ID.

## Run Python Program

> <button class="copy-button" onclick='copyText(this, "python3")'>Copy</button> Launch Python3

```shell_session
root@5e97fa9b1025:/# python3
Python 3.6.7 (default, Oct 22 2018, 11:32:17)
[GCC 8.2.0] on linux
Type "help", "copyright", "credits" or "license" for more information.
>>>
```
> <button class="copy-button" onclick='copyText(this, "print (\"Hello, World\")")'>Copy</button> Print `Hello, World`

```shell_session
>>> print ("Hello, World")
Hello, World
```
> <button class="copy-button" onclick='copyText(this, "exit()")'>Copy</button> Exit Python3 session

```shell_session
>>> exit()
root@5e97fa9b1025:/#
```

Now that you are in the container, you can run a simple Python3 program using the version of Python3 that we installed. After running the exit() command you will exit the python interpreter but still be in the container which you launched.

## Add a file

> <button class="copy-button" onclick='copyText(this, "echo \"foo\" &gt bar.txt")'>Copy</button> Write `foo` to `bar.txt`

```shell_session
root@5e97fa9b1025:/# echo "foo" > bar.txt
```

> <button class="copy-button" onclick='copyText(this, "cat bar.txt")'>Copy</button> Read back `bar.txt`

```shell_session
root@5e97fa9b1025:/# cat bar.txt
foo
```

Files in the container work just like files on your main computer. We'll create this test file `bar.txt` and put the word `foo` in it. We'll then read back the contents of the file using the `cat` command.

## List Containers

> <button class="copy-button" onclick='copyText(this, "docker container list")'>Copy</button> List all containers

```shell_session
$ docker container list
CONTAINER ID        IMAGE               COMMAND                  CREATED             STATUS              PORTS                    NAMES
5e97fa9b1025        my_image            "/bin/bash"              4 minutes ago       Up 4 minutes                                 compassionate_hawking
```

Now, in a new terminal on your host computer (not in the container) you can list the currently running containers. You'll see that there's just the one container, with an ID that matches the one you see on your command prompt that's been created from the `my_image` image.

## Exit Container

> <button class="copy-button" onclick='copyText(this, "exit")'>Copy</button> Exit container

```shell_session
root@5e97fa9b1025:/# exit
$
```

> <button class="copy-button" onclick='copyText(this, "docker container list")'>Copy</button> List running containers

```shell_session
$ docker container list
CONTAINER ID        IMAGE               COMMAND                  CREATED             STATUS              PORTS                    NAMES
```

> <button class="copy-button" onclick='copyText(this, "docker container list -a")'>Copy</button> List _all_ containers

```shell_session
$ docker container list -a
CONTAINER ID        IMAGE                                                                            COMMAND                   CREATED             STATUS                          PORTS                    NAMES
5e97fa9b1025        my_image                                                                         "/bin/bash"               8 minutes ago       Exited (0) About a minute ago                            compassionate_hawking
```

In your container, run the `exit` command to finish your `/bin/bash` process. You will see that after this is completed you'll be back in the terminal on your host computer. If you run another `docker container list` command you'll see that there are no active containers. However, if you run the `docker container list -a` command you'll see that your container is still there, it's just not running. This is an important distinction to make since your container contains all of the modifications that you've made to the base image, `my_image`.

## Container Modifications

> <button class="copy-button" onclick='copyText(this, "docker run --name my_container_2 -it my_image /bin/bash")'>Copy</button> Launch new container and check for `bar.txt`

```shell_session
$ docker run --name my_container_2 -it my_image /bin/bash
root@75566ed7baa3:/# cat bar.txt
cat: bar.txt: No such file or directory
```

> <button class="copy-button" onclick='copyText(this, "docker start -i my_container")'>Copy</button> Run same command in existing, original container

```shell_session
$ docker start -i my_container
root@5e97fa9b1025:/# cat bar.txt
foo
```

If we were to launch a new container from the same original image and check for the `bar.txt` file, we wouldn't find it. This is because each time we create a new container from the original image it doesn't contain any of the modifications we've made to other containers. Each container is isolated, the changes made in it don't affect the other images.

However, if we were to restart the original container we created, we'd see that our `bar.txt` file is still there, alive and well!

## Execute command in running container

> <button class="copy-button" onclick='copyText(this, "docker exec -it my_container cat bar.txt")'>Copy</button> Read bar.txt using `docker exec`

```shell_session
$ docker exec -it my_container cat bar.txt
foo
$
```

> <button class="copy-button" onclick='copyText(this, "docker exec -it my_container /bin/bash")'>Copy</button> Enter shell in running container

```shell_session
$ docker exec -it my_container /bin/bash
root@5e97fa9b1025:/#
```

One final concept that's important to understand about containers is that, as long as they're running, we can be executing as many commands in them as we'd like. This is just like on your host computer where you can run as many processes/applications as you'd like. In order to execute a command in a running container, we use `docker exec`. In a new terminal window on your host computer, run the command at right, making sure your original container with `bar.txt` is still up and running from the `docker start` command in the previous section. This `docker exec` command will go into the running container, run the `cat bar.txt` command, and then exit. This type of command is commonly used to enter a shell session in a running container.

## Image Tags

> <button class="copy-button" onclick='copyText(this, "docker tag my_image my_image:v1")'>Copy</button> Tag current image as V1

```shell_session
$ docker tag my_image my_image:v1
```

> <button class="copy-button" onclick='copyText(this, "RUN apt-get install -y neofetch")'>Copy</button> Add `neofetch` to Dockerfile

```
FROM ubuntu:18.04

#
# Install anything needed in the system
#
RUN apt-get update -y
RUN apt-get install -y --no-install-recommends apt-utils
RUN apt-get install -y git python3-minimal python3-pip
RUN apt-get install -y neofetch
```

> <button class="copy-button" onclick='copyText(this, "docker build -f Dockerfile -t my_image .")'>Copy</button> Rebuild Dockerfile

```shell_session
$ docker build -f Dockerfile -t my_image .

...

Successfully built 6c7b69898ec3
Successfully tagged my_image:latest
```

> <button class="copy-button" onclick='copyText(this, "docker tag my_image my_image:v2")'>Copy</button> Tag current image as v2

```shell_session
$ docker tag my_image my_image:v2
```

> <button class="copy-button" onclick='copyText(this, "docker run -it my_image:v1 neofetch")'>Copy</button> Try to run neofetch in v1 container

```shell_session
$ docker run -it my_image:v1 neofetch
docker: Error response from daemon: OCI runtime create failed: container_linux.go:348: starting container process caused "exec: \"neofetch\": executable file not found in $PATH": unknown.
```

> <button class="copy-button" onclick='copyText(this, "docker run -it my_image:v2 neofetch")'>Copy</button> Try to run neofetch in v2 container

```shell_session
$ docker run -it my_image:v2 neofetch
            .-/+oossssoo+/-.               root@3c04e7192d8c
        `:+ssssssssssssssssss+:`           -----------------
      -+ssssssssssssssssssyyssss+-         OS: Ubuntu 18.04.1 LTS bionic x86_64
    .ossssssssssssssssssdMMMNysssso.       Host: XPS 15 9570
   /ssssssssssshdmmNNmmyNMMMMhssssss/      Kernel: 4.15.0-43-generic
  +ssssssssshmydMMMMMMMNddddyssssssss+     Uptime: 1 day, 34 mins
 /sssssssshNMMMyhhyyyyhmNMMMNhssssssss/    Packages: 255
.ssssssssdMMMNhsssssssssshNMMMdssssssss.   Shell: bash 4.4.19
+sssshhhyNMMNyssssssssssssyNMMMysssssss+   CPU: Intel i7-8750H (12) @ 4.100GHz
ossyNMMMNyMMhsssssssssssssshmmmhssssssso   Memory: 6389MiB / 31813MiB
ossyNMMMNyMMhsssssssssssssshmmmhsssssssodocker rm -f $(docker ps -aq)
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

Tags are how we keep track of different versions of images. Let's say we want to modify our Dockerfile to add the line at the bottom that installs a program called `neofetch`. We first want to take our existing image and tag it as something more human-legible than its image hash, `a406b2ba741b` (note: your hash will differ). We can use the `docker tag` command to do this. This command takes two arguments where the first argument is the existing image hash/tag and the second is the new tag we want to create.

In our previous examples where we used `docker run -it my_image /bin/bash`, docker assumed to use the tag `latest` for `my_image`. This command is identical to running `docker run -it my_image:latest /bin/bash`

Now, we want to add the `neofetch` program to the Dockerfile, rebuild, and tag the image as `my_image:v2`.

Finally, we can try to run the `neofetch` command in both `v1` and `v2` containers and see that in the `v1` container `neofetch` isn't installed while in the `v2` container it is and it prints out a pretty logo and info about the OS. Note that the `v2` command can be re-run without the `v2` tag and Docker will assume `latest` and will still use the `v2` image.

## Docker Hub

> <button class="copy-button" onclick='copyText(this, "docker login")'>Copy</button> Log into Docker Hub Account

```shell_session
$ docker login
```

> <button class="copy-button" onclick='copyText(this, "docker tag my_image:latest $MY_DOCKERHUB_ACCOUNT/my_image:latest")'>Copy</button> Tag image under Docker Hub Account

```shell_session
$ docker tag my_image:latest $MY_DOCKERHUB_ACCOUNT/my_image:latest
```

> <button class="copy-button" onclick='copyText(this, "docker push $MY_DOCKERHUB_ACCOUNT/my_image:latest")'>Copy</button> Push image to Docker Hub

```shell_session
$ docker push $MY_DOCKERHUB_ACCOUNT/my_image:latest
```

Docker also has a cloud service, confusingly called "Docker Hub" in some places and "Docker Cloud" in others. Hopefully one day they'll get their messaging straight, but for all intents and purposes they can be considered to be the same thing.

Docker hub functions very similarly to github in the concept that it has repositories that you can push your built images and tags to so that others can also access them.

First, [create an account on Docker Hub](https://hub.docker.com/signup) if you don't already have one.

Once you've created an account, we can go ahead and push some of our images to it. The first thing we want to do is log in.

Once logged in, we want to re-tag our `my_image` image to one that lives within our Docker Hub account. We do this by adding `$MY_DOCKERHUB_ACCOUNT/` to the beginning of the image name. This tells docker and Docker Hub which user/organization the image belongs to. For example, if we wanted to push this image to the `elementaryrobotics` Docker Hub organization, we'd tag it as `elementaryrobotics/my_image`. For the command at right, use your Docker Hub account name.

Once you've re-tagged the image we can go ahead and push it to Docker Hub. Once this completes (it might take a minute or two), you should be able to navigate to the "Repositories" tab in Docker Hub and see that you have a new repository under your account with repository name `my_image` and a single tag `latest`. This repository is by default public, so now anyone in the world could run a container from your image using `docker run -it $MY_DOCKERHUB_ACCOUNT/my_image`! This is pretty cool in that you've now deployed your first container, but you'll likely want to delete it. You can do this in the settings for the repository.

## Useful Commands

> <button class="copy-button" onclick='copyText(this, "docker container list")'>Copy</button> List all containers

```shell_session
$ docker container list
```
> <button class="copy-button" onclick='copyText(this, "docker image list")'>Copy</button> List all images

```shell_session
$ docker image list
```

> <button class="copy-button" onclick='copyText(this, "docker tag $IMAGE_HASH $IMAGE_NAME:$IMAGE_TAG")'>Copy</button> Tag an image

```shell_session
$ docker tag $IMAGE_HASH $IMAGE_NAME:$IMAGE_TAG
```

> <button class="copy-button" onclick='copyText(this, "docker build -t $SOME_TAG .")'>Copy</button> Build an image from a Dockerfile named `Dockerfile`

```shell_session
$ docker build -t $SOME_TAG .
```

> <button class="copy-button" onclick='copyText(this, "docker build -t $SOME_TAG -f $DOCKERFILE_NAME .")'>Copy</button> Build and image from an arbitrarily named Dockerfile

```shell_session
$ docker build -t $SOME_TAG -f $DOCKERFILE_NAME .
```

> <button class="copy-button" onclick='copyText(this, "docker system prune")'>Copy</button> Remove all unused objects (stopped containers, dangling images, etc.)

```shell_session
$ docker system prune
```
> <button class="copy-button" onclick='copyText(this, "docker run -it $IMAGE_NAME")'>Copy</button> Launch a container running its default command

```shell_session
$ docker run -it $IMAGE_NAME
```

> <button class="copy-button" onclick='copyText(this, "docker run -it $IMAGE_NAME $COMMAND")'>Copy</button> Launch a container and override the command

```shell_session
$ docker run -it $IMAGE_NAME $COMMAND
```

> <button class="copy-button" onclick='copyText(this, "docker exec -it $CONTAINER_NAME $COMMAND")'>Copy</button> Execute a command in a running container

```shell_session
$ docker exec -it $CONTAINER_NAME $COMMAND
```

> <button class="copy-button" onclick='copyText(this, "docker exec -it $CONTAINER_NAME /bin/bash")'>Copy</button> Launch a shell in a running container (note: container must support bash)

```shell_session
$ docker exec -it $CONTAINER_NAME /bin/bash
```

As you're using docker, there are a fair amount of useful commands. Some of the most commonly used commands are included here. Feel free to add/update this list!

## Docker Toolbox

If you're running Mac or Windows and wish to use USB-connected hardware such as the realsense camera, you'll want to use Docker Toolbox instead of Docker CE. This is necessary to use USB-connected peripherals with Atom.

When you install Docker Toolbox, [Virtualbox](https://www.virtualbox.org/wiki/Downloads) will also be installed on your machine. Docker then works by booting up a basic linux virtual machine (VM) in Virtualbox and executing all of the docker commands in that VM. It's recommended to configure a few things in order to get the best performace.


### Hard Disk Size

The default docker machine that's created with Docker Toolbox only has a 20GB drive associated with it. You'll likely want to allocate more space. Note that this allocation won't actually remove this amount of space from your computer immediately, it'll just allow the docker VM to grow to this size before hitting an error. To delete the default docker machine and re-create it with a larger 100GB disk:

`docker-machine rm default`


`docker-machine create -d virtualbox --virtualbox-disk-size "100000" default`

### RAM

The default docker VM only allocates 1GB of RAM to the machine. It's recommended to give it 8 or 16GB, though it will work well enough on 1.

### Line Endings

Windows and Linux use different line endings. We use docker-compose to mount files between your host OS and the docker container, and if those files have CRLF (Windows) line endings when they're mounted into the container we're going to have a bad time. As such, it's recommended to configure your git repo to peg line endings on particular files (such as shell scripts). See [some docs here](https://help.github.com/en/articles/dealing-with-line-endings).

### Ports

We use docker-compose to map ports between the docker container and your host computer so that you can see web pages/graphics. For most of the documentation you'll see that we use `localhost:X` or `127.0.0.1:X` to access a port. When using Docker Toolbox, instead of `localhost` you need to use the IP address of the docker VM, `192.168.99.100`, instead of `localhost`. If you go through the [Quickstart](#getting-started-with-atom-os), you'll notice that the links to view the graphics don't work by default because of this. Simply replace `localhost` with `192.168.99.100` in the URL bar of your browser and you should be good to go.

### Mounting Folders

In order to get folder mounts to work between Windows and the docker machine, you need to set `COMPOSE_CONVERT_WINDOWS_PATHS=1` as an environment variable in your shell.

### USB Forwarding

In order for USB-connected hardware to work in Virtualbox we'll need to forward the USB device. This can be done pretty easily in Virtualbox. The docker VM must not be running while doing this config. To stop the machine, you can run

`docker-machine stop`

1. Download the Virtualbox Extension Pack to enable USB support. You'll need to go to Help->About Virtualbox to check which version you have installed. As of 2/27/19 Docker Toolbox for Windows came with 5.2.8. Then, go to [the download page](https://www.virtualbox.org/wiki/Download_Old_Builds_5_2) to download the extension pack version that matches your installed version. Download the file.
2. Add the extension pack by going to File->Preferences->Extensions and then selecting
the file you downloaded. You should then see a message letting you know that the extension pack was successfully installed.
3. Right click on the `default` VM and then select `Settings`.
4. Set up the desired USB controller and add a filter for the devices you want to forward by clicking on the plus button and choosing your desired device.

# Atom SDK [![CircleCI](https://circleci.com/gh/elementary-robotics/atom.svg?style=svg&circle-token=9b24e4298d3b4c31471509eeb5e6a61a357aba9c)](https://circleci.com/gh/elementary-robotics/atom)

## Overview

This repo contains the following:

1. Docker files to create `atom-base`, `atom` and `nucleus` docker images
2. Source code for all `atom` language libraries
3. Examples for how to use `atom` in creating elements and apps.
4. Source documentation for the [Atom Docs Site](https://atomdocs.io)
5. A [Wiki Page](https://github.com/elementary-robotics/atom/wiki/Elements) which contains links to github and docker repos for all known elements that have been released.

## Documentation

Please see [The Atom Documentation](https://atomdocs.io) for a comprehensive set of docs that cover the following:

1. Design goals and SDK features
2. The full Atom specification
3. Tutorials on how to use Atom
4. Tutorials on Docker and Docker-Compose
5. Documentation for elements that have been added to the Atom ecosystem.

The documentation is rebuilt nightly on CircleCI and, when built, pulls the latest documentation from each element that it's linked to. To add an element to the documentation build, simply add the line below to the docs [Dockerfile](doc/Dockerfile)
```
COPY --from=$dockerhub_org/$dockerhub_repo /code/README.md /elements_docs/$unique_name.md
```

Please help us keep the documentation up-to-date and accurate! You'll find a [`docker-compose`](doc/docker-compose.yml) file in the `doc` folder that will build and launch a local copy of the docs server that can be used to develop and test documentation updates. Once launched, the server can be accessed at [`localhost:4567`](http://localhost:4567).

## Redis Talks and Slides

Please see the [Redis Talks and Slides](https://github.com/elementary-robotics/atom/wiki/Redis-Talks-and-Slides) page of the wiki for video and slides from the talks that have been given on Atom at various Redis conferences.

## Development

In this repository is a `docker-compose` file that can build and launch both
the nucleus image and the atom image.

### Initializing Submodules

Before beginning, you'll want to initialize all submodules
```
git submodule update --init --recursive
```

### Building Containers

In order to build the container, use `docker-compose`
```
docker-compose build
```

This will build both the nucleus image and the atom image and will create
the following tags:
```
dev_atom:latest
dev_nucleus:latest
```

### Developing

It's best to do all developmental testing and building within
the docker containers. The easiest way to do this is to mount the
current directory into the latest atom image that's been built and
continue development in there until you're ready to rebuild. To do
this:
```
docker-compose up -d
docker exec -it dev_atom bash
```

This will open up a shell within the most recent dev_atom you've built (or you can specify a tag or even the atom-base container if
you'd like) and mount your current source folder in `/development`.
From there you can compile/run/test your code.

#### Debugging with gdb

If you want to be able to run gdb in docker, add the below
to your docker command:
```
--cap-add=SYS_PTRACE
```

### Testing

In order to test the images, we'll again use `docker-compose` to launch
containers of the images we built. This will also create a shared `tmpfs`
volume that the containers will share in order to use the redis unix socket
as opposed to using redis via TCP. This should theoretically give us better
performance.

In order to launch the test container you can run:
```
docker-compose up -d
```

This will launch the necessary containers and make the shared volume and
background everything. Then, to run the tests you care about you can run:
```
docker exec -it -w ${COMMAND_WORKING_DIRECTORY} dev_atom ${TEST_COMMAND}
```

An example of the above, to run the python unit tests is
```
docker exec -it -w /atom/languages/python dev_atom pytest
```

After running the tests, to bring down the environment you can run:
```
docker-compose down -v
```
This will shut down the containers, remove them and also take down the
shared volume that was created for the redis socket.

### Continuous Integration (CI) and Deployment

Upon pushing to github, a build will be started on CircleCI. This will build
both the nucleus and atom images and will run any implemented unit tests
against them.

If the build and tests pass, the images will be pushed to dockerhub. Depending
on the branch, they will be tagged as so:

| branch | tag |
|--------|-----|
| `master` | master-${CI_BUILD}-${COMMIT_HASH} |
| Non-`master` | development-${CI_BUILD}-${COMMIT_HASH} |

When `master` is built, the images will also be tagged and pushed as `latest`.

### Configuring CircleCI

If you've forked this repository and/or made an element and want to set up the build chain on CircleCI (recommended), please follow the steps below:

1. Push your repo to github
2. Log into CircleCI using your github account and start building the process on CircleCI. The first build will likely fail since there are a few things you need to configure.
3. Add the following envirnoment variables to your CircleCI build. Note that some of these variables are needed only to rebuild the `atom` repo and some are needed for any element you want to build.

| Variable | Required for which builds? | Description |
|----------|----------------------------|-------------|
| `DOCKERHUB_ORG` | all | Organization you want your docker containers pushed to |
| `DOCKERHUB_USER` | all | Username of the account with permissions to push to your build repos. It's recommended to make a separate user for this so you don't risk exposing your personal credentials |
| `DOCKERHUB_PASSWORD` | all | Password for `DOCKERHUB_USER`. Will be injected into the build and used to login. |
| `DOCKERHUB_REPO` | elements only | Which repo in `DOCKERHUB_ORG` to push to |
| `DOCKERHUB_ATOM_REPO` | atom repo only | If you're rebuilding atom, which repo to put the atom container into |
| `DOCKERHUB_NUCLEUS_REPO` | atom repo only | If you're rebuilding atom, which repo to put the nucleus container into |
| `DOCKERHUB_DOCS_REPO` | atom repo only | If you're rebuilding atom, which repo to put the built docs container into |
| `DOCKERHUB_ATOM_CUDA_10_REPO` | atom repo only | If you're rebuilding atom, which repo to put the built atom container with CUDA 10 support into |
| `DOCKERHUB_ATOM_CUDA_9_REPO` | atom repo only  | If you're rebuilding atom, which repo to put the built atom container with CUDA 9 support into |
| `HEROKU_API_KEY` | atom repo only | If you're rebuilding atom, secret API key to use to push the docs container to heroku for deployment. You can host your own version of the docs site pretty easily by making a new heroku app and pushing the docs container to it using our deploy script |
| `HEROKU_APP_NAME` | atom repo only | Name of the heroku app to which you're deploying the docs container |

4. If you're only interested and not running any deploy steps, simply remove the `Docker Login` and `Docker tag and push` steps from the [circleci file](.circleci/config.yml) and you don't need to configure any of the above.

## Specification

The `atom` language clients in the `languages` folder all implement the `atom`
specification. See the [documents](https://atomdocs.io)
for more information on the spec.

## Creating a new language client

To create a new language client, you must do the following:

1. Add a folder in `languages` for the new language client
2. Implement the `atom` spec atop a redis client for the language.
3. Modify `dockerfile-atom-base` to compile `protobuf` for the language.
4. Modify `dockerfile-atom` to compile/install the language into the
docker image. You will also need to bump the tag for `dockerfile-atom-base` in
this file.
5. Write a `README` on how to use the language client
6. Write unit tests for the language client
7. Modify `.circleci/config.yml` to run the unit tests for the language client.
8. Open a PR with the above changes.

## Creating an app or element

### Overview

An element creator who simply uses libraries should never have to modify this
repo. Each element should be placed in its own repository that's been
initialized to the contents of the `template` folder. In the `template` folder
you'll find the following:

1. `.circleci` folder with config for automated build/deployment
2. `Dockerfile` that imports from the most recent `atom` image
3. `docker-compose.yml` which specifies the dependencies of the element or app.
This dependency tree will contain the nucleus and all of the other elements
that need to be launched in order for the new app/element to be launched.
4. `README` example README.
5. `launch.sh`. This is expected to be filled out with the command(s) to launch
your element/app. An example of what could be put in this file would be:
```
!/bin/bash

python3 my_element.py
```

## Base Dockerfile

The `atom` dockerfile is developed atop the `atom-base` dockerfile which
isn't built in CI. This dockerfile contains things which are more static such
as basic ubuntu installs using `apt-get` and the installation of protobuf.
This saves us time on our CI rebuild changes. The process for updating the
`atom-base` docker container if needed are:

1. Modify the `atom-base` dockerfile and commit the changes. You MUST commit
the changes since the tag will depend on the git hash.
2. Rebuild the `atom-base` image using:
```
docker build --no-cache -f Dockerfile-atom-base -t elementaryrobotics/atom-base:"$(git rev-parse HEAD)" .
```
3. Push the new `atom-base` image to `elementaryrobotics/atom-base`
```
docker push elementaryrobotics/atom-base:"$(git rev-parse HEAD)"
```
4. Bump the dependency in `Dockerfile-atom` to use the new tag from `atom-base`.

### Cuda support

We also build base versions of the dockerfile for cuda 9 and 10. To build for these versions, pass `BASE_IMAGE=$X` the following to the above docker build command:

| Cuda Version | Dockerhub repo | Base Image |
|--------------|----------------|------------|
| 10 | `atom-cuda-10-base` | `nvidia/cuda:10.0-cudnn7-devel-ubuntu18.04` |
| 9 | `atom-cuda-9-base` | `nvidia/cuda:9.2-cudnn7-devel-ubuntu18.04` |

An example to build for Cuda 10 would be:
```
docker build --no-cache -f Dockerfile-atom-base -t elementaryrobotics/atom-cuda-10-base:"$(git rev-parse HEAD)" --build-arg BASE_IMAGE=nvidia/cuda:10.0-cudnn7-devel-ubuntu18.04 .
```

And for cuda 9:
```
docker build --no-cache -f Dockerfile-atom-base -t elementaryrobotics/atom-cuda-9-base:"$(git rev-parse HEAD)" --build-arg BASE_IMAGE=nvidia/cuda:9.2-cudnn7-devel-ubuntu18.04 .
```

### Graphics Support

In order to make the graphics more portable, `atom` ships with an openGL-enabled VNC, NoVNC, that by default renders to port `6080`. This is implemented largely based off of [docker-opengl](https://github.com/thewtex/docker-opengl), which is also included as a submodule in this repo. In order to launch the screen server and view it:

1. If you're using the `launch.sh` template then you'll notice you can just set the `GRAPHICS` environment variable. If you're not using this template, the server can be launched with the command:
```
/usr/bin/supervisord -c /etc/supervisor/supervisord.conf
```
2. Remap the port `6080` to be exposed on your system. This can be done in the `docker-compose` or by passing the `-p` flag when using `docker run`.
3. Visit `localhost:$port` in your browser, where `$port` corresponds to the port you mapped `6080` to using docker.

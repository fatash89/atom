# Atom SDK [![CircleCI](https://circleci.com/gh/elementary-robotics/atom.svg?style=svg&circle-token=9b24e4298d3b4c31471509eeb5e6a61a357aba9c)](https://circleci.com/gh/elementary-robotics/atom)

## Overview

This repo contains the following:

1. Docker files to create `atom` and `nucleus` docker images
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
continue development in there until you're ready to rebuild.
For more details refer to [Atom's docker-compose docs](https://github.com/elementary-robotics/atom/blob/26ff146fb23e12071a2743e12bc71c15023d23b3/doc/source/includes/docker-compose.md
).

For example, mount your local Atom source directory to `/development`
in the atom image by adding a volume entry to the atom service in the docker-compose file:

```yaml
    volumes:
      - ".:/development"
```

The recommended workflow for development is then to execute:

```
docker-compose up -d
docker exec -it dev_atom bash
```

This will open up a shell within the most recent dev_atom you've built (or you can specify a tag or an atom-test container if
you'd like) and mount your current source folder in `/development`.
Then you may compile/run code (such as unit tests of a new feature)
from within the container while editing the source in a different shell session running outside of the container.
Note that typically you'll need to restart/reinstall the service that you're developing from within the container
in order for your code edits to take effect (For example, run `python3 setup.py install` between edits to the Python3 language client).

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
| `master` | master-${CIRCLE_BUILD_NUM} |
| Non-`master` | development-${CIRCLE_BUILD_NUM} |

When `master` is built, the images will also be tagged and pushed as `latest`.

### Configuring CircleCI

#### For a generic element

If you're looking for the general CircleCI config docs for elements, see [the CircleCI README](.circleci/README.md)

#### To build this repo

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
| `DOCKERHUB_ATOM_OPENGL_REPO` | atom repo only | If you're rebuilding atom, which repo to put the built atom container with OpenGL support into |
| `DOCKERHUB_ATOM_CUDA_10_REPO` | atom repo only | If you're rebuilding atom, which repo to put the built atom container with CUDA 10 support into |
| `DOCKERHUB_ATOM_OPENGL_CUDA_10_REPO` | atom repo only | If you're rebuilding atom, which repo to put the built atom container with OpenGL + CUDA 10 support into |
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
3. Modify `Dockerfile-atom` to compile `msgpack` for the language in the `base` stage.
4. Modify `Dockerfile-atom` to compile/install the language into the
docker image in the `base` stage.
5. Copy over the installed libraries in `prod` stage of `Dockerfile-atom`.
6. Write a `README` on how to use the language client
7. Write unit tests for the language client
8. Modify `.circleci/config.yml` to run the unit tests for the language client.
9. Open a PR with the above changes.

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

## Atom Dockerfile

The `atom` Dockerfile is a multi-stage Dockerfile, meaning it contains multiple build stages that result in
different images that may be built from each other. Currently the `atom` build has the following stages:

1. `base` - this image is used to build and install any production dependencies.
2. `prod` - this image is built from the base OS image, and installed production dependencies are copied in
from the `base` stage. This prevents build dependencies from taking up space in our production image. Additionally,
since the `prod` stage is not built directly from the `base` stage, changes in the `base` stage will not invalidate
use of docker layer caching in our build process of the `prod` stage.
3. `test` - this image is built from the `prod` image and adds in test dependencies.
4. `graphics` - this image is built from the `prod` image and adds in graphics dependencies for VNC/noVNC.

To build a specific stage of `atom`, use the `--target` option with `docker build` and an appropriate tag:
```
docker build --no-cache -f Dockerfile-atom -t elementaryrobotics/atom-test:dev --target=test .
```

The `prod` stage will be pushed to dockerhub through the CircleCI build process as just `atom`, while the `test`
stage will be pushed as `atom-test`.

### OpenGL and Cuda support

We also build base versions of the dockerfile for OpenGL and cuda / cuDNN. To build for these versions, pass `BASE_IMAGE=$X` to the above docker build command:

| Cuda Version | cuDNN Version | Dockerhub repo | Base Image |
|--------------|--------------|----------------|------------|
| - | - | `atom-opengl-base` | `nvidia/opengl:1.0-glvnd-runtime-ubuntu18.04` |
| 10.0 | 7.6.4.38 | `atom-cuda-10-base` | `nvidia/cuda:10.0-cudnn7-runtime-ubuntu18.04` |
| 10.0 | 7.6.5.32 | `atom-opengl-cuda-10-base` | custom, see below\* |

An example to build for Cuda 10 / cudnn would be:
```
docker build --no-cache -f Dockerfile-atom -t elementaryrobotics/atom-cuda-10-base:dev --target=prod --build-arg BASE_IMAGE=nvidia/cuda:10.0-cudnn7-runtime-ubuntu18.04 .
```

Any image using OpenGL should be built with `--target=graphics` so that the graphics dependencies are available in the image.
The combined OpenGL/cuda/cuDNN base image can be built in two steps, with the first step utilizing the included dockerfile `Dockerfile-install-cudnn` (modify this file for cuDNN version updates):
```
docker build --no-cache -f Dockerfile-install-cudnn -t opengl-cuda-10-base .
docker build --no-cache -f Dockerfile-atom -t elementaryrobotics/atom-opengl-cuda-10-base:dev --target=graphics --build-arg BASE_IMAGE=opengl-cuda-10-base .
```

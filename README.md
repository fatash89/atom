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

### Quickstart

It's best to do all developmental testing and building within
the docker containers. The easiest way to do this is to mount the
current directory into the latest atom image that's been built and
develop from there.

This is done automatically in the [`docker-compose.yml`](docker-compose.yml)
supplied in this repo through code similar to the below.

```yaml
    volumes:
      - ".:/atom"
```

The recommended workflow for development is then to execute:

```
docker-compose pull
docker-compose up -d
docker exec -it atom bash
```

This will open up a shell within the most recent build of atom. This repo
will be mounted into the container at `/atom` and from there you can test
changes to the code.

### Rebuilding the Atom Docker Images

If you'd prefer to develop by building the atom Docker containers, this
can be done fairly easily as well by using the [`docker-compose-dev.yml`](docker-compose-dev.yml)
compose file.

```
docker-compose build
docker-compose up -d
docker exec -it atom bash
```

Everything is the same as in the quickstart, except for a few things:
1. The `atom` container will have testing dependencies installed in order to
run `pytest` `googletest`, etc.
2. The `atom` container will be built from the atom client source in this repo.

### Testing

In order to run tests, you'll want to develop with the "Rebuilding the Docker
Images" method as described above. Once you're in the `atom` container, you
can run the following tests:

| Test | Working Directory | Command |
|------|-------------------|---------|
| Python Unit Tests | `/atom/languages/python/tests` | `pytest` |
| C Unit Tests | `/atom/languages/c` | `make -j8 test` |
| C++ Unit Tests | `/atom/languages/cpp` | `make -j8 test` |
| C++ Memory Check | `/atom/languages/cpp` | `valgrind -v --tool=memcheck --leak-check=full --num-callers=40 --log-file=valgrind.log --error-exitcode=1 test/build/test_atom_cpp` |

## Docker Images

Docker images are built from the [`Dockerfile`](Dockerfile) in this repo.

This project integrates tightly with CI and CD in order to produce ready-to-go
Docker containers that should suit most users' needs for dependencies. Then,
when you build your elements, they should be `FROM` one of these pre-built
containers in order to eliminate the hassle of building/installing `atom` in
multiple places.

The following images/tags are regularly maintained and built with each merge
to `master` in this repo.

### Images

#### elementaryrobotics/atom

The Docker Hub repo for Atom images. Should be used as a `FROM` in your
Dockerfile when creating elements.

| Tag  | Base OS | Arch | Description |
|------|---------|------|-------------|
| none/`latest` | `debian:buster-slim` | `amd64` | Atom + all dependencies |
| `cuda` | `nvidia/cuda` | `amd64` | Atom + all dependencies + CuDNN |
| `opengl` | `nvidia/opengl` | `amd64` | Atom + all dependencies + OpenGL |
| `opengl-cuda` | `nvidia/cuda` | `amd64` | Atom + all dependencies + OpenGL + CUDA |
| `aarch64` | `debian:buster-slim` | `aarch64` | Atom + all dependencies cross-comiled for aarch64/ARMv8 |

#### elementaryrobotics/nucleus

The Docker Hub repo for the Nucleus image. Should be used when running Atom.

| Tag  | Base OS | Arch | Description |
|------|---------|------|-------------|
| none/`latest` | `debian:buster-slim` | `amd64` | Nucleus + all dependencies |
| `aarch64` | `debian:buster-slim` | `aarch64` | Nucleus + all dependencies cross-comiled for aarch64/ARMv8 |

## Base Images

The Docker images from above are built with the most recent Atom source
atop prebuilt base images. The base images are built from the [`Dockerfile-base`](Dockerfile-base)
in this repo. The base image contains dependencies that change infrequently
and take a long time to build from source and/or install.

### Images

#### elementaryrobotics/atom

| Tag  | Base OS | Arch | Description |
|------|---------|------|-------------|
| `base` | `debian:buster-slim` | `amd64` | Build dependencies for Atom |
| `base-cuda` | `nvidia/cuda` | `amd64` | Build dependencies for Atom + CuDNN |
| `base-opengl` | `nvidia/opengl` | `amd64` | Build dependencies for Atom + OpenGL |
| `base-opengl-cuda` | `nvidia/cuda` | `amd64` | Build dependencies for Atom + OpenGL + CUDA |
| `base-aarch64` | `debian:buster-slim` | `aarch64` | Build dependencies for Atom cross-comiled for aarch64/ARMv8 |

#### Latest Tag

For each base, please find below the latest/recommended tag to use:

| base | tag |
|------|-----|
| `base` | `base-3027` |
| `base-cuda` | `base-cuda-3030` |
| `base-opengl` | `base-opengl-3028` |
| `base-opengl-cuda` | `base-opengl-cuda-3029` |
| `base-aarch64` | `base-aarch64-TODO` |


### Updating a Base Image

Base images are also built via our CI/CD integrations, though only on specific
branches. In order to get a change to a base image into production, the steps
are:
1. Make changes to `Dockerfile-base`
2. Test locally (these builds are long/expensive in CI/CD, especially for `aarch64`)
3. Push a branch with an appropriate name to this repo (see table below)
4. Wait for the CI/CD builds to pass/complete. This will build and push a new base
with a new tag, `base-XXX-YYY` to the appropriate DockerHub repo. `XXX` will be
the base tag and `YYY` will be the CircleCI build number.
5. Note the new tag, `base-XXX-YYY` in this documentation
6. Update the [build config](.circleci/config.yml) to use the new base
7. Push a branch with a non-base-building name to github and go through the
normal PR process.

#### Special Branches

Branches ending in the names below will cause CI/CD to run rebuilds of the base
images instead of the normal workflow:

| Branch | Description |
|--------|-------------|
| `*build-base-all` | Build all base images. Use sparingly |
| `*build-base-atom` | Build the normal Atom base image |
| `*build-base-cuda` | Build the Atom + Cuda base image |
| `*build-base-opengl` | Build the Atom + opengl base image |
| `*build-base-opengl-cuda` | Build the Atom + opengl + Cuda base image |
| `*build-base-aarch64` | Build the normal Atom base image x-compiled for ARM |

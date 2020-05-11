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
$ docker-compose pull
$ docker-compose up -d
$ docker exec -it atom bash
```

This will open up a shell within the most recent build of atom. This repo
will be mounted into the container at `/atom` and from there you can test
changes to the code.

### Next Steps

After working through the quickstart, it's recommended to try rebuilding the
Atom docker images in order to test changes. Following that, it's recommended
to check out the [guide to making your first element](ELEMENT_DEVELOPMENT.md)

### Contributing

Contributions of issues and pull requests are welcome!

## Building Docker Images

### Update Submodules

Atom depends on a few third-party dependencies which are all included as
submodules in these repos. From the top-level in this repo, run:

```
git submodule update --init --recursive
```

This will pull all of the proper dependencies.

### Atom and Nucleus

If you'd prefer to develop by building the atom Docker containers, this
can be done fairly easily as well by using the [`docker-compose-dev.yml`](docker-compose-dev.yml)
compose file.

Before building atom you'll need to set the proper library
version flag. This needs to be done outside of the Dockerfile since the .git repo used to generate the version is not copied into the Docker container.

From the top level of this directory, run
```
python3 languages/python/version.py
```

Once this has been done, you can rebuild the Dockerfile.

#### Default Build

```
$ docker-compose -f docker-compose-dev.yml build
```

Everything is the same as in the quickstart, except for a few things:
1. The `atom` container will have testing dependencies installed in order to
run `pytest` `googletest`, etc.
2. The `atom` container will be built from the atom client source in this repo.

#### Build Arguments

You can pass the following build arguments to the build as well. To do this,
simply edit the `args` section of the `docker-compose-dev.yml` to include/update
variables of your choice:

| Arg | Default | Description |
|-----|---------|-------------|
| `BASE_IMAGE` | elementaryrobotics/atom:base | Which base atom image to build atop. See [Base Images](#base-images) for choices |
| `PRODUCTION_IMAGE` | debian:buster-slim | Which image to use for the slimmed, production stage. Typically best to use the `BASE_IMAGE` that was used when building the `base` that you chose to use. |

#### Build Targets

You can choose to build multiple targets from the `Dockerfile`. Each possible target is explained
below. Modify the `target` section in `docker-compose-dev.yml` to switch.

| Target | Description |
|--------|-------------|
| `atom` | Production build of atom. All dependencies, libraries, and atom utilities installed. Everything else stripped out |
| `nucleus` | Production build of nucleus. All dependencies, libraries and atom utilities installed. Everything else stripped out |
| `atom-source` | Pre-production build. Contains everything in production and all source used to build it |
| `test` | Production build of atom plus test dependencies/utilities |

### Atom Base

The Atom docker images are built atop a base, where the base contains the
parts of the build that typically don't change frequently and are long/expensive
to rebuild. Occasionally we'd like to add something new to the base and will
need to rebuild the base as well. To do so:

```
$ docker build -f Dockerfile-base -t elementaryrobotics/atom:base .
```

In addition to the vanilla base that can be built with Dockerfile-base, you
can take the build product of Dockerfile-base and pass it through any of the
additional Dockerfiles in the [Variants](#variants) section below.

#### Build Arguments

There are a few build arguments when building the base:

| Arg | Default | Description |
|-----|---------|-------------|
| `BASE_IMAGE` | debian:buster-slim | Which base docker image to build atom atop. Can be anything ubuntu/debian |
| `BLAS_TARGET_CPU` | "" | Optional target CPU for which to compile the BLAS library. See [choices here](third-party/OpenBLAS/TargetList.txt) |
| `PYARROW_EXTRA_CMAKE_ARGS` | "" | CMAKE arguments to be sent to the PyArrow build. Useful when x-compiling |

#### Building a base with variants

To build with a variant

```
$ docker build -f <Dockerfile-variant> BASE_IMAGE=<previous-built-base> -t elementaryrobotics/atom:base-variant .
```

where `Dockerfile-variant` is an entry from the table above and `previous-built-base` is the image from a previous base built. In this fashion you can use these additional Dockerfiles to add many different things onto the atom base to suit your needs.

#### Rebuilding Atom on New Base

After rebuilding the base, you can rebuild the atom/nucleus images
atop your new base with:

```
$ docker-compose -f docker-compose-dev.yml build
```

In order to get the new base deployed and into production, please see the
section about [Updating a Base Image](#updating-a-base-image) below. The base
images are fully managed by CircleCI and generally you check in your desired
changes and push them to a branch with a special name to get them built and used
in production.

### ARM Images

Atom works cross-platform on ARM by compiling the same Dockerfiles. In order
to build and test for ARM a few additional steps are needed.


#### Set up buildx

This requires `buildx`, the new Docker builder that comes with Docker 19.03+.
Begin by installing Docker version 19.03+ on your machine. Once this is done,
proceed to the next steps.

Next, we need to enable the experimental Docker CLI:

```
$ export DOCKER_CLI_EXPERIMENTAL=enabled
```

And confirm we have `buildx` set up

```
$ docker buildx version
github.com/docker/buildx v0.3.1-tp-docker 6db68d029599c6710a32aa7adcba8e5a344795a7
```

Next, we need to enable `binfmt_misc` in order to run non-native Docker
images. This will set up `qemu` to run any `arm64` binary through the
`qemu_user_static` simulator so that it can be run on your intel-based machine.

```
docker run --rm --privileged docker/binfmt:66f9012c56a8316f9244ffd7622d7c21c1f6f28d
```

You should then be able to verify that everything is set up correctly:

```
$ cat /proc/sys/fs/binfmt_misc/qemu-aarch64
enabled
interpreter /usr/bin/qemu-aarch64
flags: OCF
offset 0
magic 7f454c460201010000000000000000000200b7
mask ffffffffffffff00fffffffffffffffffeffff
```

Finally, set up Docker to use the `buildx` builder as opposed to the
normal Docker builder:

```
$ docker buildx create --use --name atombuilder
```

And we should be able to verify that our builder is in use

```
$ docker buildx ls
NAME/NODE   DRIVER/ENDPOINT             STATUS  PLATFORMS
atombuilder *  docker-container
  atombuilder0 unix:///var/run/docker.sock running linux/amd64, linux/386, linux/arm64, linux/ppc64le, linux/s390x, linux/arm/v7, linux/arm/v6
default     docker
  default   default                     running linux/amd64, linux/386
```

#### Atom Image for ARM

An example command to build the atom image for ARM can be seen below:

```
$ docker buildx build \
    --platform=linux/aarch64 \
    --progress plain \
    --load \
    -f Dockerfile \
    -t elementaryrobotics/atom:aarch64 \
    --target=test \
    --build-arg BASE_IMAGE=elementaryrobotics/atom:base-aarch64 \
    --build-arg PRODUCTION_IMAGE=debian:buster-slim \
    --pull \
    .
```

It's likely always easiest to use the most recent pre-built base image for
your desired image base (see [Base Images](#base-images)).

You can also choose to build the base image yourself if you wish but note it
will take approximately 2-4 hours on a reasonable intel-based developer machine.

#### Nucleus Image for ARM

An example command to build the nucleus image for ARM can be seen below:

```
$ docker buildx build \
    --platform=linux/aarch64 \
    --progress plain \
    --load \
    -f Dockerfile \
    -t elementaryrobotics/nucleus:aarch64 \
    --target=nucleus \
    --build-arg BASE_IMAGE=elementaryrobotics/atom:base-aarch64 \
    --build-arg PRODUCTION_IMAGE=debian:buster-slim \
    --pull \
    .
```

Generally the same command as building the Atom image, but with a different
target in the multi-stage Dockerfile.

#### Base Image for ARM

It's not recommended to do this often, but the base image can be rebuilt
with the following command:

```
$ docker buildx build \
    --platform=linux/aarch64 \
    --progress plain \
    --load \
    -f Dockerfile-base \
    -t elementaryrobotics/atom:base-aarch64 \
    --target=base \
    --build-arg BASE_IMAGE=debian:buster-slim \
    --build-arg BLAS_TARGET_CPU=ARMV8 \
    --build-arg PYARROW_EXTRA_CMAKE_ARGS=-DARROW_ARMV8_ARCH=armv8-a \
    --pull \
    .
```

## Testing

In order to run tests, you'll want to develop with the "Rebuilding the Docker
Images" method as described above. Once you're in the `atom` container, you
can run the following tests:

| Test | Working Directory | Command |
|------|-------------------|---------|
| Python Unit Tests | `/atom/languages/python/tests` | `pytest` |
| C Unit Tests | `/atom/languages/c` | `make -j8 test` |
| C++ Unit Tests | `/atom/languages/cpp` | `make -j8 test` |
| C++ Memory Check | `/atom/languages/cpp` | `valgrind -v --tool=memcheck --leak-check=full --num-callers=40 --log-file=valgrind.log --error-exitcode=1 test/build/test_atom_cpp` |

### Testing Atom Builds

In order to build and test your code in an environment identical to production,
it's recommended that you run the following initial steps:
(example shown for Python)

```
$ docker-compose -f docker-compose-dev.yml build
$ docker-compose -f docker-compose-dev.yml up -d
$ docker exec -it atom bash
# cd /atom/languages/python/tests
# pytest
```

You should see all tests pass.

### Testing ARM Builds

Similarly, you can test your ARM builds even from an Intel-based laptop!

Follow, the steps to build the atom + nucleus stages for ARM as covered
in the docs above, then:

```
$ docker-compose -f docker-compose-arm.yml up -d
$ docker exec -it atom-arm bash
# cd /atom/languages/python/tests
# pytest
```

You should see all tests pass. Also interesting to note/confirm is that
if you run the command below while in the Docker container for the ARM atom
image:

```
# uname -a
Linux 2b4919a2e614 4.15.0-96-generic #97~16.04.1-Ubuntu SMP Wed Apr 1 03:03:31 UTC 2020 aarch64 GNU/Linux
```

Note that this is indeed an `aarch64` build of linux being run on an intel
PC through the QEMU simulator.

## Docker Images

Docker images are built from the [`Dockerfile`](Dockerfile) in this repo.

This project integrates tightly with CI and CD in order to produce ready-to-go
Docker containers that should suit most users' needs for dependencies. Then,
when you build your elements, they should be `FROM` one of these pre-built
containers in order to eliminate the hassle of building/installing `atom` in
multiple places.

The following images/tags are regularly maintained and built with each merge
to `master` in this repo.

### Variants

Atom ships with many dependencies pre-compiled and pre-installed in the
container to make development more consistent across platforms and codebases.
You are always welcome to remove/override/reinstall any dependency as what you do
in your Docker container won't affect any other element in the system.

In order to track groups of dependencies we use the term `variant`, where the
default `variant` is `stock`, i.e. no additional dependencies beyond what's
needed to run Atom. In the tables below you'll find a description of the
different variants of Atom and what they come with pre-installed. Note some
release of Atoms are the combination of multiple variants -- these will
come with all dependencies installed from all variants in the tag.

#### `stock`

The `stock` variant is built using [`Dockerfile-base`](Dockerfile-base)

| Dependency | Version | Description |
|------------|---------|-------------|
| [`hiredis`](languages/c/third-party/hiredis/hiredis) | `v0.13.3` | C redis client library |
| [`msgpack-c`](languages/c/third-party/msgpack-c/msgpack-c) | `3.2.1` | C/C++ msgpack library |
| [`cython`](languages/python/third-party/cython) | `0.29.16` | Python<>C optimization tool |
| [`OpenBLAS`](third-party/OpenBLAS) | `v0.3.9` | Linear Algebra library |
| [`numpy`](languages/python/third-party/numpy) | `v1.18.3` | Python linear algebra library |
| [`arrow`](third-party/apache-arrow) | `0.17.0` | Apache arrow serialization library (C/C++/Python) |
| [`redis-py`](languages/python/third-party) | `3.4.1` | Python redis client |
| [`redis`](third-party/redis) | `6.0-rc4` | Redis itself |

#### `opencv`

The `opencv` variant is built using [`Dockerfile-opencv`](Dockerfile-opencv)

| Dependency | Version | Description |
|------------|---------|-------------|
| [`opencv`](third-party/opencv) | `4.3.0` | Computer Vision Libraries (C/C++/Python) |
| [`pillow`](languages/python/third-party/Pillow) | `7.1.2` | Python image processing library |

##### Dockerfile-opencv build arguments

| Arg | Default | Description |
|-----|---------|-------------|
| `BASE_IMAGE` | N/A | Which image we should build from to install opencv into |
| `PRODUCTION_IMAGE` | N/A | Image that this version of atom will eventually ship in, i.e. `debian:buster-slim`. This is needed to determine which libraries to package up |
| `ARCH` | `x86_64` | Architecture we're building for. Pass `aarch64` for ARM |

#### `opengl`

The `opengl` variant is built using either [`Dockerfile-opengl`](Dockerfile-opengl) or
using a BASE_IMAGE like `nvidia/opengl` that includes it. As such, the version
of openGL installed can vary.

##### Dockerfile-opengl build arguments

| Arg | Default | Description |
|-----|---------|-------------|
| `BASE_IMAGE` | N/A | Which image we should build from to install opengl into |

#### `cuda`

The `cuda` variant is based off of an NVIDIA image and includes

| Dependency | Version | Description |
|------------|---------|-------------|
| CUDA | `10.2` | NVIDIA graphics card accelerated math library |
| CUDNN | `7.6` | NVIDIA graphics card accelerated machine learning library |

#### `vnc`

The `vnc` variant adds the ability to render graphics to an in-container display server that can
be accessed through an internet browser, typically at port `6080`. This is nice
since it allows users on mac/windows to be able to see and interact with graphical
components built on atom without having to change the code. You write your code
once, for linux, and the graphics can be used via the VNC over the internet and on
all operating systems.

The VNC variant is built using software from the following tools:
- [`NoVNC`](third-party/noVNC)
- [`docker-opengl`](third-party/docker-opengl)

##### Dockerfile-vnc build arguments

| Arg | Default | Description |
|-----|---------|-------------|
| `BASE_IMAGE` | N/A | Which image we should build from to install the VNC into |

### Images

#### elementaryrobotics/atom

The Docker Hub repo for Atom images. Should be used as a `FROM` in your
Dockerfile when creating elements. Please migrate to using the tags in the
table below. For legacy purposes, we do support older variants of tags
as well but they're not recommended for use and not documented here.

All base images are prepended by an Atom tag, i.e. `v1.4.1-`. The remainder of
the tag can be found in the table below

| Tag  | Base OS | Arch | Description |
|------|---------|------|-------------|
| `stock-amd64` | `debian:buster-slim` | `amd64` | Atom + all dependencies |
| `opencv-amd64` | `debian:buster-slim` | `amd64` | Atom + OpenCV + all dependencies |
| `cuda-amd64` | `nvidia/cuda` | `amd64` | Atom + all dependencies + CUDA + CuDNN |
| `opengl-cuda-amd64` | `nvidia/cuda` | `amd64` | Atom + all dependencies + OpenGL + CUDA + CuDNN |
| `opengl-cuda-vnc-amd64` | `nvidia/cuda` | `amd64` | Atom + all dependencies + OpenGL + CUDA + CuDNN + VNC for graphics |
| `opengl-amd64` | `nvidia/opengl` | `amd64` | Atom + all dependencies + OpenGL |
| `opengl-vnc-amd64` | `nvidia/opengl` | `amd64` | Atom + all dependencies + OpenGL + VNC for graphics |
| `stock-aarch64` | `debian:buster-slim` | `aarch64` | Atom + all dependencies cross-comiled for aarch64/ARMv8 |
| `opencv-aarch64` | `debian:buster-slim` | `aarch64` | Atom + all dependencies + OpenCV cross-comiled for aarch64/ARMv8 |

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

All base images are prepended by an Atom tag, i.e. `v1.4.1-`. The remainder of
the tag can be found in the table below

| Tag  | Base OS | Arch | Description |
|------|---------|------|-------------|
| `base-stock-amd64` | `debian:buster-slim` | `amd64` | Build dependencies for Atom |
| `base-opencv-amd64` | `debian:buster-slim` | `amd64` | Build dependencies for Atom + OpenCV |
| `base-cuda-amd64` | `nvidia/cuda` | `amd64` | Build dependencies for Atom + CUDA + CuDNN |
| `base-opengl-cuda-amd64` | `nvidia/cuda` | `amd64` | Build dependencies for Atom + CUDA + CuDNN |
| `base-opengl-cuda-vnc-amd64` | `nvidia/cuda` | `amd64` | Build dependencies for Atom + CUDA + CuDNN + VNC |
| `base-opengl-amd64` | `nvidia/opengl` | `amd64` | Build dependencies for Atom + OpenGL |
| `base-opengl-amd64` | `nvidia/opengl` | `amd64` | Build dependencies for Atom + OpenGL + VNC |
| `base-stock-aarch64` | `debian:buster-slim` | `aarch64` | Build dependencies for Atom cross-comiled for aarch64/ARMv8 |
| `base-opencv-aarch64` | `debian:buster-slim` | `aarch64` | Build dependencies for Atom + OpenCV cross-comiled for aarch64/ARMv8 |

### Updating a Base Image

Base images are also built via our CI/CD integrations, though only on specific
branches. In order to get a change to a base image into production, the steps
are:
1. Make changes to `Dockerfile-base`, any additional dockerfile for bases, or to the CI/CD configuration
2. Test locally (these builds are long/expensive in CI/CD, especially for `aarch64`)
3. Push a branch with an appropriate name to this repo (see table below)
4. Wait for the CI/CD builds to pass/complete. This will build and push a new base
with a new tag, `base-XXX-YYY` to the appropriate DockerHub repo. `XXX` will be
the base tag and `YYY` will be the CircleCI build number.
5. Update the [aliases section of the CircleCI config](.circleci/config.yml) to use the new base
6. Check in the results from (5) and merge the branch into master. The new base tag will be auto-pushed to the generic base tag `base-XXX` upon merge into master.

#### Updating Base Dockerfiles

The base dockerfile is not used in the production images in order to reduce image size. Instead, everything from the following directories is coped over:

- `/usr/local/lib`
- `/usr/local/include`
- `/opt/venv`

If you're adding something to the base (new library, etc.) ensure it is installed in `/usr/local`. One trick to doing this with complex library dependencies (some installed by apt-get) can be seen in the [OpenCV base Dockerfile](Dockerfile-opencv):

```
FROM ${BASE_IMAGE} as with-opencv

... install things with apt-get ...
... build opencv ...

# Last thing to do: figure out what OpenCV needs to run
RUN ldd /usr/local/lib/libopencv* | grep "=> /" | awk '{print $3}' | sort -u > /tmp/required_libs.txt

#
# Determine libraries we'll ship with in production so we can see what's
#   missing
#
FROM ${PRODUCTION_IMAGE} as no-deps

ARG ARCH=x86_64

RUN ls /lib/${ARCH}-linux-gnu/*.so* > /tmp/existing_libs.txt && \
    ls /usr/lib/${ARCH}-linux-gnu/*.so* >> /tmp/existing_libs.txt

#
# Copy missing libraries from production into /usr/local/lib
#
FROM with-opencv as opencv-deps

COPY --from=no-deps /tmp/existing_libs.txt /tmp/existing_libs.txt
RUN diff --new-line-format="" --unchanged-line-format=""  /tmp/required_libs.txt /tmp/existing_libs.txt | grep -v /usr/local/lib > /tmp/libs_to_copy.txt
RUN xargs -a /tmp/libs_to_copy.txt cp -L -t /usr/local/lib
```

OpenCV depends on a bit of a laundry list of things that we install with apt-get. If we just copy over `/usr/local/lib`, where we install OpenCV, we will get a littany of "cannot find shared library" errors when we go to launch anything that uses OpenCV. As such, in the final step of building OpenCV we use `ldd` to determine what shared libraries OpenCV needs to link against in production and put the info in `required_libs.txt`. We then make a stage FROM the eventual production image and see which libraries it comes with and put that info in `existing_libs.txt`. Finally, we copy the set of libraries that are in `required_libs.txt` and not in `existing_libs.txt` into `/usr/local/lib` before finishing the build. We use the `LD_LIBRARY_PATH` environment variable (set in all Atom images) to let the linker to look first in `/usr/local/lib` for any libraries it needs.

#### Special Branches

Branches ending in some variant of `-build-base` will cause base builds
instead of the typical Atom workflow. Please push to these branches sparingly
and only when needed as these types of builds are usually, long, compute-intensive
and expensive (especially aarch-64). This section will become stale quickly
if we document the branch names here -- please consult the [CircleCI Config](.circleci/config.yml)
in the Base Build section for exact branch names and what they do.

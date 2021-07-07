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

## Using Atom

It's quite easy to get up and running and using Atom! Atom ships pre-built Docker images with all of the language clients pre-installed.

### Releases + Repos

Production builds are pushed to Dockerhub repositories to match the releases pushed on this repo, i.e. if there's release `vX.Y.Z` there will be tags on **all** of the following repositories:

| Repository | Description |
|------------|-------------|
| [`elementaryrobotics/atom`](https://hub.docker.com/r/elementaryrobotics/atom) | Atom images to build elements atop |
| [`elementaryrobotics/nucleus`](https://hub.docker.com/r/elementaryrobotics/nucleus) | Nucleus images to use as the core of Atom |
| [`elementaryrobotics/atom-doc`](https://hub.docker.com/r/elementaryrobotics/atom-doc) | Documentation repo which spins up a webserver with the docs |
| [`elementaryrobotics/metrics`](https://hub.docker.com/r/elementaryrobotics/metrics) | Metrics image which contains Grafana and runs the Atom dashboards |
| [`elementaryrobotics/formatter`](https://hub.docker.com/r/elementaryrobotics/formatter) | General-purpose style formatter containing `black`, `flake8`, `isort`, and others |

### Intel + ARM

Atom is built for both 64-bit intel and 64-bit ARM. All docker tags on the following repositories: are multi-arch manifests which are built for both `linux/amd64` and `linux/arm64`:

- [`elementaryrobotics/atom`](https://hub.docker.com/r/elementaryrobotics/atom)
- [`elementaryrobotics/nucleus`](https://hub.docker.com/r/elementaryrobotics/nucleus)
- [`elementaryrobotics/metrics`](https://hub.docker.com/r/elementaryrobotics/metrics)

### Atom Types

The following types/flavors of atom are built with each release and are pushed to **atom** and **nucleus**

| Tag | Description |
|-----|-------------|
| `vX.Y.Z` | Base atom. Atom + all dependencies |
| `vX.Y.Z-cv` | Adds in openCV + other CV libraries atop base Atom. |
| `vX.Y.Z-cuda` | Adds in CUDA support atop CV Atom |
| `vX.Y.Z-vnc` | Adds in VNC support atop CV Atom |

### Building your first element

Check out the [Atom Walkthrough](https://atomdocs.io/#atom-walkthrough) in the docs!

## Redis Talks and Slides

Please see the [Redis Talks and Slides](https://github.com/elementary-robotics/atom/wiki/Redis-Talks-and-Slides) page of the wiki for video and slides from the talks that have been given on Atom at various Redis conferences.

## Developing for Atom

### Update Submodules

It's always a good idea to ensure your submodules are up-to-date. Run this command after cloning the repo and/or updating your branch

```
git submodule update --init --recursive
```

### Quickstart

There are two ways to develop for Atom:
1. Link your python application-level code into a prebuilt Atom docker image
2. Re-build the Atom docker image

Most client-level changes should be able to use path #1. It's significantly easier, and the test/build process is simpler. The quickstart section here will cover path #1, see the [Building Docker Images](#Building-Docker-Images) section for more detail on how to rebuild the container.

To launch the latest production Atom images with the code from your local repos linked in for quick development, run:

```
docker-compose -f docker-compose-main.yml -f docker-compose-run.yml up -d
```

You can then run

```
docker exec -it atom bash
```

To pull up a shell in the atom docker image and go ahead developing from there for your language of choice. The code from this local repository will be linked into the container at `/atom`, so you can do things (within the container) like:

```
cd /atom/languages/python && python setup.py install && pytest
```
```
cd /atom/languages/cpp && make install && make test
```

To stop the containers

```
docker-compose -f docker-compose-main.yml -f docker-compose-run.yml down -t0
```

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

### Set up buildx

We want to use the buildkit/buildx frontend for Docker, as this gives us some nifty features we rely on for the atom build.

We first want to enable using the buildx builder

```
export DOCKER_CLI_EXPERIMENTAL=enabled
```

The commands below will install the expected version (0.8.3) and set it as the default buildx version

```
docker buildx ls | grep "build-v0.8.3" || docker buildx create --name build-v0.8.3 --driver docker-container --driver-opt image=moby/buildkit:v0.8.3,network=host
docker buildx use --default build-v0.8.3
docker buildx inspect --bootstrap
```

### Building all docker images

There are four docker images to build for this repository:
- `atom`
- `nucleus`
- `metrics`
- `formatter`

If we look at [`docker-compose-build.yml`](docker-compose-build.yml), it expects us to have a version of each image tagged `local-dev`. The commands in this section will allow you to build all of these `local-dev` images.

We do not use `docker-compose build` here, and instead build each of the tags directly. This is because `docker-compose build` does not have good support for the `buildx` frontend and all of its options as of yet.

The primary docker images built in this repo are `atom` and `nucleus`. `metrics` and `formatter` are helper images that serve minor roles. As such, more info/documentation is needed for the `atom` and `nucleus` builds, so the following sections below apply only to the `atom` and `nucleus` builds:

- Docker Image Bases
- Build Argumens

### Docker Image Bases

Atom has the following bases available. A base is a stage in the multi-stage [Dockerfile](Dockerfile) which we then add the atom application-level code atom to create the output image. With the new `buildx` frontend, we can selectively apply the final `atom` stage of the multi-stage Dockerfile atop any other build stage in the Dockerfile which is pretty nifty. The table below describes the base stages which can be used

| Name | Description |
|------|-------------|
| `atom-base` | Bare minimum requirements for Atom |
| `atom-base-cv` | Adds in openCV and other CV processing libraries atop `atom-base` |
| `atom-base-vnc` | Adds in NoVNC atop `atom-base-cv` |
| `atom-base-cuda` | Adds in additional CUDA dependencies atop `atom-base-cv` |

### Build Arguments

You can pass the following build arguments to the build. You'll see them in each of the pre-compiled build commands below and you can override/edit as you'd like.

The build arguments primarily control which docker image we should begin our atom build with, and which base from the table above we should build before putting the application-level Atom code atop it.

| Arg | Default | Description |
|-----|---------|-------------|
| `STOCK_IMAGE` | `ubuntu:bionic-20210416` | Which image to build from. Should work with most things debian-based |
| `ATOM_BASE` | `atom-base` | Which stage of the [Dockerfile](Dockerfile) to use as the "base" for Atom. Should be an option from the [Bases Table](#Bases) table. Docker will build this stage and than put the `atom` stage atop it for the final image |

### Build Targets

You can choose to build multiple targets from the `Dockerfile`. Each possible target is explained
below.

We default to the "test" stage for atom in the below build command to add in test dependencies. If you want to change to a production version, you can change the target to "atom".

| Target | Description |
|--------|-------------|
| `atom` | Production build of atom. All dependencies, libraries, and atom utilities installed. Everything else stripped out |
| `nucleus` | Production build of nucleus. All dependencies, libraries and atom utilities installed. Everything else stripped out |
| `atom-source` | Pre-production build. Contains everything in production and all source used to build it |
| `test` | Production build of atom plus test dependencies/utilities |

### Building `nucleus`

Run the command below to build the nucleus. It will leverage/pull the most recent build cache which will likely save you some time

```
docker buildx build \
    -f Dockerfile \
    -t elementaryrobotics/nucleus:local-dev \
    --pull \
    --cache-from type=registry,ref=elementaryrobotics/atom:cache-x86_64 \
    --build-arg STOCK_IMAGE=ubuntu:bionic-20210416 \
    --build-arg ATOM_BASE=atom-base \
    --load \
    --progress=plain \
    --target=nucleus \
    .
```

At the end of this command you shold have a local image, `elementaryrobotics/nucleus:local-dev` you can see from running `docker image ls`

### Building `atom`

The below command will build the base atom and tag it as `elementaryrobotics/atom:local-dev`. See the subsections below for the commands/modifications to build either the CV or CUDA atom variants.

```
docker buildx build \
    -f Dockerfile \
    -t elementaryrobotics/atom:local-dev \
    --pull \
    --cache-from type=registry,ref=elementaryrobotics/atom:cache-x86_64 \
    --build-arg STOCK_IMAGE=ubuntu:bionic-20210416 \
    --build-arg ATOM_BASE=atom-base \
    --load \
    --progress=plain \
    --target=test \
    .
```

#### Building CV `atom`

```
docker buildx build \
    -f Dockerfile \
    -t elementaryrobotics/atom:local-dev \
    --pull \
    --cache-from type=registry,ref=elementaryrobotics/atom:cache-cv-x86_64 \
    --build-arg STOCK_IMAGE=ubuntu:bionic-20210416 \
    --build-arg ATOM_BASE=atom-base-cv \
    --load \
    --progress=plain \
    --target=test \
    .
```

#### Building VNC `atom`

```
docker buildx build \
    -f Dockerfile \
    -t elementaryrobotics/atom:local-dev \
    --pull \
    --cache-from type=registry,ref=elementaryrobotics/atom:cache-vnc-x86_64 \
    --build-arg STOCK_IMAGE=ubuntu:bionic-20210416 \
    --build-arg ATOM_BASE=atom-base-vnc \
    --load \
    --progress=plain \
    --target=test \
    .
```

#### Building CUDA `atom`

```
docker buildx build \
    -f Dockerfile \
    -t elementaryrobotics/atom:local-dev \
    --pull \
    --cache-from type=registry,ref=elementaryrobotics/atom:cache-cuda-x86_64 \
    --build-arg STOCK_IMAGE=nvcr.io/nvidia/cuda:10.2-cudnn8-devel-ubuntu18.04 \
    --build-arg ATOM_BASE=atom-base-cuda \
    --load \
    --progress=plain \
    --target=test \
    .
```

### Building `metrics`

```
docker buildx build \
    -f metrics/Dockerfile \
    -t elementaryrobotics/metrics:local-dev \
    --pull \
    --load \
    --cache-from type=registry,ref=elementaryrobotics/metrics:cache-x86_64 \
    --progress plain \
    .
```

### Building `formatter`

```
cd utilities/formatting && docker buildx build \
    -f Dockerfile \
    -t elementaryrobotics/formatter:local-dev \
    --pull \
    --load \
    --cache-from type=registry,ref=elementaryrobotics/formatter:cache-x86_64 \
    --progress plain \
    .
```

### Launching built containers

Now that we've built all of our images, we can run them with

```
docker-compose -f docker-compose-main.yml -f docker-compose-build.yml up -d
```

You should see everything launch/run normally. If you see any errors similar to:
```
ERROR: manifest for elementaryrobotics/metrics:local-dev not found: manifest unknown: manifest unknown
```

It means you don't have the locally built version to launch with. Please see
the section for building that image and re-run the command. It may never
have been run before or the image may have been deleted.

### Stopping containers

```
docker-compose -f docker-compose-main.yml -f docker-compose-build.yml down -t0
```

### Rebuilds

If you want to rebuild, your flow should be

1. Stop containers
2. Rebuild image of interest with command from above (atom/nucleus/metrics/formatter)
3. Re-launch containers

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

## Formatting + Linting

Formatting + Linting checks are run in our CI/CD pipeline. Code will not be able
to be merged into `latest` without passing.

### Python

To set up type checking and code completion in your text editor, [see the wiki](https://github.com/elementary-robotics/wiki/wiki/Python-Code-Completion-and-Type-Checking-in-Text-Editors).

#### Formatting for Atom

Atom utilizes the following formatting guidelines:

1. Use [`black`](https://github.com/psf/black) for formatting. All code must
    pass `black --check`.
2. Atop black, follow the Elementary Robotics [company-wide `.flake8`](
    utilities/formatting/.flake8). This is more strict than black and catches
    more things than black can/will catch since black only deals with stylistic
    errors and not the full set of errors that can be caught with good linting.

We have created a [Docker container](utilities/formatting/Dockerfile) that comes
preinstalled with `.flake8` and `black`.

To check your formatting:
```
docker-compose -f docker-compose-dev.yml run formatting
```

This, by default, will:
1. Build the formatting container (if not already built)
2. Launch the formatting container
3. Run `black --check` and `flake8`
4. Return an exit code of 0 if all code passes, else an exit code of 1 if
    anything failed

If you'd like to configure the formatter to auto-format and then do the `.flake8`
check you can do so by adding `-e DO_FORMAT=y` to the command:

```
docker-compose -f docker-compose-dev.yml run -e DO_FORMAT=y formatting
```

This will add a step to call `black` between steps (2) and (3) of the above list
but otherwise run the same process.

#### General-purpose Formatting

This repo contains a [Dockerfile](utilities/formatting/Dockerfile) and builds a general-purpose formatter image that can be used to apply the style formatting/checks in this repo anywhere you write code.

To check your code:
```
docker run -e BLACK_EXCLUDE="" -e FLAKE8_EXCLUDE="" --mount src=$(pwd),target=/code,type=bind elementaryrobotics/formatter
```

After running this, check the return code with `echo $?` to see if the checks passed. If the return code is 0, then the checks passed, if nonzero then there were formatting inconsistencies. The logs will also be indicative.

To reformat your code:
```
docker run -e DO_FORMAT=y -e BLACK_EXCLUDE="" -e FLAKE8_EXCLUDE="" --mount src=$(pwd),target=/code,type=bind elementaryrobotics/formatter
```

Build checks are set up s.t. the formatter must pass for code to be merged in.

The formatter exposes the following command-line options which are used in the [run script](utilities/formatting/run.sh)

| Option | Default | Description |
|--------|---------|-------------|
| `DO_FORMAT` | "" | If non-empty, i.e. not "", run the auto-formatter before running the formatting check. Default is to not run the auto-formatter |
| `FORMAT_BLACK` | "y" | Use Black as the auto-formatter of choice. This is default, but we may add other auto-formatters in the future. Set to empty to not use black. |
| `DO_CHECK` | "y" | If non-empty, i.e. not "", run the formatting/linting check automatically. This is the default. |
| `DO_HANG` | "" | If non-empty, instead of returning when finished, hang the container. This is nice if you want to then shell in to the container and play around with the formatter, but otherwise not that useful |

## Language-Specific Docs

Please see the READMEs in the individual language folders for more information about the language clients.

- [Python](languages/python)
- [C++](languages/cpp)
- [C](languages/c)

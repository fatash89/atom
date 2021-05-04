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

### Quickstart

After cloning the repo, clone all submodules with
```
git submodule update --init --recursive
```

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

### Default Build

```
$ docker-compose -f docker-compose-dev.yml build
```

### Build Arguments

You can pass the following build arguments to the build as well. To do this,
simply edit the `args` section of the `docker-compose-dev.yml` to include/update
variables of your choice:

| Arg | Default | Description |
|-----|---------|-------------|
| `STOCK_IMAGE` | `ubuntu:focal-20210416` | Which image to build from. Should work with most things debian-based |
| `ATOM_BASE` | `atom-base` | Which stage of the [Dockerfile](Dockerfile) to use as the "base" for Atom. Should be an option from the [Bases Table](#Bases) table. Docker will build this stage and than put the `atom` stage atop it for the final image |

#### Bases

Atom has the following bases available

| Name | Description |
|------|-------------|
| `atom-base` | Bare minimum requirements for Atom |
| `atom-base-cv` | Adds in openCV and other CV processing libraries atop `atom-base` |
| `atom-base-vnc` | Adds in NoVNC atop `atom-base-cv` |

### Build Targets

You can choose to build multiple targets from the `Dockerfile`. Each possible target is explained
below. Modify the `target` section in `docker-compose-dev.yml` to switch.

| Target | Description |
|--------|-------------|
| `atom` | Production build of atom. All dependencies, libraries, and atom utilities installed. Everything else stripped out |
| `nucleus` | Production build of nucleus. All dependencies, libraries and atom utilities installed. Everything else stripped out |
| `atom-source` | Pre-production build. Contains everything in production and all source used to build it |
| `test` | Production build of atom plus test dependencies/utilities |

### Using `buildx`

While not required, using `buildx` will significantly improve the build experience. In particular, `buildx` supports the ability to **skip unused stages in a multi-stage dockerfile** where the normal docker builder does not.

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

Finally, to set up an alias to make `buildx` your default builder, run
```
docker buildx install
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

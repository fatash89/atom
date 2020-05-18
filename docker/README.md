# Atom Docker Images

This section contains documentation on the Atom docker images and how to build/use them.

The Atom docker image is typically a build of the `atom` folder (and its resident) Dockerfiles
atop any one "base" image that's at a minimum equal to a build of the `stock` folder
but might also have additional nice-to-haves such as `graphics`, `extras`, etc.
tacked on.

The `stock` image consists of, at the very least, all of the libraries required for a particular Atom language client to function. At the moment, all language clients share the same base, but this may not be the case in the future.

These images are provided as a convenience and due to the requirement of Atom needing to cross-compile for ARM, typically builds all packages from source unless they're commonly available for both platforms. This gives us better continuity between testing/development on AMD64 systems and deployment on ARM systems such as the Raspberry Pi, Nvidia Jetson/Xavier line of products.

## Dockerfiles

The docker images are built through a series of Dockerfiles. This is designed as such for a few reasons:

1. All parts may not be the same across all use cases. Mathematical acceleration libraries like BLAS, for example, will be highly platform-dependent to get the same results. We want to be able to switch out Dockerfiles/Dockerfile arguments here and rebuild just this piece without needing to change other parts of the build. We also get better caching performance/build sharability this way as parts that builds have in common can be shared and not rebuilt needlessly.
2. Cross-compiling for ARM on AMD64 machines uses the QEMU similator. This is quite awesome that it's possible, but quite slow. As we run build jobs on our CI/CD servers, slower builds cost more money so we want to minimize the time spent rebuilding the same thing. Further, CircleCI in particular has a 5-hour single job limit which all of the dependencies for Atom don't fit into on a standard-sized machine (large). As bumping up to the next resource class on CircleCI is 10x the cost, it's easier/better to break the job up into multiple sections.

### Naming

Dockerfiles are prepended with a two-digit integer such that we can just
loop over all of the Dockerfiles in a given Directory and be sure that
we're building/chaining them in the right order. This is similar to how
init scripts in `/etc/init.d` work. It's typically best to leave "space" between
the numbering such that if things need to be added to the C/C++ build, for
example, we don't need to re-name all of the Dockerfiles that come after. This
is a bit arbitrary and not important to get perfect.

The resultant naming scheme for a Dockerfile is then:

```
<num>-Dockerfile-<descriptor>
```

where `<num>` is the number as discussed above and `<descriptor>` should
be a unique string descriptor.

### Arguments

Since we plan to just loop over Dockerfiles in a directory to build a patricular
flavor of Atom, we need a way to specify each Dockerfile's arguments s.t. we
can have a generic build script. This is done through adding a text file
named `<descriptor>-<platform>-args` in the same folder as the corresponding
Dockerfile. When the build scripts are going through and building the Dockerfile,
they'll look for this args file, and if it exists, will take each line and pass
it as a `--build-arg` to the `docker buildx build` command.

For example, a file named `example-amd64-args` with the following contents:
```
SOME_ARG=foo
OTHER_ARG=bar
```

would get converted to the following when building the Dockerfile `<num>-Dockerfile-example`:
```
docker buildx build
... normal build args ...
--build-arg SOME_ARG=foo
--build-arg SOME_ARG=bar
... rest of build command
```

## Build options

All of the dependencies that are necessary to run a basic Atom element have their Dockerfiles found in the `stock` folder. The base image built from the resulting chain of these Dockerfiles is `stock`. All additional things/nice-to-haves are broken out into groups in their own folder. The table below explains
the options and what's in each.

| Option | Description |
|--------|-------------|
| `stock` | Contains everything needed to run Atom |
| `extras` | Contains additional libraries that many elements may need such as `opencv`, etc. |
| `graphics` | Contains everything needed to use graphics in Atom such as `opengl`, a VNC, etc. |
| `atom` | Contains the actual Atom libraries, redis, etc. |

## Building

You'll need Docker version 19.0.3 or greater in order to build Atom images. This is because we use the new experimental `buildx` builder in order to get consistent results on ARM and AMD platforms.

### Script

The build script used is `build.sh`.

Since the build is a chain of Dockerfiles within a folder, we use this bash script to perform the build and produce the final output for any base image.

The build takes positional arguments as seen in the table below:

| Position | Description | Examples |
|----------|-------------|---------|
| 1 | Platform | `amd64` or `aarch64` |
| 2 | Docker repo for the resulting and intermediate images | `elementaryrobotics/atom`, etc. |
| 3 | Docker Tag for the resulting image  | Tag for the final output of the build process | `base-stock-descriptor`, etc. |
| 4 | Original Image/OS we should build Atom atop | `debian:buster-slim`, etc. |
| 5 | Which base option we should build. | `stock`, etc. See table above |
| 6 | Production Image/OS. This will be passed to the final production stage so that we have the minimal number of layers possible | `debian:buster-slim` |

The build script will:

1. Build for the platform from (1)
2. Tag the resulting image with the repo from (2)
3. Tag the resulting image with a tag of the form `(3)-(5)-(1)`
4. Use (4) as the first `BASE_IMAGE` for the numerically first `Dockerfile` in the folder (5)
5. Run through all of the `Dockerfile`s in the folder (5), taking the result of the previous `Dockerfile` and passing it as a `BASE_IMAGE` to the current `Dockerfile` so they all build atop each other.
6. Pass arguments to the Dockerfiles using the argument file specification from above. Argument files aren't required, but will be parsed if present.
7. Once all `Dockerfiles` in (5) have been built, will pass the result through the `minimize` and `production` Dockerfiles in the `utilities` folder. See below for explanation of what this does.

### Utilities Dockerfiles

#### Minimize

These will look at all things in `/usr/local/bin` and `/usr/local/lib`, use `ldd` to determine which libraries they need, and copy all needed libraries into `/usr/local/lib` if they don't exist. Additional libraries/things to check can be passed using the `ADDITIONAL_LIB_LOCATIONS` variable (see [`graphics`](graphics/minimize-amd64-args) for example).

After all libraries that are needed throughout the rootfs have been accounted for and moved into `/usr/local/lib`, this will take the contents of the rootfs and package them into a tarball. By default, the following
folders are packaged up:

| Folder | Description |
|--------|-------------|
| `/usr/local/lib` | All libraries that are needed. It's very important that if you build any shared libraries, they wind up in here at the end of your Dockerfile |
| `/usr/local/include` | All headers that are needed. Would likely shrink down image sizes a bit eventually to remove this but not an issue for now |
| `/usr/local/bin` | All binaries that are needed. It's very important that if you build a binary that it winds up in here. |
| `opt/venv` | The `python3` virtual environment in which all Python packages are installed. This is automagically activated and used whenever you run `python3` |
| `/usr/lib/python` | The `python3` installation itself |
| `/usr/bin/python` | The `python3` binaries |
| `etc/ssl` | SSL certificates |

You can package up additional directories by using the `ADDITIONAL_FILES` variable (see [`graphics`](graphics/minimize-amd64-args) for example).

The tarball is copied out of the build so that it can be injected into the production container

#### Production

Once we have the tarball from `minimize`, it's quite simple to make the `production` image. We go from the base image from argument 6 to the build script (should be something like `debian:buster-slim` or `nvidia:cuda`) and do the following:

1. Add in and extract the tarball from `minimize`. This can be done in a single Docker step using `ADD` which is slick.
2. Run `apt-get update` and then install any packages needed for the production image. This defaults to nothing, however needed production packages can be set using the `PRODUCTION_PACKAGES` variable (set during the `minimize` setup, not the `production` step, see [`graphics`](graphics/minimize-amd64-args) for example).

### Example/Usage

An example invocation for `stock` and `amd64` can be found below:
```
./build.sh amd64 elementaryrobotics/atom build-base debian:buster-slim stock debian:buster-slim
```

This will, for example, after some amount of time, produce an image named:
```
elementaryrobotics/atom:build-base-stock-amd64
```

Once this is done, you may want to then add the `graphics` folder to the `stock` image, and you might run the script again with

```
./build.sh amd64 elementaryrobotics/atom build-base localhost:5000/elementaryrobotics/atom:build-base-stock-amd64 graphics debian:buster-slim
```

Then, you might want to add in the `extras` to get OpenCV

```
./build.sh amd64 elementaryrobotics/atom build-base localhost:5000/elementaryrobotics/atom:build-base-graphics-amd64 extras debian:buster-slim
```

And finally we'd want to put Atom atop it

```
./build.sh amd64 elementaryrobotics/atom build-base localhost:5000/elementaryrobotics/atom:build-base-extras-amd64 atom debian:buster-slim
```

At the end of this, we have Atom built atop everything we could possibly install! At any point in this example you could have also just stopped adding things to the base and added the `atom` folder, such as after the `stock` step or `graphics` step. In this manner you can customize/choose what you want to come with Atom.

### Registry

You may have noticed the odd `localhost:5000` prepended to the base whenever we wanted to build from something we had already built. This is because when we build with `docker buildx` we are within a container running `buildx` which doesn't have access to the local image store on your machine. While images can be loaded from `buildx` into your local machine using the `--load` flag, there's no way to use a local image on your machine in a `FROM` step in a Dockerfile.

This is a challenge, since our whole concept of this build is to make a bunch of intermediate images and chain them together. We could be constantly pushing the builds to/from Dockerhub but this would be both time-consuming and network-heavy which we don't really want.

Thankfully, we can run a Docker registry fairly easily locally! In this folder you'll find [`docker-compose-registry.yml`](docker-compose-registry.yml) which boots up a local copy of a Docker v2 registry. It uses your host filesystem to back the registry and thereby allows the images stored in the registry to persist between boots. These are stored in the [`registry`](registry) folder. We can technically put the registry on any port, but the default is `5000` so we stuck with that. The port can be modified in the docker-compose if you'd like.

The `build.sh` script will automatically spin up and spin down the registry and you shouldn't have to think/worry about it too much. However, if you'd like to pull a build from your local registry to debug/analyze you can always spin it up using

```
docker-compose -f docker-compose-registry.yml up -d
```

And spin it down using

```
docker-compose -f docker-compose-registry down
```

It is recommended not to spin it down while the `build.sh` script is running since it will cause it to fail.

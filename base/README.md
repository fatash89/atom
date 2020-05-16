# Atom Base Image

This section contains documentation on the Atom base images and how to build/use them.

The Atom base image consists of, at the very least, all of the libraries required for a particular Atom language client to function. At the moment, all language clients share the same base, but this may not be the case in the future.

This image is provided as a convenience and due to the requirement of Atom needing to cross-compile for ARM, typically builds all packages from source unless they're commonly available for both platforms. This gives us better continuity between testing/development on AMD64 systems and deployment on ARM systems such as the Raspberry Pi, Nvidia Jetson/Xavier line of products.

## Dockerfiles

The base image is built through a series of Dockerfiles. This is designed as such for a few reasons:

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

## Base Options

All of the dependencies that are necessary to run a basic Atom element have their Dockerfiles found in the `stock` folder. The base image built from the resulting chain of these Dockerfiles is `stock`. All additional things/nice-to-haves are broken out into groups in their own folder. The table below explains
the options and what's in each.

| Option | Description |
|--------|-------------|
| `stock` | Contains everything needed to run Atom |
| `extras` | Contains additional libraries that many elements may need such as `opencv`, etc. |
| `graphics` | Contains everything needed to use graphics in Atom such as `opengl`, a VNC, etc. |

## Building

You'll need Docker version 19.0.3 or greater in order to build Atom images. This is because we use the new experimental `buildx` builder in order to get consistent results on ARM and AMD platforms.

### Script

Since the build is a chain of Dockerfiles, we use a bash script to perform the build and produce the final output for any base image

The build takes positional arguments as seen in the table below:

| Position | Description | Examples |
|----------|-------------|---------|
| 1 | Platform | `amd64` or `aarch64` |
| 2 | Docker repo for the resulting and intermediate images | `elementaryrobotics/atom`, etc. |
| 3 | Docker Tag for the resulting image  | Tag for the final output of the build process | `base-stock-descriptor`, etc. |
| 4 | Original Image/OS we should build Atom atop | `debian:buster-slim`, etc. |
| 5 | Which base option we should build. | `stock`, etc. See table above |

#### `stock`

An example invocation for `stock` and `amd64` can be found below:
```
./build_base.sh amd64 elementaryrobotics/atom build-base debian:buster-slim stock
```

This will, for example, after some amount of time, produce an image named:
```
elementaryrobotics/atom:build-base-stock-amd64
```

Under the hood, when running this script, there's a lot going on. What's happening is:

1. We enable and set up using the experimental `buildx` builder. If you've
already done this on your machine it's OK and essentially a no-op.
2. We spin up a local Docker image registry on `localhost:5000` to store the
intermediate buildimages. Normally, if just using `docker build` we wouldn't
have to do this, but `docker buildx build` runs completely isolated from the
local docker images on your machine and can't import them using the `FROM`
command. As such, we then export each intermediate build stage to this local
registry so that the `FROM` command can pull them from somewhere and we don't
have to push them to/from our actual Dockerhub repo. This registry is set up
to host the image data on your machine in the `registry` folder so that it
persists run-to-run which is nice.
3. We loop over the Dockeriles in the `stock` folder and build them. If there
are build arguments, we use those. After building each image, we push it to
`localhost:5000/elementaryrobotics/atom:base-<Dockerfile full name>-<platform>`.
The following Dockerfile to be built will be `FROM` the image built in the
previous run.
4. At the end we `docker pull` the final version from the registry at `localhost:5000`
onto your machine and tag it as commanded in the `build_base_stock.sh` invocation.

#### `extras`

The `extras` base can be built very similar to the `stock` base, with a few key differences:

1. The original image, argument 4 of the script, should be the output of a stock build.
2. We should specify the `extras` folder

For example, if we wanted to build the `extras` base atop the `stock` base from the previous example, we could with:

```
./build_base.sh amd64 elementaryrobotics/atom build-base localhost:5000/elementaryrobotics/atom:build-base-stock-amd64 extras
```

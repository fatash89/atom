# Atom Base Image

This section contains documentation on the Atom base images and how to build/use them.

The Atom base image consists of, at the very least, all of the libraries required for a particular Atom language client to function. At the moment, all language clients share the same base, but this may not be the case in the future.

This image is provided as a convenience and due to the requirement of Atom needing to cross-compile for ARM, typically builds all packages from source unless they're commonly available for both platforms. This gives us better continuity between testing/development on AMD64 systems and deployment on ARM systems such as the Raspberry Pi, Nvidia Jetson/Xavier line of products.

## Dockerfiles

The base image is built through a series of Dockerfiles. This is designed as such for a few reasons:

1. All parts may not be the same across all use cases. Mathematical acceleration libraries like BLAS, for example, will be highly platform-dependent to get the same results. We want to be able to switch out Dockerfiles/Dockerfile arguments here and rebuild just this piece without needing to change other parts of the build. We also get better caching performance/build sharability this way as parts that builds have in common can be shared and not rebuilt needlessly.
2. Cross-compiling for ARM on AMD64 machines uses the QEMU similator. This is quite awesome that it's possible, but quite slow. As we run build jobs on our CI/CD servers, slower builds cost more money so we want to minimize the time spent rebuilding the same thing. Further, CircleCI in particular has a 5-hour single job limit which all of the dependencies for Atom don't fit into on a standard-sized machine (large). As bumping up to the next resource class on CircleCI is 10x the cost, it's easier/better to break the job up into multiple sections.

## Stock and Variants

All of the dependencies that are necessary to run a basic Atom element have their Dockerfiles found in the `stock` folder. The base image built from the resulting chain of these Dockerfiles is `stock`. All additional things/nice-to-haves for elements such as `opencv`, `opengl`, etc. can be found in the `variant` folder.

## Building

You'll need Docker version 19.0.3 or greater in order to build Atom images. This is because we use the new experimental `buildx` builder in order to get consistent results on ARM and AMD platforms.

### Stock

Since the build is a chain of Dockerfiles, we use a bash script to perform the build and produce the final output for the stock base image.

The build takes positional arguments as seen in the table below:

| Position | Description | Examples |
|----------|-------------|---------|
| 1 | Platform | `amd64` or `aarch64` |
| 2 | Docker repo for the resulting and intermediate images | `elementaryrobotics/atom`, etc. |
| 3 | Docker Tag for the resulting image  | Tag for the final output of the build process | `base-stock-descriptor`, etc. |
| 4 | Original Image/OS we should build Atom atop | `debian:buster-slim`, etc. |

An example invocation for `amd64` can be found below:
```
./build_base_stock.sh amd64 elementaryrobotics/atom build-base-experimental debian:buster-slim
```

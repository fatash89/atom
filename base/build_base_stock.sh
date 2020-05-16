#!/bin/bash

# Turn on the Docker experimental CLI
export DOCKER_CLI_EXPERIMENTAL=enabled

# Enable ARM support
docker run --rm --privileged docker/binfmt:66f9012c56a8316f9244ffd7622d7c21c1f6f28d

# Note that we're starting with the original base image
CURRENT_BASE=${4}

# Now, we want to loop over the Dockerfiles in the stock
#   folder.
for dockerfile in stock/*
do
    # Get the name of the new image
    NEW_IMAGE=${2}:base-${dockerfile##*/}

    # Do the build
    docker buildx build  \
        --platform=linux/${1}  \
        -t ${NEW_IMAGE}  \
        --progress=plain  \
        --load  \
        --build-arg BASE_IMAGE=${CURRENT_BASE} \
        ../.

    # Move the current base
    CURRENT_BASE=${NEW_IMAGE}
done

# Do the final tag
docker tag ${CURRENT_BASE} ${2}:${3}

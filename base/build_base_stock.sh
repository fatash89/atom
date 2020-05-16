#!/bin/bash

# Docker command. For debug, switch this to "echo docker"
#   to see the sequence of commands that will be run without
#   having to actually run them
DOCKER_CMD="echo docker"

# Turn on the Docker experimental CLI
export DOCKER_CLI_EXPERIMENTAL=enabled

# Enable ARM support
${DOCKER_CMD} run --rm --privileged docker/binfmt:66f9012c56a8316f9244ffd7622d7c21c1f6f28d

# Note that we're starting with the original base image
CURRENT_BASE=${4}

# Now, we want to loop over the Dockerfiles in the stock
#   folder.
for dockerfile in stock/*Dockerfile*
do
    # Get the name of the new image
    NEW_IMAGE=${2}:base-${dockerfile##*/}

    # Check to see if we have custom args for this build
    ARGS_FILE=stock/${dockerfile##*/*Dockerfile-}-${1}-args
    ADDITIONAL_ARGS=""
    if [ -f ${ARGS_FILE} ]; then
        while read arg; do
            ADDITIONAL_ARGS+="--build-arg ${arg}"
        done < ${ARGS_FILE}
    fi

    # Do the build
    ${DOCKER_CMD} buildx build  \
        -f ${dockerfile} \
        --platform=linux/${1}  \
        -t ${NEW_IMAGE}  \
        --progress=plain  \
        --load  \
        --build-arg BASE_IMAGE=${CURRENT_BASE} \
        ${ADDITIONAL_ARGS} \
        ../.

    # Move the current base
    CURRENT_BASE=${NEW_IMAGE}
done

# Do the final tag
${DOCKER_CMD} tag ${CURRENT_BASE} ${2}:${3}

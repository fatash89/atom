#!/bin/bash

# Docker command. For debug, comment this out and it
#   won't run the build.
RUN_BUILD="y"

# Docker-compose file to run the local registry
REGISTRY_COMPOSE=docker-compose-registry.yml

# Launch the registry
docker-compose -f ${REGISTRY_COMPOSE} up -d

# Turn on the Docker experimental CLI
export DOCKER_CLI_EXPERIMENTAL=enabled

# Enable ARM support
docker run --rm --privileged docker/binfmt:66f9012c56a8316f9244ffd7622d7c21c1f6f28d

# Create the builder and use the local network to talk
#   to the registry
docker buildx create --use --name basebuilder --driver-opt network=host
docker buildx inspect --bootstrap

# Note that we're starting with the original base image
CURRENT_BASE=${4}

# Now, we want to loop over the Dockerfiles in the stock
#   folder.
for dockerfile in stock/*Dockerfile*
do
    # Get the name of the new image
    NEW_IMAGE=localhost:5000/${2}:base-${dockerfile##*/}-${1}

    # Check to see if we have custom args for this build
    ARGS_FILE=stock/${dockerfile##*/*Dockerfile-}-${1}-args
    ADDITIONAL_ARGS=""
    if [ -f ${ARGS_FILE} ]; then
        while read arg; do
            ADDITIONAL_ARGS+="--build-arg ${arg}"
        done < ${ARGS_FILE}
    fi

    # Do the build
    CMD_STRING="docker buildx build  \
        -f ${dockerfile} \
        --platform=linux/${1}  \
        -t ${NEW_IMAGE}  \
        --progress=plain  \
        --push \
        --build-arg BASE_IMAGE=${CURRENT_BASE} \
        --pull=false \
        ${ADDITIONAL_ARGS} \
        ../."
    echo ${CMD_STRING}
    if [ ${RUN_BUILD} == "y" ]; then
        ${CMD_STRING}
    fi

    # Check the exit status
    if [ $? != "0" ]; then
        echo "Build of ${dockerfile} failed! Exiting"
        exit 1
    fi

    # Move the current base
    CURRENT_BASE=${NEW_IMAGE}
done

# Pull the image
docker pull ${CURRENT_BASE}

# Do the final tag
TAG_CMD="docker tag ${CURRENT_BASE} ${2}:${3}-${1}"
echo ${TAG_CMD}
${TAG_CMD}

# Take down the registry
docker-compose -f ${REGISTRY_COMPOSE} down

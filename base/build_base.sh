#!/bin/bash

# Docker command. For debug, comment this out and it
#   won't run the build.
RUN_BUILD="y"

# Docker-compose file to run the local registry
REGISTRY_COMPOSE=docker-compose-registry.yml
REGISTRY_LOCATION=localhost:5000

#
# Set up
#

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

#
# Build Dockerfiles
#

# Note that we're starting with the original base image
CURRENT_BASE=${4}
docker pull ${CURRENT_BASE}

# Now, we want to loop over the Dockerfiles in the ${5} folder
for dockerfile in ${5}/*Dockerfile*
do
    # Get the name of the new image
    NEW_IMAGE=${REGISTRY_LOCATION}/${2}:base-${dockerfile##*/}-${5}-${1}

    # Check to see if we have custom args for this build
    ARGS_FILE=${5}/${dockerfile##*/*Dockerfile-}-${1}-args
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
        --pull=true \
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

#
# Minimize
#

# Now, we want to minimize
ARGS_FILE=${5}/minimize-${1}-args
ADDITIONAL_ARGS=""
if [ -f ${ARGS_FILE} ]; then
    while read arg; do
        ADDITIONAL_ARGS+="--build-arg ${arg} "
    done < ${ARGS_FILE}
fi

# Package all of the dependencies. This happens
#   in a single stage and will create a tarball within
#   the container at /minimized.tar.gz.
NEW_IMAGE=${REGISTRY_LOCATION}/${2}:base-minimize-${5}-${1}
CMD_STRING="docker buildx build  \
    -f utilities/01-Dockerfile-minimize \
    --platform=linux/${1}  \
    -t ${NEW_IMAGE}  \
    --progress=plain  \
    --push \
    --build-arg BASE_IMAGE=${CURRENT_BASE} \
    --build-arg PRODUCTION_IMAGE=${4}
    --pull=true \
    --target=with-deps \
    ${ADDITIONAL_ARGS} \
    utilities/."
echo ${CMD_STRING}
if [ ${RUN_BUILD} == "y" ]; then
    ${CMD_STRING}
fi

# Check the exit status
if [ $? != "0" ]; then
    echo "Build of minimized Dockerfile failed! Exiting"
    exit 1
fi

# Need to launch the minimized container, copy the tarball
#   into the utilities folder and shut down the container
echo "Copying minimized tarball out"
docker pull ${NEW_IMAGE}
docker container create --name minimized ${NEW_IMAGE}
docker container cp minimized:/minimized.tar.gz utilities/minimized.tar.gz
docker container rm -f minimized

# Now, we want to production-ize
ARGS_FILE=${5}/production-${1}-args
ADDITIONAL_ARGS=""
if [ -f ${ARGS_FILE} ]; then
    while read arg; do
        ADDITIONAL_ARGS+="--build-arg ${arg} "
    done < ${ARGS_FILE}
fi

# Now we need to apply the minimized tarball to our final
#   production image
NEW_IMAGE=${REGISTRY_LOCATION}/${2}:base-production-${5}-${1}
CMD_STRING="docker buildx build  \
    -f utilities/02-Dockerfile-production \
    --platform=linux/${1}  \
    -t ${NEW_IMAGE}  \
    --progress=plain  \
    --push \
    --build-arg PRODUCTION_IMAGE=${4}
    --pull=true \
    --target=production \
    ${ADDITIONAL_ARGS} \
    utilities/."
echo ${CMD_STRING}
if [ ${RUN_BUILD} == "y" ]; then
    ${CMD_STRING}
fi

# Check the exit status
if [ $? != "0" ]; then
    echo "Build of production Dockerfile failed! Exiting"
    exit 1
fi

# Note the new base
CURRENT_BASE=${NEW_IMAGE}

#
# Package it up
#

# Note the final output tag
OUTPUT_TAG="${2}:${3}-${5}-${1}"

# Push the final tag to the registry
docker pull ${CURRENT_BASE}
docker tag ${CURRENT_BASE} ${REGISTRY_LOCATION}/${OUTPUT_TAG}
docker push ${REGISTRY_LOCATION}/${OUTPUT_TAG}

# Do the final tag
TAG_CMD="docker tag ${CURRENT_BASE} ${OUTPUT_TAG}"
echo ${TAG_CMD}
${TAG_CMD}

# Take down the registry
docker-compose -f ${REGISTRY_COMPOSE} down

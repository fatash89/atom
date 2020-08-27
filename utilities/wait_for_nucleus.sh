#!/bin/bash
#
# wait_for_nucleus.sh
#   command-line script that will wait for the nucleus
#   to be up and accessible based on the environment
#   variables set.
#

REDIS_CLI_BIN="/usr/local/bin/redis-cli"
REDIS_CLI_CMD="ping"
REDIS_CLI_EXPECTED_RESPONSE="PONG"
TIME_WAIT=1

function wait_for_redis {
    echo "Waiting for redis ${1} with args ${2} to become available"

    while true; do
        resp=$(${REDIS_CLI_BIN} ${2} ${REDIS_CLI_CMD})
        if [[ ${resp} == ${REDIS_CLI_EXPECTED_RESPONSE} ]]; then
            echo "${1} redis is up!"
            break
        else
            echo "${1} redis not up, waiting ${TIME_WAIT} seconds"
            sleep ${TIME_WAIT}
        fi
    done
}

# If we're connecting remotely to the nucleus
if [[ ! -z ${ATOM_NUCLEUS_HOST} ]]; then
    wait_for_redis "nucleus" "-h ${ATOM_NUCLEUS_HOST} -p ${ATOM_NUCLEUS_PORT}"
else
    wait_for_redis "nucleus" "-s ${ATOM_NUCLEUS_SOCKET}"
fi

# If we're connecting remotely to the nucleus
if [[ ! -z ${ATOM_METRICS_HOST} ]]; then
    wait_for_redis "metrics" "-h ${ATOM_METRICS_HOST} -p ${ATOM_METRICS_PORT}"
else
    wait_for_redis "metrics" "-s ${ATOM_METRICS_SOCKET}"
fi

# If we've been passed any args, we should run that
if [ $# -gt 0 ] ; then
    echo "Atom ready! Running '${@}'"
    exec "${@}"
fi

#!/bin/sh

#
# run.sh: Run formatting + checks
#

# Show the commands we're running
set -o xtrace

# If we should format
if [[ ! -z ${DO_FORMAT} ]]; then

    # If we're using black
    if [[ ! -z ${FORMAT_BLACK} ]]; then
        /usr/local/bin/black --exclude="${BLACK_EXCLUDE}" ${CODE_DIR} || exit 1
    # No other formatters supported at the moment
    else
        echo "No formatter specified!"
    fi
fi

# If we should check
if [[ ! -z ${DO_CHECK} ]]; then

    # If we're using black
    if [[ ! -z ${FORMAT_BLACK} ]]; then
        /usr/local/bin/black --check --exclude="${BLACK_EXCLUDE}" ${CODE_DIR} || exit 1
    fi

    # Always run flake8
    /usr/local/bin/flake8 --config=/usr/local/lib/.flake8 --exclude=${FLAKE8_EXCLUDE} ${CODE_DIR} || exit 1
fi

# If we should hang at the end
if [[ ! -z ${DO_HANG} ]]; then
    tail -f /dev/null
fi

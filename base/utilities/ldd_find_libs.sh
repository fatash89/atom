#!/bin/bash

#
# ldd_find_libs: Find the libraries needed by all things so
#   that we can copy them over
#

DEFAULT_LIB_LOCATIONS="/usr/local/lib/*.so* /usr/local/lib/*.a* /usr/local/bin"

LDD_CMD=""
for location in DEFAULT_LIB_LOCATIONS; do
    LDD_CMD+=$(ls ${location})
done

for location in ADDITIONAL_LIB_LOCATIONS; do
    LDD_CMD+=$(ls ${location})
done

# Run the command
echo "About to run LDD on ${LDD_CMD}"
ldd ${LDD_CMD} | grep "=> /" | awk '{print $3}' | sort -u > /tmp/required_libs.txt

# Note the required libraries
echo "Required libs"
cat /tmp/required_libs.txt

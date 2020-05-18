#!/bin/bash

#
# ldd_find_libs: Find the libraries needed by all things so
#   that we can copy them over
#

DEFAULT_LIB_LOCATIONS="/usr/local/lib/*.so* /usr/local/lib/*.a* /usr/local/bin/* /usr/bin/python*"

LDD_CMD=""
for location in ${DEFAULT_LIB_LOCATIONS}; do
    LDD_CMD+="$(ls --format=commas ${location}) "
done

while read location; do
    LDD_CMD+="$(ls --format=commas ${location}) "
done < /minimize/additional_libs.txt

# Run the command
LDD_CMD=$(echo ${LDD_CMD} | sed "s/,/ /g" )
echo "About to run LDD on ${LDD_CMD}"
ldd ${LDD_CMD} | grep "=> /" | awk '{print $3}' | sort -u > /tmp/required_libs.txt

# Note the required libraries
echo "Required libs"
cat /tmp/required_libs.txt

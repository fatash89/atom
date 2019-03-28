#!/bin/bash

DOCS_DIR="/docs"
DOCS_FILE=${DOCS_DIR}/"elements.md"

mkdir -p ${DOCS_DIR}

# Generate elements markdown file from sub files
echo "# Element Documentation" > ${DOCS_FILE}
ls -1 /elements_docs/*.md | sort | while read fn;
    do cat "$fn" >> ${DOCS_FILE}; echo "" >> ${DOCS_FILE}; done

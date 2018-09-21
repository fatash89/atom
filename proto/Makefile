################################################################################
#
# Makefile for proto. Builds all of the proto files into
#	their language-specific sources
#
################################################################################

curr_file := $(abspath $(lastword $(MAKEFILE_LIST)))
CURR_DIR := $(patsubst %/Makefile,%,$(curr_file))

PROTOC_BIN:=${CURR_DIR}/../third-party/protobuf/build/bin/protoc

SKILLS_TO_BUILD:=\
    robot

BUILD_DIR:=${CURR_DIR}/build

LANGUAGE_DIRS:=\
	cpp \
	cs \
	java \
	js \
	objc \
	php \
	py \
	ruby

.DEFAULT_GOAL := all

.PHONY: all
all:
	@ $(foreach skill,${SKILLS_TO_BUILD},$(foreach lang,${LANGUAGE_DIRS},mkdir -p ${BUILD_DIR}/${skill}/${lang}))
	@ $(foreach skill,${SKILLS_TO_BUILD},(${PROTOC_BIN} --cpp_out=${BUILD_DIR}/${skill}/cpp --csharp_out=${BUILD_DIR}/${skill}/cs --java_out=${BUILD_DIR}/${skill}/java --js_out=${BUILD_DIR}/${skill}/java --objc_out=${BUILD_DIR}/${skill}/objc --php_out=${BUILD_DIR}/${skill}/php --python_out=${BUILD_DIR}/${skill}/py --ruby_out=${BUILD_DIR}/${skill}/ruby ${skill}/*.proto) || exit 1;)

.PHONY: clean
clean:
	rm -rf ${BUILD_DIR}

################################################################################
#
# Makefile for hiredis
#
################################################################################

curr_file := $(abspath $(lastword $(MAKEFILE_LIST)))
CURR_DIR := $(patsubst %/Makefile,%,$(curr_file))

LIB_DIR:=hiredis

# Check if submodule exists
SUBMODULE_EXISTS:="$(shell if [ -f ${LIB_DIR}/.git ]; then echo y; else echo n; fi )"
ifneq (${SUBMODULE_EXISTS},"y")
$(error "Submodule does not exist")
endif

INSTALL_DIR:=${CURR_DIR}/build

.DEFAULT_GOAL := all

.PHONY: all
all:
	cd ${LIB_DIR} && make -j8

.PHONY: install
install:
	mkdir -p ${INSTALL_DIR}
	cd ${LIB_DIR} && make PREFIX=${INSTALL_DIR} install

.PHONY: clean
clean:
	cd ${LIB_DIR} && make clean || exit 0
	cd ${LIB_DIR} && git clean -d -f -x && git reset --hard
	rm -rf ${INSTALL_DIR}

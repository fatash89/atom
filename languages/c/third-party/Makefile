################################################################################
#
# makefile for robot element third-party libraries
#
################################################################################

.DEFAULT_GOAL := all

# List of all libraries to build with this general Makefile. Should
#	be in dependency order with higher in the list meaning no dependencies
#	and anything in the list with dependencies beneath what it depends on
LIBRARIES:= \
    hiredis \
    msgpack-c

.PHONY: all
all:
	@ $(foreach lib,${LIBRARIES},($(MAKE) -C $(lib)&& $(MAKE) -C $(lib) install) || exit 1;)

.PHONY: clean
clean:
	@ $(foreach lib,${LIBRARIES},($(MAKE) -C $(lib) clean) || exit 1;)

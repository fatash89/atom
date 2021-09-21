#!/bin/bash

MAJOR_VER=1
MINOR_VER=0
LIB_NAME=ershmem

PY_PREFIX=py_
C_LINKAGE_DIR=c_linkage
CPP_LINKAGE_DIR=cpp_linkage

CPP_SRCS=$(wildcard *.cpp)
CPP_HDRS=$(wildcard *.h)
C_LINKAGE_OBJS=$(patsubst %.cpp,$(C_LINKAGE_DIR)/%.o, $(wildcard er_*.cpp))
CPP_LINKAGE_OBJS=$(patsubst %.cpp,$(CPP_LINKAGE_DIR)/%.o, $(wildcard er_*.cpp))
PY_CPP_LINKAGE_OBJS=$(patsubst %.cpp,$(CPP_LINKAGE_DIR)/%.o, $(wildcard $(PY_PREFIX)*.cpp))

TARGET_LIB_SONAME   = lib$(LIB_NAME).so.$(MAJOR_VER)
TARGET_PYLIB_SONAME = $(LIB_NAME)

CXXFLAGS = -std=c++11 -fPIC -c
PYBIND_CXXFLAGS = $(python3-config --includes) -Ipybind11/include -I/usr/include/python3.8/

LD_FLAGS = -lrt -lboost_date_time
ifeq ($(DEBUG), on)
	CXXFLAGS += -g
endif

all: dirs $(TARGET_LIB_SONAME) $(TARGET_PYLIB_SONAME)

dirs:
	@rm -rf $(C_LINKAGE_DIR) $(CPP_LINKAGE_DIR)
	@mkdir $(C_LINKAGE_DIR)
	@mkdir $(CPP_LINKAGE_DIR)

$(C_LINKAGE_DIR)/%.o:%.cpp
	$(CXX) $(CXXFLAGS) -DER_C_LINKAGE $? -o $@

$(CPP_LINKAGE_DIR)/%.o:%.cpp
	$(CXX) $(PYBIND_CXXFLAGS) $(CXXFLAGS) $? -o $@

$(TARGET_LIB_SONAME): $(C_LINKAGE_OBJS)
	$(CXX) -shared -Wl,-soname,$@ -o $(TARGET_LIB_SONAME).$(MINOR_VER) $(C_LINKAGE_OBJS) $(LD_FLAGS)
	ln -s $(TARGET_LIB_SONAME).$(MINOR_VER) $@
	ln -s $@ lib$(LIB_NAME).so

$(TARGET_PYLIB_SONAME): $(CPP_LINKAGE_OBJS) $(PY_CPP_LINKAGE_OBJS)
	$(CXX) -Wall -shared -o $(TARGET_PYLIB_SONAME)$(shell python3-config --extension-suffix) $(CPP_LINKAGE_OBJS) $(PY_CPP_LINKAGE_OBJS) $(LD_FLAGS)

.PHONY: clean
clean:
	@rm -rf $(C_LINKAGE_DIR) $(CPP_LINKAGE_DIR)
	@rm -f $(TARGET_LIB_SONAME) \
		   $(TARGET_LIB_SONAME).$(MINOR_VER) \
		   lib$(LIB_NAME).so $(TARGET_PYLIB_SONAME)$(shell python3-config --extension-suffix)

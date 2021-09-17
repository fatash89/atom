#!/bin/bash

MAJOR_VER=1
MINOR_VER=0
LIB_NAME=ershmem

CPP_SRCS=$(wildcard *.cpp)
CPP_HDRS=$(wildcard *.h)
CPP_OBJS=$(patsubst %.cpp,%.o, $(wildcard *.cpp))

TARGET_LIB_SONAME   = lib$(LIB_NAME).so.$(MAJOR_VER)
TARGET_PYLIB_SONAME = libpy$(LIB_NAME).so.$(MAJOR_VER)

CXXFLAGS = -std=c++11 -fPIC -c

ifeq ($(DEBUG), on)
	CXXFLAGS += -g
endif

all: $(CPP_OBJS) $(TARGET_LIB_SONAME)

%.o:%.cpp
	$(CXX) $(CXXFLAGS) $? -o $@

$(TARGET_LIB_SONAME): $(CPP_OBJS)
	$(CXX) -shared -Wl,-soname,$@ -o $(TARGET_LIB_SONAME).$(MINOR_VER) $(CPP_OBJS)
	ln -s $(TARGET_LIB_SONAME).$(MINOR_VER) $@
	ln -s $@ lib$(LIB_NAME).so

.PHONY: clean
clean:
	@rm -f $(CPP_OBJS) $(TARGET_LIB_SONAME) $(TARGET_LIB_SONAME).$(MINOR_VER) lib$(LIB_NAME).so

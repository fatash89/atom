#!/bin/bash

CPP_SRCS=$(wildcard *.cpp)
CPP_OBJS=$(patsubst %.cpp,%.o,$(CPP_SRCS))

APP_NAME=test_cpp_app

CXXFLAGS= -I../lib

LDFLAGS= -L../lib -lershmem

all: $(CPP_OBJS)
	$(CXX) -o $(APP_NAME) $(CPP_OBJS) $(LDFLAGS)

%.o:%.cpp
	$(CXX) $(CXXFLAGS) -c $? -o $@

.PHONY: clean
clean:
	@rm -f $(APP_NAME) $(CPP_OBJS)

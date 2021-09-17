#!/bin/bash

CPP_SRCS=$(wildcard *.cpp)
CPP_OBJS=$(patsubst %.cpp,%.o,$(CPP_SRCS))

APP_NAME=test_cpp_app

CXXFLAGS= -std=c++11 -I../lib

LDFLAGS= -L../lib -lershmem -lrt -lboost_date_time

all: $(CPP_OBJS)
	$(CXX) -o $(APP_NAME) $(CPP_OBJS) $(LDFLAGS)

%.o:%.cpp
	$(CXX) $(CXXFLAGS) -c $? -o $@

.PHONY: clean
clean:
	@rm -f $(APP_NAME) $(CPP_OBJS)

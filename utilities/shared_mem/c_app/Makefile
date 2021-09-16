#!/bin/bash

C_SRCS=$(wildcard *.c)
C_OBJS=$(patsubst %.c,%.o,$(C_SRCS))

APP_NAME=test_c_app

CFLAGS= -I../lib

LDFLAGS= -L../lib -lershmem

all: $(C_OBJS)
	$(CC) -o $(APP_NAME) $(C_OBJS) $(LDFLAGS)

%.o:%.c
	$(CC) $(CFLAGS) -c $? -o $@

.PHONY: clean
clean:
	@rm -f $(APP_NAME) $(C_OBJS)

////////////////////////////////////////////////////////////////////////////////
//
//  @file element_command_server.h
//
//  @brief Header for the element command server implementation
//
//  @copy 2018 Elementary Robotics. All rights reserved.
//
////////////////////////////////////////////////////////////////////////////////

#ifndef __ATOM_ELEMENT_COMMAND_SERVER_H
#define __ATOM_ELEMENT_COMMAND_SERVER_H

#ifdef __cplusplus
 extern "C" {
#endif

#include "atom.h"
#include "redis.h"

// Forward declaration of the element struct
struct element;

// How many bins to put in the element command hashtable. MUST
//	be a power of 2
#define ELEMENT_COMMAND_HASH_N_BINS 256
#if ((ELEMENT_COMMAND_HASH_N_BINS & (ELEMENT_COMMAND_HASH_N_BINS - 1)) != 0)
 	#error "ELEMENT_COMMAND_HASH_N_BINS is not a power of 2!"
#endif

// Element command. Mapping between command name
//	and a function pointer to call with the data when the
//	command is passed to the element. Needs to be a linked list
//	since it will be part of a hashtable used to map incoming
//	commands to their proper callbacks.
struct element_command {
	char *name;
	int (*cb)(
		uint8_t *data,
		size_t data_len,
		uint8_t **response,
		size_t *response_len,
		char **err_str);
	int timeout;
	struct element_command *next;
};

// Adds a command to the element's set of implemented commands. The command
//	has a name, a callback, and a timeout. The timeout is sent back to the
//	caller in the ACK packet initially after receiving the command
//	s.t. they know how long to wait for the response before timing out
bool element_command_add(
	struct element *elem,
	const char *command,
	int (*cb)(
		uint8_t *data,
		size_t data_len,
		uint8_t **response,
		size_t *response_len,
		char **error_str),
	int timeout);

// Runs the command monitoring loop. Will perform XREADs on the command
//	stream and process all commands. If loop is false will only do the XREAD
//	once. If timeout is nonzero will return if we don't get a command
//	within timeout ms.
enum atom_error_t element_command_loop(
	redisContext *ctx,
	struct element *elem,
	bool loop,
	int timeout);

#ifdef __cplusplus
 }
#endif

#endif // __ATOM_ELEMENT_COMMAND_SERVER_H

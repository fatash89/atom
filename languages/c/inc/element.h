////////////////////////////////////////////////////////////////////////////////
//
//  @file element.h
//
//  @brief Header for the element implementation
//
//  @copy 2018 Elementary Robotics. All rights reserved.
//
////////////////////////////////////////////////////////////////////////////////

#ifndef __ATOM_ELEMENT_H
#define __ATOM_ELEMENT_H

#ifdef __cplusplus
 extern "C" {
#endif

#include "atom.h"
#include "redis.h"
#include "element_command_send.h"
#include "element_command_server.h"
#include "element_entry_read.h"
#include "element_entry_write.h"

// Element's name
struct _element_name {
	char *str;
	size_t len;
};

// Response stream
struct _element_response_info {
	char *stream;
	char last_id[STREAM_ID_BUFFLEN];
};

// Command stream
struct _element_command_info {
	char *stream;
	char last_id[STREAM_ID_BUFFLEN];
	redisContext *ctx;
	struct element_command *hash[ELEMENT_COMMAND_HASH_N_BINS];
};

// Element itself. Element consists of a name, command stream
//	and response stream.
struct element {
	// Element's name
	struct _element_name name;
	// Response stream
	struct _element_response_info response;
	// Command stream
	struct _element_command_info command;
};

// Initializes an element of the given name.
struct element *element_init(
	redisContext *ctx,
	const char *name);

// Cleans up an element of the given name
void element_cleanup(
	redisContext *ctx,
	struct element *elem);

#ifdef __cplusplus
 }
#endif

#endif // __ATOM_ELEMENT_H

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

// Skill itself. Skill consists of a client, a command stream
//	and an ID for the command stream. Since the client
//	already needs a name and name len we'll not store an additional
//	name within the skill, though I admit this is a bit confusing.
struct element {

	// Element's name
	struct _element_name {
		char *str;
		size_t len;
	} name;

	// Response stream
	struct _element_response_info {
		char *stream;
		char last_id[STREAM_ID_BUFFLEN];
	} response;

	// Command stream
	struct _element_command_info {
		char *stream;
		char last_id[STREAM_ID_BUFFLEN];
		redisContext *ctx;
		struct element_command *hash[ELEMENT_COMMAND_HASH_N_BINS];
	} command;
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

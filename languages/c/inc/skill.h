////////////////////////////////////////////////////////////////////////////////
//
//  @file skill.h
//
//  @brief Header for the skill implementation
//
//  @copy 2018 Elementary Robotics. All rights reserved.
//
////////////////////////////////////////////////////////////////////////////////

#ifndef __SKILLS_SKILL_H
#define __SKILLS_SKILL_H

#ifdef __cplusplus
 extern "C" {
#endif

#include "skills.h"
#include "redis.h"

// How many bins to put in the skill command hashtable. MUST
//	be a power of 2
#define SKILL_COMMAND_HASH_N_BINS 256
#if ((SKILL_COMMAND_HASH_N_BINS & (SKILL_COMMAND_HASH_N_BINS - 1)) != 0)
 	#error "SKILL_COMMAND_HASH_N_BINS is not a power of 2!"
#endif

// Skill command. Mapping between command name
//	and a function pointer to call with the data when the
//	command is passed to the skill. Needs to be a linked list
//	since it will be part of a hashtable used to map incoming
//	commands to their proper callbacks.
struct skill_command {
	char *name;
	int (*cb)(
		uint8_t *data,
		size_t data_len,
		uint8_t **response,
		size_t *response_len,
		char **err_str);
	int timeout;
	struct skill_command *next;
};

// Skill itself. Skill consists of a client, a command stream
//	and an ID for the command stream. Since the client
//	already needs a name and name len we'll not store an additional
//	name within the skill, though I admit this is a bit confusing.
struct skill {
	struct client *client;
	char *command_stream;
	char command_last_id[STREAM_ID_BUFFLEN];
	struct skill_command *command_hash[SKILL_COMMAND_HASH_N_BINS];
	redisContext *resp_ctx;
};

// Stream struct. Will allocate the memory for the XADD infos
//	and initialize the stream for the droplets. Infos will be
//	allocated to hold some more info than the user requests
//	s.t. we can throw a timestamp and/or other things on there
struct skill_stream {
	struct redis_xadd_info *droplet_items;
	size_t n_droplet_items;
	char stream[STREAM_ID_BUFFLEN];
};

// Initializes a skill of the given name.
struct skill *skill_init(
	redisContext *ctx,
	const char *name);

// Cleans up a client of the given name.
void skill_cleanup(
	redisContext *ctx,
	struct skill *skl);

// Adds a command to the skill's set of implemented commands. The command
//	has a name, a callback, and a timeout. The timeout is sent back to the
//	caller in the ACK packet initially after receiving the command
//	s.t. they know how long to wait for the response before timing out
bool skill_add_command(
	struct skill *skl,
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
enum skills_error_t skill_command_loop(
	redisContext *ctx,
	struct skill *skl,
	bool loop,
	int timeout);

// Initializes a stream. Once this is done
//	once, at startup, it will be quite lightweight
//	to update and publish the droplet.
struct skill_stream *skill_init_stream(
	redisContext *ctx,
	struct skill *skl,
	const char *name,
	int n_keys);

// Cleans up a stream
void skill_cleanup_stream(
	redisContext *ctx,
	struct skill_stream *stream);

// Adds a droplet to a stream. User will fill out the
//	redis_xadd_info struct for now for the key:value pairs to
//	put in the stream. timestamp and maxlen can allow the
//	caller to put their own timestamp (in milliseconds) on the data
//	and maxlen controls the number of items that redis will
//	store internally
#define SKILL_DROPLET_DEFAULT_TIMESTAMP 0
#define SKILL_DROPLET_DEFAULT_MAXLEN 1024
enum skills_error_t skill_add_droplet(
	redisContext *ctx,
	struct skill_stream *stream,
	int timestamp,
	int maxlen);

#ifdef __cplusplus
 }
#endif

#endif // __SKILLS_SKILL_H

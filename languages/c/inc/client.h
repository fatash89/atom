////////////////////////////////////////////////////////////////////////////////
//
//  @file client.h
//
//  @brief Header for the client interface
//
//  @copy 2018 Elementary Robotics. All rights reserved.
//
////////////////////////////////////////////////////////////////////////////////

#ifndef __SKILLS_CLIENT_H
#define __SKILLS_CLIENT_H

#ifdef __cplusplus
 extern "C" {
#endif

#include <stdbool.h>
#include "redis.h"
#include "skills.h"

// Struct of client data. Not too much stored in here,
//	mainly just the string of its response stream and
//	the last ID seen on the stream s.t. when we loop on
//	responses we only get new data.
struct client {
	char *name;
	size_t name_len;
	char *response_stream;
	char response_last_id[STREAM_ID_BUFFLEN];
};

// Initializes a client of the given name.
struct client *client_init(
	redisContext *ctx,
	const char *name);

// Cleans up a client of the given name.
void client_cleanup(
	redisContext *ctx,
	struct client *clnt);

// Sends a command with the given data to the given stream. If
//	block is true, will wait until the response is completed. If response_cb
//	is also non-null then will call response_cb with the data in the response
//	s.t. the user can handle it.
enum skills_error_t client_send_command(
	redisContext *ctx,
	struct client *clnt,
	const char *stream,
	const char *command,
	uint8_t *data,
	size_t data_len,
	bool block,
	bool (*response_cb)(const uint8_t *response, size_t response_len));

// Struct that defines all information for processing a droplet:
//	1. The stream for the droplet
//	2. The keys expected in the droplet
//	3. The callback and data to pass to it when we get data for the droplet
//
//	This struct is used both for the droplet loop and for getting the N
//	most recent droplets.
struct client_droplet_info {
	const char *skill;
	const char *stream;
	struct redis_xread_kv_item *kv_items;
	size_t n_kv_items;
	void *user_data;
	bool (*response_cb)(
		const struct redis_xread_kv_item *kv_items,
		int n_kv_items,
		void *user_data);
};

// Allows a client to listen for all data on streams
enum skills_error_t client_droplet_loop(
	redisContext *ctx,
	struct client *clnt,
	struct client_droplet_info *info,
	size_t n_infos,
	bool loop,
	int timeout);

// Allows a client to get the N most recent items on a stream
enum skills_error_t client_droplet_get_n_most_recent(
	redisContext *ctx,
	struct client *clnt,
	struct client_droplet_info *info,
	size_t n);

#ifdef __cplusplus

 }
#endif

#endif // __SKILLS_CLIENT_H

////////////////////////////////////////////////////////////////////////////////
//
//  @file skills.c
//
//  @brief Implements shared functionality of skills
//
//  @copy 2018 Elementary Robotics. All rights reserved.
//
////////////////////////////////////////////////////////////////////////////////
#define _GNU_SOURCE
#include <stdio.h>
#include <hiredis/hiredis.h>
#include <pthread.h>
#include <stdbool.h>
#include <string.h>

#include "redis.h"
#include "skills.h"

// User data callback to send to the redis helper for finding skills
struct skills_find_skill_data {
	bool (*user_cb)(const char *key);
};

// User data callback to send to the redis helper for finding streams
struct skills_find_stream_data {
	bool (*user_cb)(const char *stream);
	size_t offset;
};

// User data callback to send to the redis helper for finding clients
struct skills_find_client_data {
	bool (*user_cb)(const char *key);
};

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Data callback for when we get a key that matches the skill
//			pattern. We want to strip off the prefix
//
////////////////////////////////////////////////////////////////////////////////
static bool skills_find_skill_data_cb(
	const char *key,
	void *user_data)
{
	struct skills_find_skill_data *data;

	// Get the data
	data = (struct skills_find_skill_data*)user_data;

	// Want to pass only the skill name along to the user callback
	return data->user_cb(
		&key[CONST_STRLEN(SKILLS_SKILL_COMMAND_STREAM_PREFIX)]);
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Calls a callback for each skill present in the system. User
//			can then do as they please. in the callback
//
////////////////////////////////////////////////////////////////////////////////
bool skills_get_all_skills(
	redisContext *ctx,
	bool (*data_cb)(const char *skill))
{
	struct skills_find_skill_data data;
	bool ret_val = false;

	// Set up the callback data s.t. when our cb is called we can pass
	//	it along to the user
	data.user_cb = data_cb;

	// Want to get all matching keys for the skill command stream prefix.
	//
	if (redis_get_matching_keys(ctx,
		SKILLS_SKILL_COMMAND_STREAM_PREFIX "*",
		skills_find_skill_data_cb,
		&data) < 0)
	{
		fprintf(stderr, "Failed to check for skills\n");
		goto done;
	}

	ret_val = true;

done:
	return ret_val;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Data callback for when we get a key that matches the stream
//			pattern. We want to strip off the prefix for the stream
//			and perhaps the stream name if one was passed
//
////////////////////////////////////////////////////////////////////////////////
static bool skills_find_stream_data_cb(
	const char *key,
	void *user_data)
{
	struct skills_find_stream_data *data;

	// Get the data
	data = (struct skills_find_stream_data*)user_data;

	// Want to pass only the skill name along to the user callback
	return data->user_cb(&key[data->offset]);
}


////////////////////////////////////////////////////////////////////////////////
//
//  @brief Calls a callback for each stream present in the system. Optional
//			skill parameter will allow the user to filter with only
//			streams for a particular skill if desired
//
////////////////////////////////////////////////////////////////////////////////
bool skills_get_all_streams(
	redisContext *ctx,
	bool (*data_cb)(const char *stream),
	const char *skill)
{
	struct skills_find_stream_data data;
	bool ret_val = false;
	char stream_prefix_buffer[128];

	// Set up the callback data s.t. when our cb is called we can pass
	//	it along to the user
	data.user_cb = data_cb;

	// Make the stream pattern
	if (skill != NULL) {
		data.offset = snprintf(stream_prefix_buffer, sizeof(stream_prefix_buffer),
			SKILLS_SKILL_DATA_STREAM_PREFIX "%s:*", skill) - 1;
	} else {
		strncpy(stream_prefix_buffer,
			SKILLS_SKILL_DATA_STREAM_PREFIX "*",
			sizeof(stream_prefix_buffer));
		data.offset = CONST_STRLEN(SKILLS_SKILL_DATA_STREAM_PREFIX);
	}

	// Want to get all matching keys for the skill command stream prefix.
	//
	if (redis_get_matching_keys(ctx,
		stream_prefix_buffer,
		skills_find_stream_data_cb,
		&data) < 0)
	{
		fprintf(stderr, "Failed to check for streams\n");
		goto done;
	}

	ret_val = true;

done:
	return ret_val;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Data callback for when we get a key that matches the client
//			pattern. We want to strip off the prefix
//
////////////////////////////////////////////////////////////////////////////////
static bool skills_find_client_data_cb(
	const char *key,
	void *user_data)
{
	struct skills_find_client_data *data;

	// Get the data
	data = (struct skills_find_client_data*)user_data;

	// Want to pass only the skill name along to the user callback
	return data->user_cb(
		&key[CONST_STRLEN(SKILLS_CLIENT_RESPONSE_STREAM_PREFIX)]);
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Calls a callback for each skill present in the system. User
//			can then do as they please. in the callback
//
////////////////////////////////////////////////////////////////////////////////
bool skills_get_all_clients(
	redisContext *ctx,
	bool (*data_cb)(const char *skill))
{
	struct skills_find_client_data data;
	bool ret_val = false;

	// Set up the callback data s.t. when our cb is called we can pass
	//	it along to the user
	data.user_cb = data_cb;

	// Want to get all matching keys for the skill command stream prefix.
	//
	if (redis_get_matching_keys(ctx,
		SKILLS_CLIENT_RESPONSE_STREAM_PREFIX "*",
		skills_find_client_data_cb,
		&data) < 0)
	{
		fprintf(stderr, "Failed to check for clients\n");
		goto done;
	}

	ret_val = true;

done:
	return ret_val;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Gets client stream from client name. If buffer is non-NULL
//			will write the output into the buffer, else will allocate
//			the string and return it.
//
////////////////////////////////////////////////////////////////////////////////
char *skills_get_client_response_stream(
	const char *client,
	char buffer[STREAM_NAME_MAXLEN])
{
	char *ret = NULL;

	if (buffer != NULL) {
		if (snprintf(
			buffer,
			STREAM_NAME_MAXLEN,
			SKILLS_CLIENT_RESPONSE_STREAM_PREFIX "%s",
			client) >= STREAM_NAME_MAXLEN)
		{
			fprintf(stderr, "Stream name too long!\n");
		}
	} else {
		asprintf(
			&ret,
			SKILLS_CLIENT_RESPONSE_STREAM_PREFIX "%s",
			client);
	}

	return ret;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Gets skill stream from client name. If buffer is non-NULL
//			will write the output into the buffer, else will allocate
//			the string and return it.
//
////////////////////////////////////////////////////////////////////////////////
char *skills_get_skill_command_stream(
	const char *skill,
	char buffer[STREAM_NAME_MAXLEN])
{
	char *ret = NULL;

	if (buffer != NULL) {
		if (snprintf(
			buffer,
			STREAM_NAME_MAXLEN,
			SKILLS_SKILL_COMMAND_STREAM_PREFIX "%s",
			skill) >= STREAM_NAME_MAXLEN)
		{
			fprintf(stderr, "Stream name too long!\n");
		}
	} else {
		asprintf(
			&ret,
			SKILLS_SKILL_COMMAND_STREAM_PREFIX "%s",
			skill);
	}

	return ret;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Gets skill droplet prefix. If buffer is non-NULL
//			will write the output into the buffer, else will allocate
//			the string and return it.
//
////////////////////////////////////////////////////////////////////////////////
char *skills_get_skill_droplet_prefix(
	const char *skill,
	char buffer[STREAM_NAME_MAXLEN])
{
	char *ret = NULL;

	if (buffer != NULL) {
		if (snprintf(
			buffer,
			STREAM_NAME_MAXLEN,
			SKILLS_SKILL_DATA_STREAM_PREFIX "%s:",
			skill) >= STREAM_NAME_MAXLEN)
		{
			fprintf(stderr, "Stream name too long!\n");
		}
	} else {
		asprintf(
			&ret,
			SKILLS_SKILL_DATA_STREAM_PREFIX "%s:",
			skill);
	}

	return ret;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Gets droplet stream from skill and droplet name. If buffer is
//			non-NULL will write the output into the buffer, else will allocate
//			the string and return it.
//
////////////////////////////////////////////////////////////////////////////////
char *skills_get_droplet_stream(
	const char *skill,
	const char *droplet,
	char buffer[STREAM_NAME_MAXLEN])
{
	char *ret = NULL;

	if (buffer != NULL) {
		if (snprintf(
			buffer,
			STREAM_NAME_MAXLEN,
			SKILLS_SKILL_DATA_STREAM_PREFIX "%s:%s",
			skill,
			droplet) >= STREAM_NAME_MAXLEN)
		{
			fprintf(stderr, "Stream name too long!\n");
		}
	} else {
		asprintf(
			&ret,
			SKILLS_SKILL_DATA_STREAM_PREFIX "%s:%s",
			skill,
			droplet);
	}

	return ret;
}

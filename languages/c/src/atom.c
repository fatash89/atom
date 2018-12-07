////////////////////////////////////////////////////////////////////////////////
//
//  @file atom.c
//
//  @brief Implements atom library-level shared functionality
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
#include <malloc.h>
#include <assert.h>

#include "redis.h"
#include "atom.h"
#include "element.h"

// User data callback to send to the redis helper for finding elements
struct atom_get_element_cb_info {
	bool (*user_cb)(const char *key, void *user_data);
	void *user_data;
};

// User data callback to send to the redis helper for finding streams
struct atom_get_data_stream_cb_info {
	bool (*user_cb)(const char *stream, void *user_data);
	void *user_data;
	size_t offset;
};

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Data callback for when we get a key that matches the element
//			pattern. We want to strip off the prefix
//
////////////////////////////////////////////////////////////////////////////////
static bool atom_get_element_cb(
	const char *key,
	void *user_data)
{
	struct atom_get_element_cb_info *info;

	// Get the info
	info = (struct atom_get_element_cb_info*)user_data;

	// Want to pass only the element name along to the user callback
	//	along with the user data
	return info->user_cb(
		&key[CONST_STRLEN(ATOM_COMMAND_STREAM_PREFIX)],
		info->user_data);
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Calls a callback for each element present in the system. User
//			can then do as they please.
//
////////////////////////////////////////////////////////////////////////////////
enum atom_error_t atom_get_all_elements_cb(
	redisContext *ctx,
	bool (*data_cb)(const char *element, void *user_data),
	void *user_data)
{
	struct atom_get_element_cb_info info;
	enum atom_error_t err = ATOM_INTERNAL_ERROR;

	// Set up the callback info s.t. when our cb is called we can pass
	//	it along to the user
	info.user_cb = data_cb;
	info.user_data = user_data;

	// Want to get all matching keys for the element command stream prefix.
	//
	if (redis_get_matching_keys(ctx,
		ATOM_COMMAND_STREAM_PREFIX "*",
		atom_get_element_cb,
		&info) < 0)
	{
		fprintf(stderr, "Failed to check for elements\n");
		err = ATOM_REDIS_ERROR;
		goto done;
	}

	err = ATOM_NO_ERROR;

done:
	return err;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Data callback for when we get a key that matches the stream
//			pattern. We want to strip off the prefix for the stream
//			and perhaps the stream name if one was passed
//
////////////////////////////////////////////////////////////////////////////////
static bool atom_get_data_stream_cb(
	const char *key,
	void *user_data)
{
	struct atom_get_data_stream_cb_info *info;

	// Get the info
	info = (struct atom_get_data_stream_cb_info*)user_data;

	// Want to pass only the element name along to the user callback
	return info->user_cb(&key[info->offset], info->user_data);
}


////////////////////////////////////////////////////////////////////////////////
//
//  @brief Calls a callback for each stream present in the system. Optional
//			element parameter will allow the user to filter with only
//			streams for a particular element if desired
//
////////////////////////////////////////////////////////////////////////////////
enum atom_error_t atom_get_all_data_streams_cb(
	redisContext *ctx,
	const char *element,
	bool (*data_cb)(const char *stream, void *user_data),
	void *user_data)
{
	struct atom_get_data_stream_cb_info info;
	char stream_prefix_buffer[128];
	enum atom_error_t err = ATOM_INTERNAL_ERROR;

	// Set up the callback info s.t. when our cb is called we can pass
	//	it along to the user
	info.user_cb = data_cb;
	info.user_data = user_data;

	// Make the stream pattern
	if (element != NULL) {
		info.offset = snprintf(stream_prefix_buffer, sizeof(stream_prefix_buffer),
			ATOM_DATA_STREAM_PREFIX "%s:*", element) - 1;
	} else {
		strncpy(stream_prefix_buffer,
			ATOM_DATA_STREAM_PREFIX "*",
			sizeof(stream_prefix_buffer));
		info.offset = CONST_STRLEN(ATOM_DATA_STREAM_PREFIX);
	}

	// Want to get all matching keys for the element command stream prefix.
	if (redis_get_matching_keys(ctx,
		stream_prefix_buffer,
		atom_get_data_stream_cb,
		&info) < 0)
	{
		fprintf(stderr, "Failed to check for streams\n");
		err = ATOM_REDIS_ERROR;
		goto done;
	}

	err = ATOM_NO_ERROR;

done:
	return err;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Gets a callback when an element/data stream
//			is found. Adds it to the list, allocating the memory
//			as needed
//
////////////////////////////////////////////////////////////////////////////////
static bool atom_add_to_list(
	const char *item,
	void *user_data)
{
	struct atom_list_node **list;
	struct atom_list_node *new_node;
	int ret;

	// Assign the user data to the list
	list = (struct atom_list_node **)user_data;

	// Want to see if the item is in the list or if we've gone
	//	past the point in the list at which we should add the item
	while ((*list) != NULL) {
		ret = strcmp((*list)->name, item);

		// If the item is in the list, we're done
		if (ret == 0) {
			return true;

		// Else if the item is greater than the current item
		//	we want to insert it where we are;
		} else if (ret > 0) {
			break;

		// Otherwise we want to keep iterating
		} else {
			list = &((*list)->next);
		}
	}

	// If we got here then we want to make a new node
	//	and put it in the list at the current location
	new_node = malloc(sizeof(struct atom_list_node));
	assert(new_node != NULL);
	new_node->name = strdup(item);
	assert(new_node->name != NULL);

	new_node->next = *list;
	*list = new_node;

	return true;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Frees a list of atom elements
//
////////////////////////////////////////////////////////////////////////////////
void atom_list_free(
	struct atom_list_node *list)
{
	struct atom_list_node *to_delete;

	while (list != NULL) {
		to_delete = list;
		list = list->next;

		if (to_delete->name != NULL) {
			free(to_delete->name);
		}
		free(to_delete);
	}
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Returns a sorted list of all elements in the system
//
////////////////////////////////////////////////////////////////////////////////
enum atom_error_t atom_get_all_elements(
	redisContext *ctx,
	struct atom_list_node **result)
{
	*result = NULL;
	return atom_get_all_elements_cb(
		ctx,
		atom_add_to_list,
		result);
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Returns a sorted list of all data streams in the system
//
////////////////////////////////////////////////////////////////////////////////
enum atom_error_t atom_get_all_data_streams(
	redisContext *ctx,
	const char *element,
	struct atom_list_node **result)
{
	*result = NULL;
	return atom_get_all_data_streams_cb(
		ctx,
		element,
		atom_add_to_list,
		result);
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Make sure the element name is valid
//
////////////////////////////////////////////////////////////////////////////////
bool atom_element_name_is_valid(
	const char *element)
{
	size_t name_len;

	if (element == NULL) {
		return false;
	} else {
		name_len = strnlen(element, ATOM_NAME_MAXLEN);
		if ((name_len == 0) || (name_len == ATOM_NAME_MAXLEN)) {
			return false;
		} else {}
	}

	if ((element != NULL) && (strnlen(element, ATOM_NAME_MAXLEN) < ATOM_NAME_MAXLEN)) {
		return true;
	} else {
		return false;
	}
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Gets response stream for an element. If buffer is non-NULL
//			will write the output into the buffer, else will allocate
//			the string and return it.
//
////////////////////////////////////////////////////////////////////////////////
char *atom_get_response_stream_str(
	const char *element,
	char buffer[ATOM_NAME_MAXLEN])
{
	char *ret = NULL;

	if (!atom_element_name_is_valid(element)) {
		return NULL;
	}

	if (buffer != NULL) {
		if (snprintf(
			buffer,
			ATOM_NAME_MAXLEN,
			ATOM_RESPONSE_STREAM_PREFIX "%s",
			element) >= ATOM_NAME_MAXLEN)
		{
			fprintf(stderr, "Stream name too long!\n");
		} else {
			ret = buffer;
		}
	} else {
		asprintf(
			&ret,
			ATOM_RESPONSE_STREAM_PREFIX "%s",
			element);
	}

	return ret;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Gets request stream for an element. If buffer is non-NULL
//			will write the output into the buffer, else will allocate
//			the string and return it.
//
////////////////////////////////////////////////////////////////////////////////
char *atom_get_command_stream_str(
	const char *element,
	char buffer[ATOM_NAME_MAXLEN])
{
	char *ret = NULL;

	if (!atom_element_name_is_valid(element)) {
		return NULL;
	}

	if (buffer != NULL) {
		if (snprintf(
			buffer,
			ATOM_NAME_MAXLEN,
			ATOM_COMMAND_STREAM_PREFIX "%s",
			element) >= ATOM_NAME_MAXLEN)
		{
			fprintf(stderr, "Stream name too long!\n");
		} else {
			ret = buffer;
		}
	} else {
		asprintf(
			&ret,
			ATOM_COMMAND_STREAM_PREFIX "%s",
			element);
	}

	return ret;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Gets data stream prefix. If buffer is non-NULL
//			will write the output into the buffer, else will allocate
//			the string and return it.
//
////////////////////////////////////////////////////////////////////////////////
char *atom_get_data_stream_prefix_str(
	const char *element,
	char buffer[ATOM_NAME_MAXLEN])
{
	char *ret = NULL;

	if (!atom_element_name_is_valid(element)) {
		return NULL;
	}

	if (buffer != NULL) {
		if (snprintf(
			buffer,
			ATOM_NAME_MAXLEN,
			ATOM_DATA_STREAM_PREFIX "%s:",
			element) >= ATOM_NAME_MAXLEN)
		{
			fprintf(stderr, "Stream name too long!\n");
		} else {
			ret = buffer;
		}
	} else {
		asprintf(
			&ret,
			ATOM_DATA_STREAM_PREFIX "%s:",
			element);
	}

	return ret;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Gets data stream. If buffer is non-NULL
//			will write the output into the buffer, else will allocate
//			the string and return it.
//
////////////////////////////////////////////////////////////////////////////////
char *atom_get_data_stream_str(
	const char *element,
	const char *name,
	char buffer[ATOM_NAME_MAXLEN])
{
	char *ret = NULL;

	if (!atom_element_name_is_valid(element)) {
		return NULL;
	}

	if (buffer != NULL) {
		if (snprintf(
			buffer,
			ATOM_NAME_MAXLEN,
			ATOM_DATA_STREAM_PREFIX "%s:%s",
			element,
			name) >= ATOM_NAME_MAXLEN)
		{
			fprintf(stderr, "Stream name too long!\n");
		} else {
			ret = buffer;
		}
	} else {
		asprintf(
			&ret,
			ATOM_DATA_STREAM_PREFIX "%s:%s",
			element,
			name);
	}

	return ret;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Logs a message to the global log stream
//
////////////////////////////////////////////////////////////////////////////////
enum atom_error_t atom_log(
	redisContext *ctx,
	struct element *element,
	int level,
	const char *msg,
	size_t msg_len)
{
	struct redis_xadd_info infos[LOG_N_KEYS];
	char level_str[2];
	enum atom_error_t err = ATOM_INTERNAL_ERROR;

	// Check the level
	if ((level < LOG_CRIT) || (level > LOG_DEBUG)) {
		fprintf(stderr, "Invalid log level %d\n", level);
		err = ATOM_COMMAND_INVALID_DATA;
		goto done;
	}

	// Make the level string
	level_str[0] = '0' + level;
	level_str[1] = '\0';

	// Fill in the infos
	infos[LOG_KEY_LEVEL].key = LOG_KEY_LEVEL_STR;
	infos[LOG_KEY_LEVEL].key_len = sizeof(LOG_KEY_LEVEL_STR) - 1;
	infos[LOG_KEY_LEVEL].data = (const uint8_t*)level_str;
	infos[LOG_KEY_LEVEL].data_len = 1;

	infos[LOG_KEY_ELEMENT].key = LOG_KEY_ELEMENT_STR;
	infos[LOG_KEY_ELEMENT].key_len = sizeof(LOG_KEY_ELEMENT_STR) - 1;
	infos[LOG_KEY_ELEMENT].data = (const uint8_t*)element->name.str;
	infos[LOG_KEY_ELEMENT].data_len = element->name.len;

	infos[LOG_KEY_MESSAGE].key = LOG_KEY_MESSAGE_STR;
	infos[LOG_KEY_MESSAGE].key_len = sizeof(LOG_KEY_MESSAGE_STR) - 1;
	infos[LOG_KEY_MESSAGE].data = (const uint8_t*)msg;
	infos[LOG_KEY_MESSAGE].data_len = msg_len;

	if (!redis_xadd(
		ctx,
		ATOM_LOG_STREAM_NAME,
		infos,
		LOG_N_KEYS,
		ATOM_DEFAULT_MAXLEN,
		true,
		NULL))
	{
		err = ATOM_REDIS_ERROR;
		goto done;
	}

	err = ATOM_NO_ERROR;

done:
	return err;
}

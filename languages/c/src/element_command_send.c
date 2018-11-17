////////////////////////////////////////////////////////////////////////////////
//
//  @file element_command.c
//
//  @brief Implements client/request side of commands
//
//  @copy 2018 Elementary Robotics. All rights reserved.
//
////////////////////////////////////////////////////////////////////////////////
#include <stdio.h>
#include <hiredis/hiredis.h>
#include <pthread.h>
#include <stdbool.h>
#include <string.h>
#include <assert.h>
#include <malloc.h>
#include <stdlib.h>

#include "redis.h"
#include "atom.h"
#include "element.h"

#define ELEMENT_COMMAND_ACK_TIMEOUT 100000

// How long to wait for a response if the command is not supported
#define ELEMENT_NO_COMMAND_TIMEOUT_MS 1000

// Struct for handling a response on the command stream. Will be passed
//	to the XREAD as the user data.
struct element_response_stream_data {
	struct element *elem;
	const char *cmd_elem;
	const char *cmd_id;
	struct redis_xread_kv_item *kv_items;
	size_t n_kv_items;
	bool (*user_cb)(
		const struct redis_xread_kv_item *kv_items,
		void* user_data);
	void *user_data;
};

// Data we want to obtain from the ACK
struct element_command_ack_data {
	bool found_ack;
	int timeout;
};

// Data we want to obtain from the response
struct element_command_response_data {
	bool found_response;
	bool (*response_cb)(
		const uint8_t *response,
		size_t response_len,
		void *user_data);
	int error_code;
	void *user_data;
};

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Callback for all XREADS from the element's response stream
//
////////////////////////////////////////////////////////////////////////////////
static bool element_response_stream_callback(
	const char *id,
	const struct redisReply *reply,
	void *user_data)
{
	struct element_response_stream_data *data;
	bool ret_val = false;

	// Cast the user data
	data = (struct element_response_stream_data*)user_data;

	// Update the most recent ID that we've seen for the element's
	//	tracking buffer
	strncpy(data->elem->response.last_id, id,
		sizeof(data->elem->response.last_id));

	// Now, we want to parse out the reply array using our kv items
	if (!redis_xread_parse_kv(reply, data->kv_items, data->n_kv_items)) {
		fprintf(stderr, "Failed to parse reply!\n");
		goto done;
	}

	// Now, we want to check to see if the element was found and if it
	//	matches
	if (data->kv_items[STREAM_KEY_ELEMENT].found &&
		(data->kv_items[STREAM_KEY_ELEMENT].reply->type == REDIS_REPLY_STRING) &&
		!strcmp(data->kv_items[STREAM_KEY_ELEMENT].reply->str, data->cmd_elem))
	{
		// If the element matches, check to see if the ID matches
		if (data->kv_items[STREAM_KEY_ID].found &&
			(data->kv_items[STREAM_KEY_ID].reply->type == REDIS_REPLY_STRING) &&
			!strcmp(data->kv_items[STREAM_KEY_ID].reply->str, data->cmd_id))
		{
			// If we're here then we know that the element matches and
			//	the command ID matches. At this point we should call the
			//	user callback s.t. it can check the rest of the data
			if (!data->user_cb(data->kv_items, data->user_data)) {
				fprintf(stderr, "Failed to call user callback!\n");
				goto done;
			}

		} else {
			fprintf(stderr, "couldn't find id\n");
		}
	} else {
		fprintf(stderr, "couldn't find element\n");
	}

	// Note the success
	ret_val = true;

done:
	return ret_val;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Initializes for a general XREAD on a response stream
//
////////////////////////////////////////////////////////////////////////////////
static void element_response_stream_init_data(
	struct redis_stream_info *stream_info,
	struct element_response_stream_data *data,
	struct element *elem,
	const char *cmd_elem,
	const char *cmd_id,
	struct redis_xread_kv_item *kv_items,
	size_t n_kv_items,
	bool (*user_cb)(
		const struct redis_xread_kv_item *kv_items,
		void* user_data),
	void *user_data)
{
	// Initialize all of the necessary fields of the data
	data->elem = elem;
	data->cmd_elem = cmd_elem;
	data->cmd_id = cmd_id;
	data->user_data = user_data;
	data->user_cb = user_cb;
	data->kv_items = kv_items;
	data->n_kv_items = n_kv_items;

	// Initialize the shared keys in the kv_items for any
	//	response on the stream
	kv_items[STREAM_KEY_ELEMENT].key = STREAM_KEY_ELEMENT_STR;
	kv_items[STREAM_KEY_ELEMENT].key_len = CONST_STRLEN(STREAM_KEY_ELEMENT_STR);
	kv_items[STREAM_KEY_ID].key = STREAM_KEY_ID_STR;
	kv_items[STREAM_KEY_ID].key_len = CONST_STRLEN(STREAM_KEY_ID_STR);

	// Finally we want to set up the stream info. This will tell the
	//	XREAD which stream to monitor, the data callback to call when
	//	we get data, from where to start monitoring the stream and the
	//	user pointer to pass along to the data callback
	redis_init_stream_info(
		NULL,
		stream_info,
		elem->response.stream,
		element_response_stream_callback,
		elem->response.last_id,
		data);
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief ACK data callback on the element response stream. Will be called once
//			and ACK (or similar) packet is received and will try to get the
//			timeout and note the success of the ACK.
//
////////////////////////////////////////////////////////////////////////////////
static bool element_command_ack_callback(
	const struct redis_xread_kv_item *kv_items,
	void *user_data)
{
	struct element_command_ack_data *data;

	// Cast the user data
	data = (struct element_command_ack_data*)user_data;

	// Now, make sure the timestamp was found and copy it over
	if (kv_items[ACK_KEY_TIMEOUT].found &&
		(kv_items[ACK_KEY_TIMEOUT].reply->type == REDIS_REPLY_STRING))
	{
		data->timeout = atoi(kv_items[ACK_KEY_TIMEOUT].reply->str);
		data->found_ack = true;
	}

	return true;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Response data callback on the element response stream. Will be called
//			once a response (or similar) packet is received and will
//			make sure all of the items are there and valid
//
////////////////////////////////////////////////////////////////////////////////
static bool element_command_response_callback(
	const struct redis_xread_kv_item *kv_items,
	void *user_data)
{
	struct element_command_response_data *data;
	int atom_err;

	// Cast the user data
	data = (struct element_command_response_data*)user_data;

	// Now, want to make sure all necessary fields were found,
	//	and are the right type.
	if ((kv_items[RESPONSE_KEY_CMD].found) &&
		(kv_items[RESPONSE_KEY_CMD].reply->type == REDIS_REPLY_STRING) &&
		(kv_items[RESPONSE_KEY_ERR_CODE].found) &&
		(kv_items[RESPONSE_KEY_ERR_CODE].reply->type == REDIS_REPLY_STRING))
	{
		// Note that we found the response
		data->found_response = true;

		// Get the error code from the element
		atom_err = atoi(kv_items[RESPONSE_KEY_ERR_CODE].reply->str);

		// If we had a successful response from the element
		if (atom_err == ATOM_NO_ERROR) {

			// Note that there's no error, for now
			data->error_code = ATOM_NO_ERROR;

			// If there's data then we want to call the user-supplied
			//	callback, if there is one
			if ((data->response_cb != NULL) &&
				(kv_items[RESPONSE_KEY_DATA].found) &&
				(kv_items[RESPONSE_KEY_DATA].reply->type ==
					REDIS_REPLY_STRING) &&
				(kv_items[RESPONSE_KEY_DATA].reply->len > 0))
			{
				// Call the callback. If it fails, note the error
				if (!data->response_cb(
					(uint8_t*)kv_items[RESPONSE_KEY_DATA].reply->str,
					kv_items[RESPONSE_KEY_DATA].reply->len,
					data->user_data))
				{
					data->error_code = ATOM_CALLBACK_FAILED;
				}
			}

		// Process the error code and error string
		} else {

			// Note the error code
			data->error_code = atom_err;

			// Print out the error for now. No need to return it to the
			//	user.
			if ((kv_items[RESPONSE_KEY_ERR_STR].found) &&
				(kv_items[RESPONSE_KEY_ERR_STR].reply->type ==
					REDIS_REPLY_STRING))
			{
				fprintf(stderr, "%s\n", kv_items[RESPONSE_KEY_ERR_STR].reply->str);
			}
		}
	}

	return true;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief initializes the xadd data for sending a command
//
////////////////////////////////////////////////////////////////////////////////
static void element_command_init_data(
	struct redis_xadd_info cmd_data[CMD_N_KEYS],
	const char *element_name,
	size_t element_name_len,
	const char *command,
	const uint8_t *data,
	size_t data_len)
{
	cmd_data[CMD_KEY_ELEMENT].key = COMMAND_KEY_ELEMENT_STR;
	cmd_data[CMD_KEY_ELEMENT].key_len = CONST_STRLEN(COMMAND_KEY_ELEMENT_STR);
	cmd_data[CMD_KEY_ELEMENT].data = (uint8_t*)element_name;
	cmd_data[CMD_KEY_ELEMENT].data_len = element_name_len;

	cmd_data[CMD_KEY_CMD].key = COMMAND_KEY_COMMAND_STR;
	cmd_data[CMD_KEY_CMD].key_len = CONST_STRLEN(COMMAND_KEY_COMMAND_STR);
	cmd_data[CMD_KEY_CMD].data = (uint8_t*)command;
	cmd_data[CMD_KEY_CMD].data_len = strlen(command);

	cmd_data[CMD_KEY_DATA].key = COMMAND_KEY_DATA_STR;
	cmd_data[CMD_KEY_DATA].key_len = CONST_STRLEN(COMMAND_KEY_DATA_STR);
	cmd_data[CMD_KEY_DATA].data = data;
	cmd_data[CMD_KEY_DATA].data_len = data_len;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief initializes the ACK items for sending a command.
//
////////////////////////////////////////////////////////////////////////////////
static void element_command_init_ack_data(
	struct element_command_ack_data *ack_data,
	struct redis_xread_kv_item ack_items[ACK_N_KEYS])
{
	// Note that we haven't found the ack
	ack_data->found_ack = false;

	// And reset the timeout
	ack_data->timeout = 0;

	// We also want to fill in the non-shared parts of the ack items
	ack_items[ACK_KEY_TIMEOUT].key = ACK_KEY_TIMEOUT_STR;
	ack_items[ACK_KEY_TIMEOUT].key_len = CONST_STRLEN(ACK_KEY_TIMEOUT_STR);
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief initializes the response items for sending a command
//
////////////////////////////////////////////////////////////////////////////////
static void element_command_init_response_data(
	struct element_command_response_data *response_data,
	struct redis_xread_kv_item response_items[STREAM_N_KEYS],
	bool (*response_cb)(
		const uint8_t *response,
		size_t response_len,
		void *user_data),
	void *user_data)
{
	// Note that we haven't found the ack
	response_data->found_response = false;

	// And note the user response callback
	response_data->response_cb = response_cb;

	// Initialize the error code to an internal error
	response_data->error_code = ATOM_INTERNAL_ERROR;

	// Note the user data
	response_data->user_data = user_data;

	// We also want to fill in the non-shared parts of the ack items
	response_items[RESPONSE_KEY_CMD].key = RESPONSE_KEY_CMD_STR;
	response_items[RESPONSE_KEY_CMD].key_len = CONST_STRLEN(RESPONSE_KEY_CMD_STR);
	response_items[RESPONSE_KEY_ERR_CODE].key = RESPONSE_KEY_ERR_CODE_STR;
	response_items[RESPONSE_KEY_ERR_CODE].key_len = CONST_STRLEN(RESPONSE_KEY_ERR_CODE_STR);
	response_items[RESPONSE_KEY_ERR_STR].key = RESPONSE_KEY_ERR_STR_STR;
	response_items[RESPONSE_KEY_ERR_STR].key_len = CONST_STRLEN(RESPONSE_KEY_ERR_STR_STR);
	response_items[RESPONSE_KEY_DATA].key = RESPONSE_KEY_DATA_STR;
	response_items[RESPONSE_KEY_DATA].key_len = CONST_STRLEN(RESPONSE_KEY_DATA_STR);
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Sends a command to another element. If block=TRUE
//			will wait for the command to get a response. If block=True AND
//			response_cb != NULL then will call the response_cb with the
//			data payload that came back in the response.
//
////////////////////////////////////////////////////////////////////////////////
enum atom_error_t element_command_send(
	redisContext *ctx,
	struct element *elem,
	const char *cmd_elem,
	const char *cmd,
	const uint8_t *data,
	size_t data_len,
	bool block,
	bool (*response_cb)(
		const uint8_t *response,
		size_t response_len,
		void *user_data),
	void *user_data)
{
	int ret;
	struct redis_stream_info stream_info;
	struct redis_xadd_info cmd_data[CMD_N_KEYS];
	char cmd_elem_stream[ATOM_NAME_MAXLEN];
	char cmd_id[STREAM_ID_BUFFLEN];

	struct element_response_stream_data stream_data;

	struct element_command_ack_data ack_data;
	struct redis_xread_kv_item ack_items[ACK_N_KEYS];

	struct element_command_response_data response_data;
	struct redis_xread_kv_item response_items[RESPONSE_N_KEYS];

	// Initialize the error code
	ret = ATOM_INTERNAL_ERROR;

	// Want to set up the data for the command
	element_command_init_data(
		cmd_data, elem->name.str, elem->name.len, cmd, data, data_len);

	// Get the name of the element stream we want to write to
	atom_get_command_stream_str(cmd_elem, cmd_elem_stream);

	// Now, call the XADD to send the data over to the element. We want to
	//	note the command ID since we'll expect it back in the ACK and response
	if (!redis_xadd(ctx, cmd_elem_stream, cmd_data, CMD_N_KEYS,
		10, ATOM_DEFAULT_APPROX_MAXLEN, cmd_id))
	{
		fprintf(stderr, "Failed to XADD command data to stream\n");
		ret = ATOM_REDIS_ERROR;
		goto done;
	}

	// Need to set up the ack. This will initialize our user data
	//	and set up the keys we're looking for in the ack
	element_command_init_ack_data(&ack_data, ack_items);
	// Need to set up the general response callback
	element_response_stream_init_data(
		&stream_info, &stream_data, elem, cmd_elem, cmd_id, ack_items,
		ACK_N_KEYS, element_command_ack_callback, &ack_data);

	// Now, we're ready to call the XREAD. We want to do this until either
	//	the ACK is found or we've timed out. Note that this re-does the
	//	timeout each time we get a message which is not ideal.
	while (!ack_data.found_ack) {
		// XREAD with a default timeout since the ACK should come quickly
		if (!redis_xread(ctx, &stream_info, 1, ELEMENT_COMMAND_ACK_TIMEOUT)) {
			ret = ATOM_COMMAND_NO_ACK;
			fprintf(stderr, "Failed to get ACK\n");
			goto done;
		}
	}

	// Now, if we're not blocking then we're all done! We can just return
	//	out noting the success. Else we need to again do an XREAD on the
	//	stream and pass the data along to the command handler.
	if (!block) {
		ret = ATOM_NO_ERROR;
		goto done;
	}

	// Need to set up the response. This will initialize our user data
	//	and set up the keys we're looking for in the ack
	element_command_init_response_data(
		&response_data, response_items, response_cb, user_data);
	// Need to set up the general response callback
	element_response_stream_init_data(
		&stream_info, &stream_data, elem, cmd_elem, cmd_id, response_items,
		RESPONSE_N_KEYS, element_command_response_callback,
		&response_data);

	// Now, we're ready to call the XREAD. Want to do this until either
	//	the response is found or we've timed out. Note that this re-does the
	//	timeout each time we get a message which is not ideal.
	while (!response_data.found_response) {
		// XREAD with the timeout returned from the ACK
		if (!redis_xread(ctx, &stream_info, 1, ack_data.timeout)) {
			ret = ATOM_COMMAND_NO_RESPONSE;
			fprintf(stderr, "Failed to get response\n");
			goto done;
		}
	}

	// If we got here then we got the response. We can set our status
	//	to that returned by the response
	ret = response_data.error_code;

done:
	return ret;
}

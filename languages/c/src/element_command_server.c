////////////////////////////////////////////////////////////////////////////////
//
//  @file element_cmd_rep.c
//
//  @brief Implements server/response side of commands
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

// This value is returned to the caller when the command they
//	request is not supported. It tells them how long to wait for our
//	error response
#define ELEMENT_NO_COMMAND_TIMEOUT_MS 1000

// Struct of user data for when we get a callback on the element command
//	stream
struct element_command_cb_data {
	struct element *elem;
	struct redis_xread_kv_item *kv_items;
	size_t n_kv_items;
	enum atom_error_t err_code;
};

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Element command hash function. For now just djb2.
//			See: http://www.cse.yorku.ca/~oz/hash.html
//
//			Note: this does modulate around the number of bins in the element
//			hashtable. It is assumed that the output of this function is
//			a valid index into the element hashtable
//
////////////////////////////////////////////////////////////////////////////////
static uint32_t element_command_hash_fn(
	const char *name)
{
    uint32_t hash = 5381;
    int c;

    while ((c = (uint8_t)(*name++))) {
        hash = ((hash << 5) + hash) + c; /* hash * 33 + c */
    }

    return hash & (ELEMENT_COMMAND_HASH_N_BINS - 1);
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Returns the info struct for a command, passed by name. If the
//			command is registered returns a pointer to the info, else returns
//			NULL.
//
////////////////////////////////////////////////////////////////////////////////
static struct element_command *element_command_get(
	struct element *elem,
	const char *command)
{
	struct element_command *cmd = NULL;
	struct element_command *iter;

	// Get the list at the beginning of the bin for the hashtable
	iter = elem->command.hash[element_command_hash_fn(command)];

	// Loop until we either get to the end of the list or we find the
	//	matching command
	while (iter != NULL) {
		if (strcmp(iter->name, command) == 0) {
			cmd = iter;
			break;
		}
		iter = iter->next;
	}

	return cmd;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Initializes the shared aspects of the element command data
//
////////////////////////////////////////////////////////////////////////////////
static void element_command_init_shared_data(
	struct element *elem,
	const char *id,
	const char *req_elem,
	struct redis_xadd_info *infos,
	char req_elem_stream[ATOM_NAME_MAXLEN])
{
	infos[STREAM_KEY_ELEMENT].key = STREAM_KEY_ELEMENT_STR;
	infos[STREAM_KEY_ELEMENT].key_len = CONST_STRLEN(STREAM_KEY_ELEMENT_STR);
	infos[STREAM_KEY_ELEMENT].data = (uint8_t*)elem->name.str;
	infos[STREAM_KEY_ELEMENT].data_len = elem->name.len;

	infos[STREAM_KEY_ID].key = STREAM_KEY_ID_STR;
	infos[STREAM_KEY_ID].key_len = CONST_STRLEN(STREAM_KEY_ID_STR);
	infos[STREAM_KEY_ID].data = (uint8_t*)id;
	infos[STREAM_KEY_ID].data_len = strlen(id);

	// Get the element reply stream name
	atom_get_response_stream_str(req_elem, req_elem_stream);
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Sends an ACK to the requesting element letting them know that we
//			received their command
//
////////////////////////////////////////////////////////////////////////////////
static bool element_command_send_ack(
	redisContext *ctx,
	struct element *elem,
	const char *id,
	const char *req_elem,
	int timeout)
{
	struct redis_xadd_info ack_info[ACK_N_KEYS];
	bool ret_val = false;
	char timeout_buffer[32];
	size_t timeout_len;
	char req_elem_stream[ATOM_NAME_MAXLEN];

	// Need to set up the XADD info to send back
	element_command_init_shared_data(
		elem, id, req_elem, ack_info, req_elem_stream);

	// And fill in the ACK-specific data
	ack_info[ACK_KEY_TIMEOUT].key = ACK_KEY_TIMEOUT_STR;
	ack_info[ACK_KEY_TIMEOUT].key_len = CONST_STRLEN(ACK_KEY_TIMEOUT_STR);
	timeout_len = snprintf(
		timeout_buffer, sizeof(timeout_buffer), "%d", timeout);
	ack_info[ACK_KEY_TIMEOUT].data = (uint8_t*)timeout_buffer;
	ack_info[ACK_KEY_TIMEOUT].data_len = timeout_len;

	// And want to call the XADD to send the info back to the caller
	if (!redis_xadd(
		ctx, req_elem_stream, ack_info, ACK_N_KEYS,
		ATOM_DEFAULT_MAXLEN, ATOM_DEFAULT_APPROX_MAXLEN, NULL))
	{
		atom_logf(ctx, elem, LOG_ERR, "Failed to send ACK");
		goto done;
	}

	// Note the success
	ret_val = true;

done:
	return ret_val;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Sends the response to the caller
//
////////////////////////////////////////////////////////////////////////////////
static bool element_command_send_response(
	redisContext *ctx,
	struct element *elem,
	const char *id,
	const char *req_elem,
	struct element_command *cmd,
	uint8_t *response,
	size_t response_len,
	enum atom_error_t error_code,
	char *error_str)
{
	struct redis_xadd_info response_info[RESPONSE_N_KEYS];
	bool ret_val = false;
	char req_elem_stream[ATOM_NAME_MAXLEN];
	char err_code_buffer[32];
	size_t err_code_len;
	int response_idx = STREAM_N_KEYS;

	// Need to set up the XADD info to send back
	element_command_init_shared_data(
		elem, id, req_elem, response_info, req_elem_stream);

	// Fill in the error code
	response_info[response_idx].key = RESPONSE_KEY_ERR_CODE_STR;
	response_info[response_idx].key_len = CONST_STRLEN(
		RESPONSE_KEY_ERR_CODE_STR);
	err_code_len = snprintf(
		err_code_buffer, sizeof(err_code_buffer), "%d", error_code);
	response_info[response_idx].data = (uint8_t*)err_code_buffer;
	response_info[response_idx].data_len = err_code_len;
	++response_idx;

	// If we have a command, fill that in
	if (cmd != NULL) {
		response_info[response_idx].key = RESPONSE_KEY_CMD_STR;
		response_info[response_idx].key_len = CONST_STRLEN(RESPONSE_KEY_CMD_STR);
		response_info[response_idx].data = (uint8_t*)cmd->name;
		response_info[response_idx].data_len = strlen(cmd->name);
		++response_idx;
	}

	// If we have an error string, fill that in
	if (error_str != NULL) {
		response_info[response_idx].key = RESPONSE_KEY_ERR_STR_STR;
		response_info[response_idx].key_len = CONST_STRLEN(
			RESPONSE_KEY_ERR_STR_STR);
		response_info[response_idx].data = (uint8_t*)error_str;
		response_info[response_idx].data_len = strlen(error_str);
		++response_idx;
	}

	// If we have response data, fill that in
	if (response != NULL) {
		response_info[response_idx].key = RESPONSE_KEY_DATA_STR;
		response_info[response_idx].key_len = CONST_STRLEN(
			RESPONSE_KEY_DATA_STR);
		response_info[response_idx].data = response;
		response_info[response_idx].data_len = response_len;
		++response_idx;
	}

	// And want to call the XADD to send the info back to the caller
	if (!redis_xadd(
		ctx, req_elem_stream, response_info, response_idx,
		ATOM_DEFAULT_MAXLEN, ATOM_DEFAULT_APPROX_MAXLEN, NULL))
	{
		atom_logf(ctx, elem, LOG_ERR, "Failed to send response");
		goto done;
	}

	// Note the success
	ret_val = true;

done:
	return ret_val;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Element callback from XREAD for when we get a command. Will check
//			to make sure that all of the necessary command fields
//			are present in the command request and also that we support
//			the passed command
//
////////////////////////////////////////////////////////////////////////////////
static bool element_cmd_rep_xread_cb(
	const char *id,
	const struct redisReply *reply,
	void *user_data)
{
	bool ret_val = false;
	struct element_command_cb_data *data;
	struct element_command *cmd;
	int ret, timeout;
	uint8_t *response = NULL;
	size_t response_len = 0;
	char *error_str = NULL;
	void *cleanup_ptr = NULL;

	// Want to cast the user data to our expected data struct
	data = (struct element_command_cb_data *)user_data;

	// Update the most recent ID that we've seen for the command
	//	tracking buffer
	strncpy(data->elem->command.last_id, id,
		sizeof(data->elem->command.last_id));

	// Now, we want to parse out the reply array using our kv items
	if (!redis_xread_parse_kv(reply, data->kv_items, data->n_kv_items)) {
		atom_logf(data->elem->command.ctx, data->elem, LOG_ERR,
			"Failed to parse reply!");
		goto done;
	}

	// The only other thing needed to not have a complete failure
	//	on this message is for the element key to exist in the
	//	message. Make sure that's there
	if (!data->kv_items[CMD_KEY_ELEMENT].found) {
		atom_logf(data->elem->command.ctx, data->elem, LOG_ERR,
			"Didn't get element in message!");
		goto done;
	}

	// Want to try to get the command s.t. we can get the timeout
	//	length to send back to the caller in the ACK
	cmd = data->kv_items[CMD_KEY_CMD].found ?
		element_command_get(
			data->elem, data->kv_items[CMD_KEY_CMD].reply->str) :
		NULL;
	timeout = (cmd != NULL) ? cmd->timeout : ELEMENT_NO_COMMAND_TIMEOUT_MS;

	// At this point we know that we got a message and have a caller
	//	to respond back to, so we need to send an ACK
	if (!element_command_send_ack(
		data->elem->command.ctx,
		data->elem,
		id,
		data->kv_items[CMD_KEY_ELEMENT].reply->str,
		timeout))
	{
		atom_logf(data->elem->command.ctx, data->elem, LOG_ERR,
			"Failed to send ACK to caller");
		goto done;
	}

	// Now, if we're missing the command it's either because the user
	//	didn't supply one or we don't support the requested command.
	//	Find the proper error and then send the user a response.
	if (cmd == NULL) {
		if (data->kv_items[CMD_KEY_CMD].found) {
			atom_logf(data->elem->command.ctx, data->elem, LOG_ERR,
				"Unsupported command!");
			data->err_code = ATOM_COMMAND_UNSUPPORTED;
		} else {
			atom_logf(data->elem->command.ctx, data->elem, LOG_ERR,
				"Missing command!");
			data->err_code = ATOM_COMMAND_INVALID_DATA;
		}

	// Otherwise we want to try to call the user callback for the command
	} else {

		// Initialize the response
		response = NULL;
		response_len = 0;
		error_str = NULL;

		ret = cmd->cb(
			data->kv_items[CMD_KEY_DATA].found ?
				(uint8_t*)data->kv_items[CMD_KEY_DATA].reply->str : NULL,
			data->kv_items[CMD_KEY_DATA].found ?
				data->kv_items[CMD_KEY_DATA].reply->len : 0,
			&response,
			&response_len,
			&error_str,
			cmd->user_data,
			&cleanup_ptr);

		// If the return is an error, we want to append it atop the internal
		//	element errors
		if (ret != 0) {
			data->err_code = ATOM_USER_ERRORS_BEGIN + ret;
		} else {
			data->err_code = ATOM_NO_ERROR;
		}
	}

	// Now we want to send the response out to the caller
	if (!element_command_send_response(
		data->elem->command.ctx,
		data->elem,
		id,
		data->kv_items[CMD_KEY_ELEMENT].reply->str,
		cmd,
		response,
		response_len,
		data->err_code,
		error_str))
	{
		atom_logf(data->elem->command.ctx, data->elem, LOG_ERR,
			"Failed to send response to caller");
		goto done;
	}

	// Note the success
	ret_val = true;

done:
	if (cleanup_ptr != NULL) {
		if (cmd->cleanup != NULL) {
			cmd->cleanup(cleanup_ptr);
		} else {
			atom_logf(data->elem->command.ctx, data->elem, LOG_ERR,
				"Cleanup ptr non-null but no cleanup fn!");
		}
	} else {
		if (response != NULL) {
			free(response);
		}
		if (error_str != NULL) {
			free(error_str);
		}
	}
	return ret_val;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Runs the element command monitoring loop. Will handle commands
//			and call the command callbacks in the hashtable if/when
//			a command comes. Loop == false causes the XREAD for commands
//			only to be run once, else infinitely. If timeout is nonzero
//			then we will return with a failure after timeout ms of not
//			gettin a command.
//
////////////////////////////////////////////////////////////////////////////////
enum atom_error_t element_command_loop(
	redisContext *ctx,
	struct element *elem,
	bool loop,
	int timeout)
{
	struct redis_stream_info stream_info;
	struct element_command_cb_data cmd_data;
	struct redis_xread_kv_item cmd_kv_items[CMD_N_KEYS];
	enum atom_error_t ret = ATOM_INTERNAL_ERROR;

	// Set up the kv items
	cmd_kv_items[CMD_KEY_ELEMENT].key = COMMAND_KEY_ELEMENT_STR;
	cmd_kv_items[CMD_KEY_ELEMENT].key_len = CONST_STRLEN(COMMAND_KEY_ELEMENT_STR);
	cmd_kv_items[CMD_KEY_CMD].key = COMMAND_KEY_COMMAND_STR;
	cmd_kv_items[CMD_KEY_CMD].key_len = CONST_STRLEN(COMMAND_KEY_COMMAND_STR);
	cmd_kv_items[CMD_KEY_DATA].key = COMMAND_KEY_DATA_STR;
	cmd_kv_items[CMD_KEY_DATA].key_len = CONST_STRLEN(COMMAND_KEY_DATA_STR);

	// Set up the command data
	cmd_data.elem = elem;
	cmd_data.kv_items = cmd_kv_items;
	cmd_data.n_kv_items = CMD_N_KEYS;
	cmd_data.err_code = ATOM_INTERNAL_ERROR;

	// Want to set up the XREAD. Should be a pretty straightforward
	//	setup of the stream info
	if (!redis_init_stream_info(
		ctx,
		&stream_info,
		elem->command.stream,
		element_cmd_rep_xread_cb,
		elem->command.last_id,
		&cmd_data))
	{
		atom_logf(ctx, elem, LOG_ERR, "Failed to initialize stream info");
		goto done;
	}

	// Now that we've initialized the stream info, we want to go ahead and
	//	call the XREAD! Pretty simple.
	while (true) {

		// Do the xread
		if (!redis_xread(
			ctx,
			&stream_info,
			1,
			timeout,
			REDIS_XREAD_NOMAXCOUNT))
		{
			atom_logf(ctx, elem, LOG_ERR, "Redis issue/timeout");
			ret = ATOM_REDIS_ERROR;
		}

		// And if we shouldn't be looping then break out
		if (!loop) {
			break;
		}
	}

	// Note the lack of error
	ret = ATOM_NO_ERROR;

done:
	return ret;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Adds a command to an element. This will create a node in
//			the element's command hashtable for the command and set all of the
//			values properly. The callback is called each time a caller calls the
//			command and the timeout is sent in the initial ACK packet back
//			to the caller to let them know how long to wait for a response
//			before timing out.
//
//			NOTE: this is thread-safe for a single element adder and
//					multiple element readers. It is not thread-safe for multiple
//					element adder threads.
//
////////////////////////////////////////////////////////////////////////////////
bool element_command_add(
	struct element *elem,
	const char *command,
	int (*cb)(
		uint8_t *data,
		size_t data_len,
		uint8_t **response,
		size_t *response_len,
		char **error_str,
		void *user_data,
		void **cleanup_ptr),
	void (*cleanup)(void *cleanup_ptr),
	void *user_data,
	int timeout)
{
	struct element_command *cmd = NULL;
	uint32_t hash;

	// Need to allocate the memory for the new command
	cmd = malloc(sizeof(struct element_command));
	assert(cmd != NULL);

	// Now that we've allocated the command, we should fill it in.
	// Start with the name
	cmd->name = strdup(command);
	assert(cmd->name != NULL);

	// Now fill in the callback, user data and the timeout
	cmd->cb = cb;
	cmd->cleanup = cleanup;
	cmd->timeout = timeout;
	cmd->user_data = user_data;

	// Get the hash for the element
	hash = element_command_hash_fn(cmd->name);

	// Now, we want to insert the node into the hashtable. We'll
	//	do this at the *front* of the list s.t. we avoid any concurrency
	//	issues with someone reading at the same time since the swapout
	//	will be atomic. That said, this function is not thread-safe for
	//	multiple adds at the same time.
	cmd->next = elem->command.hash[hash];
	elem->command.hash[hash] = cmd;

	return true;
}

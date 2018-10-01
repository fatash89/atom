////////////////////////////////////////////////////////////////////////////////
//
//  @file skill.c
//
//  @brief Implements functionality of a skills skill.
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
#include <assert.h>
#include <malloc.h>
#include <stdlib.h>

#include "redis.h"
#include "skills.h"
#include "client.h"
#include "skill.h"

// How long to wait for a response if the command is not supported
#define SKILL_NO_COMMAND_TIMEOUT_MS 1000

// Struct of user data for when we get a callback on the skill command
//	stream
struct skill_command_data {
	struct skill *skill;
	struct redis_xread_kv_item *kv_items;
	size_t n_kv_items;
	enum skills_error_t err_code;
};

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Initializes a redis skill. MUST be cleaned up by passing the
//			struct returned to skill_cleanup when done. Note that the context
//			isn't associated with the skill. All functionaity is indifferent
//			to which redis context is being used.
//
////////////////////////////////////////////////////////////////////////////////
struct skill *skill_init(
	redisContext *ctx,
	const char *name)
{
	struct skill *skl = NULL;
	struct redis_xadd_info skill_info[2];

	// Make the new skill
	skl = malloc(sizeof(struct skill));
	if (skl == NULL) {
		fprintf(stderr, "Failed to create new skill\n");
		goto done;
	}

	// Clear out the hashtable for the skill. This initializes
	//	all of the bins to empty
	memset(skl->command_hash, 0, sizeof(skl->command_hash));

	// Want to initialize the skill client
	skl->client = client_init(ctx, name);
	if (skl->client == NULL) {
		fprintf(stderr, "Failed to initialize skill client\n");
		goto skill_err_cleanup;
	}

	// Now, we want to set up the command stream for the skill
	skl->command_stream = skills_get_skill_command_stream(name, NULL);
	if (skl->command_stream == NULL) {
		fprintf(stderr, "Failed to create skill command stream\n");
		goto skill_err_cleanup;
	}

	// Want to add a new redis context for sending ACKs and responses
	//	while we're still working on the response from the old context
	skl->resp_ctx = redis_context_init();
	if (skl->resp_ctx == NULL) {
		fprintf(stderr, "Failed to create response context!\n");
		goto skill_err_cleanup;
	}

	// We want to initialize the client information and call an XADD
	//	to create our client's response stream
	skill_info[0].key = SKILLS_LANGUAGE_KEY;
	skill_info[0].key_len = CONST_STRLEN(SKILLS_LANGUAGE_KEY);
	skill_info[0].data = (uint8_t*)SKILLS_LANGUAGE;
	skill_info[0].data_len = CONST_STRLEN(SKILLS_LANGUAGE);
	skill_info[1].key = SKILLS_VERSION_KEY;
	skill_info[1].key_len = CONST_STRLEN(SKILLS_VERSION_KEY);
	skill_info[1].data = (uint8_t*)SKILLS_VERSION;
	skill_info[1].data_len = CONST_STRLEN(SKILLS_VERSION);

	// And we want to XADD the data to the stream to create it. This will
	//	also put the ID of the item in the stream that we added with our
	//	info into our last id
	if (!redis_xadd(
		ctx, skl->command_stream, skill_info, 2,
		STREAM_DEFAULT_MAXLEN, STREAM_DEFAULT_APPROX_MAXLEN,
		skl->command_last_id))
	{
		fprintf(stderr, "Failed to add initial skill info to command stream\n");
		goto skill_err_cleanup;
	}

	// If we got here, then we're good. Skip the error cleanup
	goto done;

skill_err_cleanup:
	skill_cleanup(ctx, skl);
	skl = NULL;
done:
	return skl;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Frees a command struct
//
////////////////////////////////////////////////////////////////////////////////
static void skill_free_command(
	struct skill_command *cmd)
{
	if (cmd != NULL) {
		if (cmd->name != NULL) {
			free(cmd->name);
		}
		free(cmd);
	}
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Frees a hashtable associated with a skill
//
////////////////////////////////////////////////////////////////////////////////
static void skill_free_command_hashtable(
	struct skill_command *command_hash[SKILL_COMMAND_HASH_N_BINS])
{
	int i;
	struct skill_command *iter, *to_delete;

	// Loop over the bins and free the entire linked list in the bin
	for (i = 0; i < SKILL_COMMAND_HASH_N_BINS; ++i) {
		iter = command_hash[i];
		while (iter != NULL) {
			to_delete = iter;
			iter = iter->next;
			skill_free_command(to_delete);
		}
	}
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Cleans up a redis skill. Will deallocate all memory associated
//			with it and do any other necessary cleanup
//
////////////////////////////////////////////////////////////////////////////////
void skill_cleanup(
	redisContext *ctx,
	struct skill *skl)
{
	if (skl != NULL) {

		// Clean up the client
		if (skl->client != NULL) {
			client_cleanup(ctx, skl->client);
		}

		// Clean up the command stream
		if (skl->command_stream != NULL) {
			redis_remove_key(ctx, skl->command_stream, true);
			free(skl->command_stream);
		}

		// Clean up the response context
		if (skl->resp_ctx != NULL) {
			redis_context_cleanup(skl->resp_ctx);
		}

		// Clean up the hashtable
		skill_free_command_hashtable(skl->command_hash);

		// And free the skill itself
		free(skl);
	}
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Skill command hash function. For now just djb2.
//			See: http://www.cse.yorku.ca/~oz/hash.html
//
//			Note: this does modulate around the number of bins in the skill
//			hashtable. It is assumed that the output of this function is
//			a valid index into the skill hashtable
//
////////////////////////////////////////////////////////////////////////////////
uint32_t skill_command_hash_fn(
	const char *name)
{
    uint32_t hash = 5381;
    int c;

    while ((c = (uint8_t)(*name++))) {
        hash = ((hash << 5) + hash) + c; /* hash * 33 + c */
    }

    return hash & (SKILL_COMMAND_HASH_N_BINS - 1);
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Adds a command to a redis skill. This will create a node in
//			the skill's hashtable for the command and set all of the values
//			properly. The callback is called each time a client calls the
//			command and the timeout is sent in the initial ACK packet back
//			to the client to let them know how long to wait for a response
//			before timing out.
//
//			NOTE: this is thread-safe for a single skill adder and
//					multiple skill readers. It is not thread-safe for multiple
//					skill adder threads.
//
////////////////////////////////////////////////////////////////////////////////
bool skill_add_command(
	struct skill *skl,
	const char *command,
	int (*cb)(
		uint8_t *data,
		size_t data_len,
		uint8_t **response,
		size_t *response_len,
		char **error_str),
	int timeout)
{
	bool ret_val = false;
	struct skill_command *cmd = NULL;
	uint32_t hash;

	// Need to allocate the memory for the new command
	cmd = malloc(sizeof(struct skill_command));
	if (cmd == NULL) {
		fprintf(stderr, "Failed to allocate memory for command\n");
		goto done;
	}

	// Now that we've allocated the command, we should fill it in.
	// Start with the name
	cmd->name = strdup(command);
	if (cmd->name == NULL) {
		fprintf(stderr, "Failed to create name for command\n");
		goto err_free_cmd;
	}

	// Now fill in the callback and the timeout
	cmd->cb = cb;
	cmd->timeout = timeout;

	// Get the hash for the skill
	hash = skill_command_hash_fn(cmd->name);

	// Now, we want to insert the node into the hashtable. We'll
	//	do this at the *front* of the list s.t. we avoid any concurrency
	//	issues with someone reading at the same time since the swapout
	//	will be atomic. That said, this function is not thread-safe for
	//	multiple adds at the same time.
	cmd->next = skl->command_hash[hash];
	skl->command_hash[hash] = cmd;

	// Since we got here then we're good to go. Note the success
	//	Skip the freeing stack
	ret_val = true;
	goto done;

err_free_cmd:
	skill_free_command(cmd);
done:
	return ret_val;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Returns the callback for a skill command, if it is present
//			in the skill hashtable, else NULL
//
////////////////////////////////////////////////////////////////////////////////
struct skill_command *skill_get_command(
	struct skill *skl,
	const char *command)
{
	struct skill_command *cmd = NULL;
	struct skill_command *iter;

	// Get the list at the beginning of the bin for the hashtable
	iter = skl->command_hash[skill_command_hash_fn(command)];

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
//  @brief Initializes the shared aspects of the skill command data
//
////////////////////////////////////////////////////////////////////////////////
void skill_command_init_shared_data(
	struct skill *skl,
	const char *id,
	const char *client,
	struct redis_xadd_info *infos,
	char client_stream[STREAM_NAME_MAXLEN])
{
	infos[STREAM_KEY_SKILL].key = STREAM_KEY_SKILL_STR;
	infos[STREAM_KEY_SKILL].key_len = CONST_STRLEN(STREAM_KEY_SKILL_STR);
	infos[STREAM_KEY_SKILL].data = (uint8_t*)skl->client->name;
	infos[STREAM_KEY_SKILL].data_len = skl->client->name_len;

	infos[STREAM_KEY_ID].key = STREAM_KEY_ID_STR;
	infos[STREAM_KEY_ID].key_len = CONST_STRLEN(STREAM_KEY_ID_STR);
	infos[STREAM_KEY_ID].data = (uint8_t*)id;
	infos[STREAM_KEY_ID].data_len = strlen(id);

	// Get the client response stream name
	skills_get_client_response_stream(client, client_stream);
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Sends an ACK to the caller client letting them know that we
//			received their command
//
////////////////////////////////////////////////////////////////////////////////
bool skill_command_send_ack(
	redisContext *ctx,
	struct skill *skl,
	const char *id,
	const char *client,
	int timeout)
{
	struct redis_xadd_info ack_info[ACK_N_KEYS];
	bool ret_val = false;
	char timeout_buffer[32];
	size_t timeout_len;
	char client_stream[STREAM_NAME_MAXLEN];

	// Need to set up the XADD info to send back
	skill_command_init_shared_data(
		skl, id, client, ack_info, client_stream);

	// And fill in the ACK-specific data
	ack_info[ACK_KEY_TIMEOUT].key = ACK_KEY_TIMEOUT_STR;
	ack_info[ACK_KEY_TIMEOUT].key_len = CONST_STRLEN(ACK_KEY_TIMEOUT_STR);
	timeout_len = snprintf(
		timeout_buffer, sizeof(timeout_buffer), "%d", timeout);
	ack_info[ACK_KEY_TIMEOUT].data = (uint8_t*)timeout_buffer;
	ack_info[ACK_KEY_TIMEOUT].data_len = timeout_len;

	// Get the client response stream name
	skills_get_client_response_stream(client, client_stream);

	// And want to call the XADD to send the info back to the client
	if (!redis_xadd(
		ctx, client_stream, ack_info, ACK_N_KEYS,
		STREAM_DEFAULT_MAXLEN, STREAM_DEFAULT_APPROX_MAXLEN, NULL))
	{
		fprintf(stderr, "Failed to send ACK\n");
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
bool skill_command_send_response(
	redisContext *ctx,
	struct skill *skl,
	const char *id,
	const char *client,
	struct skill_command *cmd,
	uint8_t *response,
	size_t response_len,
	enum skills_error_t error_code,
	char *error_str)
{
	struct redis_xadd_info response_info[RESPONSE_N_KEYS];
	bool ret_val = false;
	char client_stream[STREAM_NAME_MAXLEN];
	char err_code_buffer[32];
	size_t err_code_len;
	int response_idx = STREAM_N_KEYS;

	// Need to set up the XADD info to send back
	skill_command_init_shared_data(
		skl, id, client, response_info, client_stream);

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

	// And want to call the XADD to send the info back to the client
	if (!redis_xadd(
		ctx, client_stream, response_info, response_idx,
		STREAM_DEFAULT_MAXLEN, STREAM_DEFAULT_APPROX_MAXLEN, NULL))
	{
		fprintf(stderr, "Failed to send response\n");
		goto done;
	}

	// Note the success
	ret_val = true;

done:
	return ret_val;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Skill callback from XREAD for when we get a command. Will check
//			to make sure that all of the necessary command fields
//			are present in the command request and also that we support
//			the passed command
//
////////////////////////////////////////////////////////////////////////////////
bool skill_command_xread_cb(
	const char *id,
	const struct redisReply *reply,
	void *user_data)
{
	bool ret_val = false;
	struct skill_command_data *data;
	struct skill_command *cmd;
	int ret, timeout;
	uint8_t *response = NULL;
	size_t response_len = 0;
	char *error_str = NULL;

	// Want to cast the user data to our expected data struct
	data = (struct skill_command_data *)user_data;

	// Update the most recent ID that we've seen for the skill's
	//	tracking buffer
	strncpy(data->skill->command_last_id, id, STREAM_ID_BUFFLEN);

	// Now, we want to parse out the reply array using our kv items
	if (!redis_xread_parse_kv(reply, data->kv_items, data->n_kv_items)) {
		fprintf(stderr, "Failed to parse reply!\n");
		goto done;
	}

	// The only other thing needed to not have a complete failure
	//	on this message is for the client key to exist in the
	//	message. Make sure that's there
	if (!data->kv_items[CMD_KEY_CLIENT].found) {
		fprintf(stderr, "Didn't get client in message!\n");
		goto done;
	}

	// Want to try to get the command s.t. we can get the timeout
	//	length to send back to the caller in the ACK
	cmd = data->kv_items[CMD_KEY_CMD].found ?
		skill_get_command(
			data->skill, data->kv_items[CMD_KEY_CMD].reply->str) :
		NULL;
	timeout = (cmd != NULL) ? cmd->timeout : SKILL_NO_COMMAND_TIMEOUT_MS;

	// At this point we know that we got a message and have a client
	//	to respond back to, so we need to send an ACK
	if (!skill_command_send_ack(
		data->skill->resp_ctx,
		data->skill,
		id,
		data->kv_items[CMD_KEY_CLIENT].reply->str,
		timeout))
	{
		fprintf(stderr, "Failed to send ACK to caller\n");
		goto done;
	}

	// Now, if we're missing the command it's either because the user
	//	didn't supply one or we don't support the requested command.
	//	Find the proper error and then send the user a response.
	if (cmd == NULL) {
		if (data->kv_items[CMD_KEY_CMD].found) {
			fprintf(stderr, "Unsupported command!\n");
			data->err_code = SKILLS_COMMAND_UNSUPPORTED;
		} else {
			fprintf(stderr, "Missing command!\n");
			data->err_code = SKILLS_COMMAND_INVALID_DATA;
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
			&error_str);

		// If the return is an error, we want to append it atop the internal
		//	skill errors
		if (ret != 0) {
			data->err_code = SKILLS_USER_ERRORS_BEGIN + ret;
		} else {
			data->err_code = SKILLS_NO_ERROR;
		}
	}

	// Now we want to send the response out to the caller
	if (!skill_command_send_response(
		data->skill->resp_ctx,
		data->skill,
		id,
		data->kv_items[CMD_KEY_CLIENT].reply->str,
		cmd,
		response,
		response_len,
		data->err_code,
		error_str))
	{
		fprintf(stderr, "Failed to send response to caller\n");
		goto done;
	}

	// Note the success
	ret_val = true;

done:
	// If the user allocated any memory, we need to free it up here
	if (response != NULL) {
		free(response);
	}
	if (error_str != NULL) {
		free(error_str);
	}
	return ret_val;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Runs the skill command monitoring loop. Will handle commands
//			and call the command callbacks in the hashtable if/when
//			a command comes. Loop == false causes the XREAD for commands
//			only to be run once, else infinitely. If timeout is nonzero
//			then we will return with a failure after timeout ms of not
//			gettin a command.
//
////////////////////////////////////////////////////////////////////////////////
enum skills_error_t skill_command_loop(
	redisContext *ctx,
	struct skill *skl,
	bool loop,
	int timeout)
{
	struct redis_stream_info stream_info;
	struct skill_command_data cmd_data;
	struct redis_xread_kv_item cmd_kv_items[CMD_N_KEYS];
	enum skills_error_t ret = SKILLS_INTERNAL_ERROR;

	// Set up the kv items
	cmd_kv_items[CMD_KEY_CLIENT].key = COMMAND_KEY_CLIENT_STR;
	cmd_kv_items[CMD_KEY_CLIENT].key_len = CONST_STRLEN(COMMAND_KEY_CLIENT_STR);
	cmd_kv_items[CMD_KEY_CMD].key = COMMAND_KEY_COMMAND_STR;
	cmd_kv_items[CMD_KEY_CMD].key_len = CONST_STRLEN(COMMAND_KEY_COMMAND_STR);
	cmd_kv_items[CMD_KEY_DATA].key = COMMAND_KEY_DATA_STR;
	cmd_kv_items[CMD_KEY_DATA].key_len = CONST_STRLEN(COMMAND_KEY_DATA_STR);

	// Set up the command data
	cmd_data.skill = skl;
	cmd_data.kv_items = cmd_kv_items;
	cmd_data.n_kv_items = CMD_N_KEYS;
	cmd_data.err_code = SKILLS_INTERNAL_ERROR;

	// Want to set up the XREAD. Should be a pretty straightforward
	//	setup of the stream info
	if (!redis_init_stream_info(
		ctx,
		&stream_info,
		skl->command_stream,
		skill_command_xread_cb,
		skl->command_last_id,
		&cmd_data))
	{
		fprintf(stderr, "Failed to initialize stream info\n");
		goto done;
	}

	// Now that we've initialized the stream info, we want to go ahead and
	//	call the XREAD! Pretty simple.
	while (true) {

		// Do the xread
		if (!redis_xread(ctx, &stream_info, 1, timeout)) {
			fprintf(stderr, "Redis issue/timeout\n");
			ret = SKILLS_REDIS_ERROR;
		}

		// And if we shouldn't be looping then break out
		if (!loop) {
			break;
		}
	}

	// Note the lack of error
	ret = SKILLS_NO_ERROR;

done:
	return ret;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Cleans up a stream
//
////////////////////////////////////////////////////////////////////////////////
void skill_cleanup_stream(
	redisContext *ctx,
	struct skill_stream *stream)
{
	if (stream != NULL) {

		// Free the stream infos
		if (stream->droplet_items != NULL) {
			free(stream->droplet_items);
		}

		// Remove the stream key
		redis_remove_key(ctx, stream->stream, true);

		// Free the stream itself
		free(stream);
	}
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Initializes a stream. Will allocate the memory for the stream
//			and get the name of the stream
//
////////////////////////////////////////////////////////////////////////////////
struct skill_stream *skill_init_stream(
	redisContext *ctx,
	struct skill *skl,
	const char *name,
	int n_droplet_items)
{
	struct skill_stream *stream = NULL;

	// Allocate the memory for the stream
	stream = malloc(sizeof(struct skill_stream));
	if (stream == NULL) {
		fprintf(stderr, "Failed to allocate memory for stream\n");
		goto stream_err_cleanup;
	}

	// Allocate the memory for the infos for the droplets
	stream->droplet_items = malloc(
		sizeof(struct redis_xadd_info) *
			(n_droplet_items + DROPLET_N_ADDITIONAL_KEYS));
	if (stream->droplet_items == NULL) {
		fprintf(stderr, "Failed to allocate memory for droplet items!\n");
		goto stream_err_cleanup;
	}

	// Set up the stream name
	skills_get_droplet_stream(skl->client->name, name, stream->stream);

	// Note the number of droplet items
	stream->n_droplet_items = n_droplet_items;

	// Since we made it here and we're all set we can just go ahead
	//	and exit out
	goto done;

stream_err_cleanup:
	skill_cleanup_stream(ctx, stream);
	stream = NULL;
done:
	return stream;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Adds a stream to a stream. User will set up the custom
//			xinfos data to be passed
//
////////////////////////////////////////////////////////////////////////////////
enum skills_error_t skill_add_droplet(
	redisContext *ctx,
	struct skill_stream *stream,
	int timestamp,
	int maxlen)
{
	enum skills_error_t ret = SKILLS_INTERNAL_ERROR;
	size_t n_infos;
	char timestamp_buffer[64];
	size_t timestamp_buffer_len;

	// Initialize the number of infos to that of the stream itself
	n_infos = stream->n_droplet_items;

	// If the timestamp is not the default then we want to add it to
	//	the infos and note the new number of infos
	if (timestamp != SKILL_DROPLET_DEFAULT_TIMESTAMP) {

		// Make the string
		timestamp_buffer_len = snprintf(
			timestamp_buffer, sizeof(timestamp_buffer), "%d", timestamp);

		// Add it to the droplet items
		// Initialize the timestamp key and key len
		stream->droplet_items[n_infos + DROPLET_KEY_TIMESTAMP].key =
			DROPLET_KEY_TIMESTAMP_STR;
		stream->droplet_items[n_infos + DROPLET_KEY_TIMESTAMP].key_len =
			CONST_STRLEN(DROPLET_KEY_TIMESTAMP_STR);
		stream->droplet_items[n_infos + DROPLET_KEY_TIMESTAMP].data =
			(uint8_t*)timestamp_buffer;
		stream->droplet_items[n_infos + DROPLET_KEY_TIMESTAMP].data_len =
			timestamp_buffer_len;

		// Note the new number of infos
		++n_infos;
	}

	// And we want to XADD the data to the stream to create it. This will
	//	also put the ID of the item in the stream that we added with our
	//	info into our last id
	if (!redis_xadd(
		ctx,
		stream->stream,
		stream->droplet_items,
		n_infos,
		maxlen,
		STREAM_DEFAULT_APPROX_MAXLEN,
		NULL))
	{
		fprintf(stderr, "Failed to publish droplet on stream\n");
		ret = SKILLS_REDIS_ERROR;
		goto done;
	}

	// Note the success
	ret = SKILLS_NO_ERROR;

done:
	return ret;
}

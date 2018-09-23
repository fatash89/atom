////////////////////////////////////////////////////////////////////////////////
//
//  @file client.c
//
//  @brief Implements functionality of a skills client.
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
#include "skills.h"
#include "client.h"
#include "skill.h"

#define SKILL_COMMAND_ACK_TIMEOUT 100000

// Struct for handling a response on the command stream. Will be passed
//	to the XREAD as the user data.
struct client_response_stream_data {
	struct client *client;
	const char *skill;
	const char *cmd_id;
	struct redis_xread_kv_item *kv_items;
	size_t n_kv_items;
	bool (*user_cb)(
		const struct redis_xread_kv_item *kv_items,
		void* user_data);
	void *user_data;
};

// Data we want to obtain from the ACK
struct client_send_command_ack_data {
	bool found_ack;
	int timeout;
};

// Data we want to obtain from the response
struct client_send_command_response_data {
	bool found_response;
	bool (*response_cb)(const uint8_t *response, size_t response_len);
	int error_code;
};

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Initializes a redis client. MUST be cleaned up by passing the
//			struct returned to client_cleanup when done. Note that the context
//			isn't associated with the client. All functionaity is indifferent
//			to which redis context is being used
//
////////////////////////////////////////////////////////////////////////////////
struct client* client_init(
	redisContext *ctx,
	const char *name)
{
	struct redis_xadd_info client_info[2];
	struct client *clnt;

	// First, need to make the struct for the client itself
	clnt = malloc(sizeof(struct client));
	assert(clnt != NULL);

	// Copy over the name
	clnt->name = strdup(name);
	assert(clnt->name != NULL);
	clnt->name_len = strlen(clnt->name);

	// Make the response stream name
	clnt->response_stream = skills_get_client_response_stream(name, NULL);
	assert(clnt->response_stream != NULL);

	// We want to initialize the client information and call an XADD
	//	to create our client's response stream
	client_info[0].key = SKILLS_LANGUAGE_KEY;
	client_info[0].key_len = CONST_STRLEN(SKILLS_LANGUAGE_KEY);
	client_info[0].data = (uint8_t*)SKILLS_LANGUAGE;
	client_info[0].data_len = CONST_STRLEN(SKILLS_LANGUAGE);
	client_info[1].key = SKILLS_VERSION_KEY;
	client_info[1].key_len = CONST_STRLEN(SKILLS_VERSION_KEY);
	client_info[1].data = (uint8_t*)SKILLS_VERSION;
	client_info[1].data_len = CONST_STRLEN(SKILLS_VERSION);

	// And we want to XADD the data to the stream to create it. This will
	//	also put the ID of the item in the stream that we added with our
	//	info into our last id
	assert(redis_xadd(
		ctx, clnt->response_stream, client_info, 2,
		STREAM_DEFAULT_MAXLEN, STREAM_DEFAULT_APPROX_MAXLEN,
		clnt->response_last_id));

	return clnt;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Cleans up the client named name
//
////////////////////////////////////////////////////////////////////////////////
void client_cleanup(
	redisContext *ctx,
	struct client *clnt)
{
	if (clnt != NULL) {
		if (clnt->response_stream != NULL) {
			redis_remove_key(ctx, clnt->response_stream, true);
			free(clnt->response_stream);
		}
		if (clnt->name != NULL) {
			free(clnt->name);
		}
		free(clnt);
	}
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief ACK data callback on the client stream. Will be called once an
//			ACK (or similar) packet is received and will try to get the
//			timeout and note the success of the ACK.
//
////////////////////////////////////////////////////////////////////////////////
bool client_send_command_ack_callback(
	const struct redis_xread_kv_item *kv_items,
	void *user_data)
{
	struct client_send_command_ack_data *data;

	// Cast the user data to the client_send_command_data
	data = (struct client_send_command_ack_data*)user_data;

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
//  @brief Response data callback on the client stream. Will be called once
//			a response (or similar) packet is received and will
//			make sure all of the items are there and valid
//
////////////////////////////////////////////////////////////////////////////////
bool client_send_command_response_callback(
	const struct redis_xread_kv_item *kv_items,
	void *user_data)
{
	struct client_send_command_response_data *data;
	int skill_err;

	// Cast the user data to the client_send_command_data
	data = (struct client_send_command_response_data*)user_data;

	// Now, want to make sure all necessary fields were found,
	//	and are the right type.
	if ((kv_items[RESPONSE_KEY_CMD].found) &&
		(kv_items[RESPONSE_KEY_CMD].reply->type == REDIS_REPLY_STRING) &&
		(kv_items[RESPONSE_KEY_ERR_CODE].found) &&
		(kv_items[RESPONSE_KEY_ERR_CODE].reply->type == REDIS_REPLY_STRING))
	{
		// Note that we found the response
		data->found_response = true;

		// Get the error code from the skill
		skill_err = atoi(kv_items[RESPONSE_KEY_ERR_CODE].reply->str);

		// If we had a successful response from the skill
		if (skill_err == SKILLS_NO_ERROR) {

			// Note that there's no error, for now
			data->error_code = SKILLS_NO_ERROR;

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
					kv_items[RESPONSE_KEY_DATA].reply->len))
				{
					data->error_code = SKILLS_CALLBACK_FAILED;
				}
			}

		// Process the error code and error string
		} else {

			// Note the error code
			data->error_code = skill_err;

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
//  @brief Callback for all XREADS from the client's command stream
//
////////////////////////////////////////////////////////////////////////////////
bool client_response_stream_callback(
	const char *id,
	const struct redisReply *reply,
	void *user_data)
{
	struct client_response_stream_data *data;
	bool ret_val = false;

	// Cast the user data to the client_send_command_data
	data = (struct client_response_stream_data*)user_data;

	// Update the most recent ID that we've seen for the client's
	//	tracking buffer
	strncpy(data->client->response_last_id, id, STREAM_ID_BUFFLEN);

	// Now, we want to parse out the reply array using our kv items
	if (!redis_xread_parse_kv(reply, data->kv_items, data->n_kv_items)) {
		fprintf(stderr, "Failed to parse reply!\n");
		goto done;
	}

	// Now, we want to check to see if the skill was found and if it
	//	matches
	if (data->kv_items[STREAM_KEY_SKILL].found &&
		(data->kv_items[STREAM_KEY_SKILL].reply->type == REDIS_REPLY_STRING) &&
		!strcmp(data->kv_items[STREAM_KEY_SKILL].reply->str, data->skill))
	{
		// If the skill matches, check to see if the ID matches
		if (data->kv_items[STREAM_KEY_ID].found &&
			(data->kv_items[STREAM_KEY_ID].reply->type == REDIS_REPLY_STRING) &&
			!strcmp(data->kv_items[STREAM_KEY_ID].reply->str, data->cmd_id))
		{
			// If we're here then we know that the skill matches and
			//	the command ID matches. At this point we should call the
			//	user callback s.t. it can check the rest of the data
			if (!data->user_cb(data->kv_items, data->user_data)) {
				fprintf(stderr, "Failed to call user callback!\n");
				goto done;
			}

		}
	}

	// Note the success
	ret_val = true;

done:
	return ret_val;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief initializes the xadd data for sending a command
//
////////////////////////////////////////////////////////////////////////////////
static void client_send_command_init_cmd_data(
	struct redis_xadd_info cmd_data[CMD_N_KEYS],
	const char *client_name,
	size_t client_name_len,
	const char *command,
	const uint8_t *data,
	size_t data_len)
{
	cmd_data[CMD_KEY_CLIENT].key = COMMAND_KEY_CLIENT_STR;
	cmd_data[CMD_KEY_CLIENT].key_len = CONST_STRLEN(COMMAND_KEY_CLIENT_STR);
	cmd_data[CMD_KEY_CLIENT].data = (uint8_t*)client_name;
	cmd_data[CMD_KEY_CLIENT].data_len = client_name_len;

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
//  @brief Initializes for a general XREAD on a response stream
//
////////////////////////////////////////////////////////////////////////////////
static void client_response_stream_init_data(
	struct redis_stream_info *stream_info,
	struct client_response_stream_data *data,
	struct client *clnt,
	const char *skill,
	const char *cmd_id,
	struct redis_xread_kv_item *kv_items,
	size_t n_kv_items,
	bool (*user_cb)(
		const struct redis_xread_kv_item *kv_items,
		void* user_data),
	void *user_data)
{
	// Initialize all of the necessary fields of the data
	data->client = clnt;
	data->skill = skill;
	data->cmd_id = cmd_id;
	data->user_data = user_data;
	data->user_cb = user_cb;
	data->kv_items = kv_items;
	data->n_kv_items = n_kv_items;

	// Initialize the shared keys in the kv_items for any
	//	response on the stream
	kv_items[STREAM_KEY_SKILL].key = STREAM_KEY_SKILL_STR;
	kv_items[STREAM_KEY_SKILL].key_len = CONST_STRLEN(STREAM_KEY_SKILL_STR);
	kv_items[STREAM_KEY_ID].key = STREAM_KEY_ID_STR;
	kv_items[STREAM_KEY_ID].key_len = CONST_STRLEN(STREAM_KEY_ID_STR);

	// Finally we want to set up the stream info. This will tell the
	//	XREAD which stream to monitor, the data callback to call when
	//	we get data, from where to start monitoring the stream and the
	//	user pointer to pass along to the data callback
	redis_init_stream_info(
		NULL,
		stream_info,
		clnt->response_stream,
		client_response_stream_callback,
		clnt->response_last_id,
		data);
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief initializes the ACK items for sending a command.
//
////////////////////////////////////////////////////////////////////////////////
static void client_send_command_init_ack_data(
	struct client_send_command_ack_data *ack_data,
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
static void client_send_command_init_response_data(
	struct client_send_command_response_data *response_data,
	struct redis_xread_kv_item response_items[STREAM_N_KEYS],
	bool (*response_cb)(const uint8_t *response, size_t response_len))
{
	// Note that we haven't found the ack
	response_data->found_response = false;

	// And note the user response callback
	response_data->response_cb = response_cb;

	// Finally note the user-allocated status struct
	response_data->error_code = SKILLS_INTERNAL_ERROR;

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
//  @brief Sends a command from the client to a skill. If block=TRUE will
//			wait for the command to get a response. If block=True AND
//			response_cb != NULL then will call the response_cb with the
//			data payload that came back in the response.
//
////////////////////////////////////////////////////////////////////////////////
enum skills_error_t client_send_command(
	redisContext *ctx,
	struct client *clnt,
	const char *skill,
	const char *command,
	uint8_t *data,
	size_t data_len,
	bool block,
	bool (*response_cb)(const uint8_t *response, size_t response_len))
{
	int ret;
	struct redis_stream_info stream_info;
	struct redis_xadd_info cmd_data[CMD_N_KEYS];
	char skill_stream[STREAM_NAME_MAXLEN];
	char cmd_id[STREAM_ID_BUFFLEN];

	struct client_response_stream_data stream_data;

	struct client_send_command_ack_data ack_data;
	struct redis_xread_kv_item ack_items[ACK_N_KEYS];

	struct client_send_command_response_data response_data;
	struct redis_xread_kv_item response_items[RESPONSE_N_KEYS];

	// Initialize the error code
	ret = SKILLS_INTERNAL_ERROR;

	// Want to set up the data for the command
	client_send_command_init_cmd_data(
		cmd_data, clnt->name, clnt->name_len, command, data, data_len);

	// Get the name of the skill stream we want to write to
	skills_get_skill_command_stream(skill, skill_stream);

	// Now, call the XADD to send the data over to the client. We want to
	//	note the command ID since we'll expect it back in the ACK and response
	if (!redis_xadd(ctx, skill_stream, cmd_data, CMD_N_KEYS,
		STREAM_DEFAULT_MAXLEN, STREAM_DEFAULT_APPROX_MAXLEN, cmd_id))
	{
		fprintf(stderr, "Failed to XADD command data to stream\n");
		ret = SKILLS_REDIS_ERROR;
		goto done;
	}

	// Need to set up the ack. This will initialize our user data
	//	and set up the keys we're looking for in the ack
	client_send_command_init_ack_data(&ack_data, ack_items);
	// Need to set up the general response callback
	client_response_stream_init_data(
		&stream_info, &stream_data, clnt, skill, cmd_id, ack_items,
		ACK_N_KEYS, client_send_command_ack_callback, &ack_data);

	// Now, we're ready to call the XREAD. We want to do this until either
	//	the ACK is found or we've timed out. Note that this re-does the
	//	timeout each time we get a message which is not ideal.
	while (!ack_data.found_ack) {
		// XREAD with a default timeout since the ACK should come quickly
		if (!redis_xread(ctx, &stream_info, 1, SKILL_COMMAND_ACK_TIMEOUT)) {
			ret = SKILLS_COMMAND_NO_ACK;
			fprintf(stderr, "Failed to get ACK\n");
			goto done;
		}
	}

	// Now, if we're not blocking then we're all done! We can just return
	//	out noting the success. Else we need to again do an XREAD on the
	//	stream and pass the data along to the command handler.
	if (!block) {
		ret = SKILLS_NO_ERROR;
		goto done;
	}

	// Need to set up the response. This will initialize our user data
	//	and set up the keys we're looking for in the ack
	client_send_command_init_response_data(
		&response_data, response_items, response_cb);
	// Need to set up the general response callback
	client_response_stream_init_data(
		&stream_info, &stream_data, clnt, skill, cmd_id, response_items,
		RESPONSE_N_KEYS, client_send_command_response_callback,
		&response_data);

	// Now, we're ready to call the XREAD. Want to do this until either
	//	the response is found or we've timed out. Note that this re-does the
	//	timeout each time we get a message which is not ideal.
	while (!response_data.found_response) {
		// XREAD with the timeout returned from the ACK
		if (!redis_xread(ctx, &stream_info, 1, ack_data.timeout)) {
			ret = SKILLS_COMMAND_NO_RESPONSE;
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

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Generic callback for when we get an XREAD on a stream
//			we were listening to. Will process the kv items
//			and then call the user callback with the kv items
//
////////////////////////////////////////////////////////////////////////////////
bool client_droplet_cb(
	const char *id,
	const struct redisReply *reply,
	void *user_data)
{
	bool ret_val = false;
	struct client_droplet_info *info;

	// Cast the user data to a client listen stream info
	info = (struct client_droplet_info *)user_data;

	// Now, we want to parse the reply into the kv items
	if (!redis_xread_parse_kv(reply, info->kv_items, info->n_kv_items)) {
		fprintf(stderr, "Failed to parse reply!\n");
		goto done;
	}

	// Send the kv items along to the user response
	if (!info->response_cb(info->kv_items, info->n_kv_items, info->user_data)) {
		fprintf(stderr, "Failed to call user response callback with kv items\n");
		goto done;
	}

	// Note the success
	ret_val = true;

done:
	return ret_val;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Allows the client to listen for droplets on a set of streams.
//			Each info specifies the stream to listen on as well as the expected
//			data for each stream. The given data callback will then be called
//			with the redis_xread_kv_items indicating whether each item
//			was found and if so pointing to the base redisReply for the
//			item in the response
//
////////////////////////////////////////////////////////////////////////////////
enum skills_error_t client_droplet_loop(
	redisContext *ctx,
	struct client *clnt,
	struct client_droplet_info *infos,
	size_t n_infos,
	bool loop,
	int timeout)
{
	int ret;
	struct redis_stream_info *stream_info = NULL;
	int i;
	char *stream_name;

	// Initialize the return to an internal error
	ret = SKILLS_INTERNAL_ERROR;

	// Need to allocate the stream info where we have one info
	//	for each stream we want to listen to
	stream_info = malloc(n_infos * sizeof(struct redis_stream_info));
	if (stream_info == NULL) {
		fprintf(stderr, "Failed to malloc stream_infos\n");
		goto done;
	}
	memset(stream_info, 0, n_infos * sizeof(struct redis_stream_info));

	// Now we want to loop over the stream infos and initialize them
	//	with their respective data
	for (i = 0; i < n_infos; ++i) {

		// Get the full stream name for the stream
		stream_name = skills_get_droplet_stream(
			infos[i].skill, infos[i].stream, NULL);
		if (stream_name == NULL) {
			fprintf(stderr, "Failed to get stream name!\n");
			goto free_stream_info;
		}

		// And initialize the stream info for the stream
		redis_init_stream_info(
			ctx,
			&stream_info[i],
			stream_name,
			client_droplet_cb,
			NULL,
			&infos[i]);
	}

	// Now that we've initialized the stream info, we want to go ahead and
	//	call the XREAD! Pretty simple.
	while (true) {

		// Do the xread
		if (!redis_xread(ctx, stream_info, n_infos, timeout)) {
			fprintf(stderr, "Redis issue/timeout\n");
			ret = SKILLS_REDIS_ERROR;
			goto free_stream_info;
		}

		// And if we shouldn't be looping then break out
		if (!loop) {
			break;
		}
	}

	// If we got here then it was a success!
	ret = SKILLS_NO_ERROR;

free_stream_info:
	for (i = 0; i < n_infos; ++i) {
		free((char*)stream_info[i].name);
	}
	free(stream_info);
done:
	return ret;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Get the N most recent items on a stream
//
////////////////////////////////////////////////////////////////////////////////
enum skills_error_t client_droplet_get_n_most_recent(
	redisContext *ctx,
	struct client *clnt,
	struct client_droplet_info *info,
	size_t n)
{
	int ret = SKILLS_INTERNAL_ERROR;
	char stream_name[STREAM_NAME_MAXLEN];

	// Get the stream name
	skills_get_droplet_stream(info->skill, info->stream, stream_name);

	// Want to initialize the stream info
	if (!redis_xrevrange(ctx, stream_name, client_droplet_cb, n, info)) {
		fprintf(stderr, "Failed to call XREVRANGE\n");
		ret = SKILLS_REDIS_ERROR;
		goto done;
	}

	// Note the success
	ret = SKILLS_NO_ERROR;

done:
	return ret;
}

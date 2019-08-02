////////////////////////////////////////////////////////////////////////////////
//
//  @file redis.c
//
//  @brief Implements basic wrappers for redis functionality that needs
//			it, primarily xread.
//
//  @copy 2018 Elementary Robotics. All rights reserved.
//
////////////////////////////////////////////////////////////////////////////////
#include <stdio.h>
#include <hiredis/hiredis.h>
#include <pthread.h>
#include <stdbool.h>
#include <string.h>

#include "redis.h"

// If this is 1 then will print out each redis command before sending
//	it s.t. we can see what's going on in the system
#define DEBUG_COMMANDS 0

#define REDIS_CMD_BUFFER_LEN 1024

#define REDIS_XADD_MAX_ARGS 64
#define REDIS_XADD_CMD_STR "XADD"
#define REDIS_XADD_ID_STR "*"
#define REDIS_XADD_MAXLEN_STR "MAXLEN"
#define REDIS_XADD_MAXLEN_APPROX_STR "~"
#define REDIS_XADD_MAXLEN_BUFFLEN 32

#define REDIS_XREAD_MAX_ARGS 64
#define REDIS_XREAD_CMD_STR "XREAD"
#define REDIS_XREAD_BLOCK_STR "BLOCK"
#define REDIS_XREAD_COUNT_STR "COUNT"
#define REDIS_XREAD_STREAMS_STR "STREAMS"

#define REDIS_SCAN_BEGIN_ITERATOR "0"
#define REDIS_SCAN_ITERATOR_BUFFLEN 32
#define REDIS_SCAN_N_ARGS 4
#define REDIS_SCAN_CMD_STR "SCAN"
#define REDIS_SCAN_MATCH_STR "MATCH"

#define REDIS_REMOVE_KEY_N_ARGS 2
#define REDIS_REMOVE_KEY_DEL_STR "DEL"
#define REDIS_REMOVE_KEY_UNLINK_STR "UNLINK"

// LUT for redis type strings
const char *const redis_reply_type_strs[] = {
	[0] = "undefined",
	[REDIS_REPLY_STRING] = "string",
	[REDIS_REPLY_ARRAY] = "array",
	[REDIS_REPLY_INTEGER] = "integer",
	[REDIS_REPLY_NIL] = "nil",
	[REDIS_REPLY_STATUS] = "status",
	[REDIS_REPLY_ERROR] = "error",
};

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Prints out a redis reply recursively. When calling from the
//			top level, call with (0, 0, reply). The first parameter is the
//			depth into redis arrays and the second parameter is the indix
//			into the array at the current level.
//
////////////////////////////////////////////////////////////////////////////////
void redis_print_reply(
	int depth,
	int elem,
	const redisReply *reply)
{
	int i;
	fprintf(stderr, "Depth: %d, elem: %d, ", depth, elem);

	switch(reply->type) {
		case REDIS_REPLY_STRING:
			fprintf(stderr, "%s: %s\n",
				redis_reply_type_strs[reply->type], reply->str);
			break;
		case REDIS_REPLY_ARRAY:
			fprintf(stderr, "%s\n",
				redis_reply_type_strs[reply->type]);
			for (i = 0; i < reply->elements; ++ i) {
				redis_print_reply(depth + 1, i, reply->element[i]);
			}
			break;
		case REDIS_REPLY_INTEGER:
			fprintf(stderr, "%s: %lld\n",
				redis_reply_type_strs[reply->type], reply->integer);
			break;
		case REDIS_REPLY_NIL:
			fprintf(stderr, "%s\n",
				redis_reply_type_strs[reply->type]);
			break;
		case REDIS_REPLY_STATUS:
			fprintf(stderr, "%s: %s\n",
				redis_reply_type_strs[reply->type], reply->str);
			break;
		case REDIS_REPLY_ERROR:
			fprintf(stderr, "%s\n",
				redis_reply_type_strs[reply->type]);
			break;
		default:
			fprintf(stderr, "Invalid type %d!\n", reply->type);
			break;
	}
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Prints out xread kv items
//
////////////////////////////////////////////////////////////////////////////////
void redis_print_xread_kv_items(
	const struct redis_xread_kv_item *items,
	size_t n_items)
{
	int i;
	int n_types = sizeof(redis_reply_type_strs) / sizeof(const char *const);

	for (i = 0; i < n_items; ++i) {
		fprintf(stderr, "kv item %d, key '%s', found %s, type '%s', value '%s'\n",
			i, items[i].key, items[i].found ? "true" : "false",
			(items[i].found ? ((items[i].reply->type < n_types) ?
				redis_reply_type_strs[items[i].reply->type] : "invalid") : "N/A"),
			(items[i].found ? items[i].reply->str : "N/A"));
	}
}


////////////////////////////////////////////////////////////////////////////////
//
//  @brief Handles the response from an xread. Will loop over the streams
//			and pass along the data from the response to each of the given
//			callbacks. Will also update the last known ID in the stream infos
//			s.t. on our next call we get the correct data
//
////////////////////////////////////////////////////////////////////////////////
static bool redis_xread_process_response(
	struct redisReply *reply,
	struct redis_stream_info *infos,
	int n_infos)
{
	bool ret_val = false;
	redisReply *stream_array, *data_array, *data_point;
	const char *name;
	size_t stream, point;
	int info;
	struct redis_stream_info *found_info;

	// The first element of the reply should be an array
	if (reply->type != REDIS_REPLY_ARRAY) {
		fprintf(stderr, "Level 0 is not array!\n");
		goto done;
	}

	// Now, we want to loop over the elements of the array. Each element
	//	should again be an array where the first item in the array is
	//	a stream name
	for (stream = 0; stream < reply->elements; stream++) {

		// Get the stream array. It should be an array with 2 elements
		stream_array = reply->element[stream];
		if ((stream_array->type != REDIS_REPLY_ARRAY) ||
			(stream_array->elements != 2))
		{
			fprintf(stderr, "Stream array incorrect!\n");
			goto done;
		}

		// Now we want to check for the stream name and make sure we have a
		//	corresponding stream info. If we don't have a stream info then
		//	we'll just move on
		if (stream_array->element[0]->type != REDIS_REPLY_STRING) {
			fprintf(stderr, "Stream name is not a string!\n");
			goto done;
		}
		name = stream_array->element[0]->str;
		found_info = NULL;
		for (info = 0; info < n_infos; ++info) {
			// TODO: something safer/better than strcmp() and strlen()
			if ((strlen(infos[info].name) == strlen(name)) &&
				strcmp(infos[info].name, name) == 0) {
				found_info = &infos[info];
				break;
			}
		}
		if (found_info == NULL) {
			fprintf(stderr, "No matching stream for %s in infos\n", name);
			continue;
		}

		// If we got here then we have a matching stream. We want to take the
		//	second item in the stream array as this is the array of
		//	datapoints
		data_array = stream_array->element[1];
		if (data_array->type != REDIS_REPLY_ARRAY) {
			fprintf(stderr, "Data is not an array!\n");
			goto done;
		}

		// Note how many elements we read
		found_info->items_read = data_array->elements;

		// Now, we want to loop over the datapoints in the data array
		for (point = 0; point < data_array->elements; ++point) {

			// Note the data point
			data_point = data_array->element[point];
			if (data_point->type != REDIS_REPLY_ARRAY) {
				fprintf(stderr, "Data point is not an array!\n");
				goto done;
			}

			// Now, the first item in the array should be a string and the
			//	second should be an array of data that we'll pass to the
			//	callback handler. Want to note that we saw this point, since
			//	even if the handler fails we did process the data
			if (data_point->element[0]->type != REDIS_REPLY_STRING) {
				fprintf(stderr, "Item ID is not string!\n");
				goto done;
			}
			// Update the last seen ID for the stream
			strncpy(found_info->last_id, data_point->element[0]->str,
				sizeof(found_info->last_id));

			if (data_point->element[1]->type != REDIS_REPLY_ARRAY) {
				fprintf(stderr, "Item value is not array!\n");
				goto done;
			}

			// Finally, now that we've verified all of this we're ready to
			//	go ahead and send the data to the callback
			if (!found_info->data_cb(
				data_point->element[0]->str,
				data_point->element[1],
				found_info->user_data))
			{
				fprintf(stderr, "Failed data callback\n");
			}
		}
	}

	// At this point we should have processed the whole reply. Nothing to free
	//	in here so just note the success
	ret_val = true;

done:
	return ret_val;
}

////////////////////////////////////////////////////////////////////////////////
//
// 	@brief	Performs an XREAD of the passed infos and calls the callback
//			associated with the info for any data that comes through. In
//			this manner we get a clean, zero-copy implementation of
//			XREAD data passing as we'll call the callbacks while we're
//			running through the response. This function will also
//			set up the XREAD call.
//
////////////////////////////////////////////////////////////////////////////////
bool redis_xread(
	redisContext *ctx,
	struct redis_stream_info *infos,
	int n_infos,
	int block,
	size_t maxcount)
{
	const char *argv[REDIS_XREAD_MAX_ARGS];
	size_t argvlen[REDIS_XREAD_MAX_ARGS];
	char block_buffer[32];
	char count_buffer[32];
	size_t len;
	int argc = 0;
	bool ret_val = false;
	int i;
	struct redisReply *reply;

	// Put in the XREAD command
	argv[argc] = REDIS_XREAD_CMD_STR;
	argvlen[argc++] = CONST_STRLEN(REDIS_XREAD_CMD_STR);

	// If we're blocking, add in the BLOCK command
	if (block != REDIS_XREAD_DONTBLOCK) {
		if (block < 0) {
			fprintf(stderr, "Invalid block!\n");
			goto done;
		}

		argv[argc] = REDIS_XREAD_BLOCK_STR;
		argvlen[argc++] = CONST_STRLEN(REDIS_XREAD_BLOCK_STR);

		// Need to add in the block number
		len = snprintf(block_buffer, sizeof(block_buffer), "%d", block);
		argv[argc] = block_buffer;
		argvlen[argc++] = len;
	}

	// If we have a maxcount, add that in as well
	if (maxcount != REDIS_XREAD_NOMAXCOUNT) {
		argv[argc] = REDIS_XREAD_COUNT_STR;
		argvlen[argc++] = CONST_STRLEN(REDIS_XREAD_COUNT_STR);

		// Need to add in the count number
		len = snprintf(count_buffer, sizeof(count_buffer), "%lu", maxcount);
		argv[argc] = count_buffer;
		argvlen[argc++] = len;
	}

	// Add in the streams key
	argv[argc] = REDIS_XREAD_STREAMS_STR;
	argvlen[argc++] = CONST_STRLEN(REDIS_XREAD_STREAMS_STR);

	// Now, for each of the streams, need to add in the stream name.
	//	The good news is that we can just reuse their buffers
	for (i = 0; i < n_infos; ++i) {
		argv[argc] = infos[i].name;
		argvlen[argc++] = strlen(infos[i].name);
	}

	// And we need to add in the last seen ID for each stream
	for (i = 0; i < n_infos; ++i) {
		argv[argc] = infos[i].last_id;
		argvlen[argc++] = strlen(infos[i].last_id);
	}

	// Now we should have a constructed XREAD command which we
	//	can send to redis and then attempt to get the reply
	reply = redisCommandArgv(ctx, argc, argv, argvlen);
	if (reply == NULL) {
		fprintf(stderr, "NULL from redisCommand\n");
		goto done;
	}

	// If we timed out reply should be false
	if (reply->type == REDIS_REPLY_NIL) {
		ret_val = false;
		goto free_reply;
	}

	// Now, if we got here, we got data on at least 1 stream. We'll want to
	//	process the response
	if (!redis_xread_process_response(reply, infos, n_infos)) {
		fprintf(stderr, "Failed to process response\n");
		goto free_reply;
	}

	// Note the success
	ret_val = true;

free_reply:
	freeReplyObject(reply);
done:
	return ret_val;
}

////////////////////////////////////////////////////////////////////////////////
//
// 	@brief	Parses the (key, value) array that we get back from an XREAD
//			in an efficient manner. Fills in the infos passed to see if
//			(1) they were all found and (2) if found their redisReply item
//
////////////////////////////////////////////////////////////////////////////////
bool redis_xread_parse_kv(
	const redisReply *reply,
	struct redis_xread_kv_item *items,
	size_t n_items)
{
	int idx, item;
	bool ret_val = false;

	// Initialize all of the found fields to false
	for (item = 0; item < n_items; ++item) {
		items[item].found = false;
	}

	// Make sure there's an even number of elements in the array. It should
	//	be a list of key1, value1, key2, value2, etc.
	if (reply->elements & 0x1) {
		fprintf(stderr, "Odd number of elements!\n");
		goto done;
	}

	// Now, we want to loop over the reply looking for keys
	for (idx = 0; idx < reply->elements; idx += 2) {

		// For the key, we want to see if it's in the list of items that
		//	we care about
		for (item = 0; item < n_items; ++item) {

			// If we've already found the item, just move on
			if (items[item].found) {
				continue;
			}

			// Otherwise, check to see if the key is a match to the item
			if ((reply->element[idx]->len == items[item].key_len) &&
				(!strncmp(reply->element[idx]->str, items[item].key, items[item].key_len)))
			{
				items[item].found = true;
				items[item].reply = reply->element[idx + 1];
				break;
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
// 	@brief	Performs an XREVRANGE of the passed infos and calls the callback
//			associated with the info for any data that comes through. In
//			this manner we get a clean, zero-copy implementation of
//			data passing as we'll call the callbacks while we're
//			running through the response. This function will also
//			set up the XREVRANGE call.
//
////////////////////////////////////////////////////////////////////////////////
bool redis_xrevrange(
	redisContext *ctx,
	const char *name,
	bool (*data_cb)(
		const char *id,
		const struct redisReply *reply,
		void *user_data),
	size_t n,
	void *user_data)
{
	char xrevrange_cmd_buffer[REDIS_CMD_BUFFER_LEN];
	int ret;
	bool ret_val = false;
	struct redisReply *reply, *reply_item;
	int item;

	// Print the beginning of the command into the
	//	command buffer
	ret = snprintf(xrevrange_cmd_buffer, REDIS_CMD_BUFFER_LEN,
		"XREVRANGE %s + - COUNT %lu", name, n);
	if ((ret < 0) || (ret >= REDIS_CMD_BUFFER_LEN)) {
		fprintf(stderr, "snprintf!\n");
		goto done;
	}

	#if DEBUG_COMMANDS
		fprintf(stderr, "Command: %s\n", xrevrange_cmd_buffer);
	#endif

	// Now we should have a properly written XREAD buffer which we
	//	can send to redis and then attemp,t to get the reply
	reply = redisCommand(ctx, xrevrange_cmd_buffer);
	if (reply == NULL) {
		fprintf(stderr, "NULL from redisCommand\n");
		goto done;
	}

	// Otherwise we have a reply. If we timed out then there are no
	//	callbacks to call so we can just note that
	if (reply->type == REDIS_REPLY_NIL) {
		fprintf(stderr, "timed out!\n");
		goto free_reply;
	}

	// Want to make sure the reply is an array
	if (reply->type != REDIS_REPLY_ARRAY) {
		fprintf(stderr, "Reply level 0 not array!\n");
		goto free_reply;
	}
	if (reply->elements != n) {
		fprintf(stderr, "Failed to read %lu elements\n", n);
		goto free_reply;
	}

	// Otherwise, loop over the elements
	for (item = 0; item < n; ++item) {

		// Get the item
		reply_item = reply->element[item];
		if (reply_item->type != REDIS_REPLY_ARRAY) {
			fprintf(stderr, "Reply item %d is not an array!\n", item);
			goto free_reply;
		}

		// Make sure the first value in the item is a status (ID) and the second
		//	is an array
		if ((reply_item->element[0]->type != REDIS_REPLY_STRING) ||
			(reply_item->element[1]->type != REDIS_REPLY_ARRAY))
		{
			fprintf(stderr, "Reply item doesn't have proper data!\n");
			goto free_reply;
		}

		// Finally, if we're here then we're good to pass the
		//	data along to the callback function
		if (!data_cb(
			reply_item->element[0]->str,
			reply_item->element[1],
			user_data))
		{
			fprintf(stderr, "Data cb failed!\n");
			goto free_reply;
		}

	}

	// Note the success
	ret_val = true;

free_reply:
	freeReplyObject(reply);
done:
	return ret_val;
}

////////////////////////////////////////////////////////////////////////////////
//
// 	@brief	Adds the array of (key, value) pairs to the redis stream.
//			Pass maxlen == REDIS_XADD_NO_MAXLEN to not use the maxlen
//			parameter
//
////////////////////////////////////////////////////////////////////////////////
bool redis_xadd(
	redisContext *ctx,
	const char *stream_name,
	struct redis_xadd_info *infos,
	size_t info_len,
	int maxlen,
	bool approx_maxlen,
	char ret_id[STREAM_ID_BUFFLEN])
{
	struct redisReply *reply;
	int argc = 0;
	const char *argv[REDIS_XADD_MAX_ARGS];
	size_t argvlen[REDIS_XADD_MAX_ARGS];
	char maxlen_buffer[REDIS_XADD_MAXLEN_BUFFLEN];
	int maxlen_bytes;
	int i;
	bool ret_val = false;

	// First, want to put the XADD and stream name
	argv[argc] = REDIS_XADD_CMD_STR;
	argvlen[argc++] = CONST_STRLEN(REDIS_XADD_CMD_STR);

	argv[argc] = stream_name;
	argvlen[argc++] = strlen(stream_name);

	// Now, if we have a max length then we want to use that
	if (maxlen != REDIS_XADD_NO_MAXLEN) {
		argv[argc] = REDIS_XADD_MAXLEN_STR;
		argvlen[argc++] = CONST_STRLEN(REDIS_XADD_MAXLEN_STR);

		if (approx_maxlen) {
			argv[argc] = REDIS_XADD_MAXLEN_APPROX_STR;
			argvlen[argc++] = CONST_STRLEN(REDIS_XADD_MAXLEN_APPROX_STR);
		}

		maxlen_bytes = snprintf(maxlen_buffer, REDIS_XADD_MAXLEN_BUFFLEN,
			"%d", maxlen);
		argv[argc] = maxlen_buffer;
		argvlen[argc++] = maxlen_bytes;
	}

	// Add the ID string
	argv[argc] = REDIS_XADD_ID_STR;
	argvlen[argc++] = CONST_STRLEN(REDIS_XADD_ID_STR);

	// Finally we can loop through the (key, value) pairs in the infos
	//	adding them to the argv list
	for (i = 0; i < info_len; ++i) {

		// Put in the key. If the user passed us a key length (as they should
		//	for constant key names) then we will use that, otherwise we'll
		//	do strlen on the key
		argv[argc] = infos[i].key;
		argvlen[argc++] = (infos[i].key_len != 0) ?
			infos[i].key_len : strlen(infos[i].key);

		// Put in the data
		argv[argc] = (const char*)infos[i].data;
		argvlen[argc++] = infos[i].data_len;
	}

	#if DEBUG_COMMANDS
		fprintf(stderr, "Redis Command: ");
		for (i = 0; i < argc; ++i) {
			fprintf(stderr, "%s ", argv[i]);
		}
		fprintf(stderr, "\n");
	#endif

	// Now we're ready to send the redis command
	reply = redisCommandArgv(ctx, argc, argv, argvlen);
	if (reply == NULL){
		fprintf(stderr, "Bad XADD\n");
		for (i = 0; i < argc; i++) {
			fprintf(stderr, "Arg %d: %s: len %lu\n",
				i, argv[i], argvlen[i]);
		}
		goto done;
	}

	// Make sure the reply is a status type with the ID for the value that
	//	we inserted
	if (reply->type != REDIS_REPLY_STRING) {
		fprintf(stderr, "Reply was not string!\n");
		goto free_reply;
	}

	// And copy over the ID into the buffer if the user passed a non-NULL
	//	pointer
	if (ret_id != NULL) {
		strncpy(ret_id, reply->str, STREAM_ID_BUFFLEN);
	}

	// Note the success
	ret_val = true;

free_reply:
	freeReplyObject(reply);
done:
	return ret_val;
}

////////////////////////////////////////////////////////////////////////////////
//
// 	@brief	Calls the callback function for each key that matches the
//			string passed. Redis supports different types of wildcard/pattern
//			in the pattern string, mainly '*' for wildcard matching.
//			See the redis KEYS documentation: https://redis.io/commands/keys
//
////////////////////////////////////////////////////////////////////////////////
int redis_get_matching_keys(
	redisContext *ctx,
	const char *pattern,
	bool (*data_cb)(const char *key, void *user_data),
	void *user_data)
{
	int n_keys = 0;
	int i;
	redisReply *reply = NULL;
	redisReply *matching_keys;
	char iterator[REDIS_SCAN_ITERATOR_BUFFLEN];
	bool first_attempt = true;
	const char *argv[REDIS_SCAN_N_ARGS];
	size_t argvlen[REDIS_SCAN_N_ARGS];

	// Want to initialize the iterator to the starting iterator
	memcpy(iterator, REDIS_SCAN_BEGIN_ITERATOR,
		sizeof(REDIS_SCAN_BEGIN_ITERATOR));

	// Want to set up the arguments for the SCAN call
	argv[0] = REDIS_SCAN_CMD_STR;
	argvlen[0] = CONST_STRLEN(REDIS_SCAN_CMD_STR);

	argv[1] = iterator;
	argvlen[1] = CONST_STRLEN(REDIS_SCAN_BEGIN_ITERATOR);

	argv[2] = REDIS_SCAN_MATCH_STR;
	argvlen[2] = CONST_STRLEN(REDIS_SCAN_MATCH_STR);

	argv[3] = pattern;
	argvlen[3] = strlen(pattern);


	// Want to keep calling SCAN until we're not on the first attempt
	//	and the iterator is not equal to the beginning iterator
	while (first_attempt ||
		(strcmp(iterator, REDIS_SCAN_BEGIN_ITERATOR) != 0))
	{
		// Make the call to SCAN
		reply = redisCommandArgv(ctx, REDIS_SCAN_N_ARGS, argv, argvlen);
		if (reply == NULL) {
			fprintf(stderr, "NULL reply!\n");
			goto done;
		}

		// Check the reply type
		if (reply->type != REDIS_REPLY_ARRAY) {
			fprintf(stderr, "SCAN return is not an array!\n");
			goto done;
		}

		// The first element in the array is the new iterator
		if (reply->element[0]->type != REDIS_REPLY_STRING) {
			fprintf(stderr, "Iterator is not a string!\n");
			goto done;
		}

		// Update the iterator and its length in the argument list
		strncpy(iterator, reply->element[0]->str, sizeof(iterator));
		argvlen[1] = strlen(iterator);

		// The second element in the array is an array of strings for the keys
		matching_keys = reply->element[1];
		if (matching_keys->type != REDIS_REPLY_ARRAY) {
			fprintf(stderr, "Key array is not an array!\n");
			goto done;
		}

		// Now, we want to loop over the keys that we got in the reply
		for (i = 0; i < matching_keys->elements; ++i) {

			// Make sure each key is a string
			if (matching_keys->element[i]->type != REDIS_REPLY_STRING) {
				fprintf(stderr, "Key is not a string!\n");
				goto done;
			}

			// Call the callback on each string
			if (!data_cb(matching_keys->element[i]->str, user_data)) {
				fprintf(stderr, "Failed to call callback!\n");
				goto done;
			}

			++n_keys;
		}

		// Now that we're all done with the reply we can free it. Need to make
		//	sure that we set it to NULL as well s.t. it doesn't get double
		//	freed from the error handling stack
		freeReplyObject(reply);
		reply = NULL;

		// Note that we're no longer on the first attempt
		first_attempt = false;
	}

done:
	if (reply != NULL) {
		freeReplyObject(reply);
	}
	return n_keys;
}

////////////////////////////////////////////////////////////////////////////////
//
// 	@brief	Removes a key from the redis DB, either using UNLINK or del based
//			on the boolean argument passed
//
////////////////////////////////////////////////////////////////////////////////
bool redis_remove_key(
	redisContext *ctx,
	const char *key,
	bool unlink)
{
	redisReply *reply;
	const char *argv[REDIS_REMOVE_KEY_N_ARGS];
	size_t argvlen[REDIS_REMOVE_KEY_N_ARGS];
	bool ret_val = false;

	// Want to set up the arguments for the SCAN call
	if (unlink) {
		argv[0] = REDIS_REMOVE_KEY_UNLINK_STR;
		argvlen[0] = CONST_STRLEN(REDIS_REMOVE_KEY_UNLINK_STR);
	} else {
		argv[0] = REDIS_REMOVE_KEY_DEL_STR;
		argvlen[0] = CONST_STRLEN(REDIS_REMOVE_KEY_DEL_STR);
	}

	argv[1] = key;
	argvlen[1] = strlen(key);

	// Send the unlink/del command
	reply = redisCommandArgv(ctx, REDIS_REMOVE_KEY_N_ARGS, argv, argvlen);
	if (reply == NULL) {
		fprintf(stderr, "Failed to get reply!\n");
		goto done;
	}

	// Make sure the reply is an integer and it's equal to 1, i.e.
	//	the number of keys removed
	if ((reply->type != REDIS_REPLY_INTEGER) || (reply->integer != 1)) {
		fprintf(stderr, "Reply invalid!\n");
		goto free_reply;
	}

	// Note the success
	ret_val = true;

free_reply:
	freeReplyObject(reply);
done:
	return ret_val;
}

////////////////////////////////////////////////////////////////////////////////
//
// 	@brief	Gets a new redis handle to a remote redis server
//
////////////////////////////////////////////////////////////////////////////////
redisContext *redis_context_init_remote(const char *addr, int port)
{
	return redisConnect(addr, port);
}

////////////////////////////////////////////////////////////////////////////////
//
// 	@brief	Gets a new redis handle to a redis server on a unix socket
//
////////////////////////////////////////////////////////////////////////////////
redisContext *redis_context_init_local(const char *socket)
{
	return redisConnectUnix(socket);
}

////////////////////////////////////////////////////////////////////////////////
//
// 	@brief	Gets a new redis handle using all defaults
//
////////////////////////////////////////////////////////////////////////////////
redisContext *redis_context_init(void)
{
	return redis_context_init_local(REDIS_DEFAULT_LOCAL_SOCKET);
}

////////////////////////////////////////////////////////////////////////////////
//
// 	@brief	Frees the redis context
//
////////////////////////////////////////////////////////////////////////////////
void redis_context_cleanup(redisContext * ctx)
{
	redisFree(ctx);
}


////////////////////////////////////////////////////////////////////////////////
//
// 	@brief	Initializes a new stream info. Will set up all of the fields
//			of the info for use with the XREAD function. If time_ctx is
//			non-NULL then will quert redis for the current TIME and set the
//			last_seen_id to the current time. Otherwise will leave the
//			last_seen_id untouched and the user can choose how to implement
//			it.
//
////////////////////////////////////////////////////////////////////////////////
bool redis_init_stream_info(
	redisContext *ctx,
	struct redis_stream_info *info,
	const char *name,
	bool (*data_cb)(
		const char *id,
		const struct redisReply *reply,
		void *user_data),
	const char *last_id,
	void *user_data)
{
	bool ret_val = false;
	struct redisReply *reply;

	// Make sure we either got a context or a last_id
	if ((ctx == NULL) && (last_id == NULL)) {
		fprintf(stderr, "Either conext or last_id needs to be non-NULL!\n");
		goto done;
	}

	// Set the name, data callback and user data
	info->name = name;
	info->data_cb = data_cb;
	info->user_data = user_data;

	// Prefer to use the last ID.
	if (last_id != NULL) {
		strncpy(info->last_id, last_id, sizeof(info->last_id));
	} else {

		// Zero out the last known ID
		memset(info->last_id, 0, sizeof(info->last_id));

		// Get the current time
		reply = redisCommand(ctx, "TIME");

		// If the time is invalid then use '$' for now
		if ((reply == NULL) || (reply->type != REDIS_REPLY_ARRAY) ||
			(reply->elements != 2) ||
			(reply->element[0]->type != REDIS_REPLY_STRING) ||
			(reply->element[1]->type != REDIS_REPLY_STRING))
		{
			fprintf(stderr, "Invalid TIME reply\n");
			info->last_id[0] = '$';

		// Otherwise set the last seen ID to the time
		} else {

			// Cut off the microseconds from the timestamp
			reply->element[1]->str[3] = '\0';

			// Otherwise we want to make the first timestamp
			snprintf(info->last_id, sizeof(info->last_id), "%s%s",
				reply->element[0]->str,
				reply->element[1]->str);
		}

		// If we have a reply then we want to free it
		if (reply != NULL) {
			freeReplyObject(reply);
		}
	}

	// Note the success
	ret_val = true;

done:
	return ret_val;
}

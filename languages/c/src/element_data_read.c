////////////////////////////////////////////////////////////////////////////////
//
//  @file element_data_read.c
//
//  @brief Implements data read functionality for an element
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

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Generic callback for when we get an XREAD on a stream
//			we were listening to. Will process the kv items
//			and then call the user callback with the kv items
//
////////////////////////////////////////////////////////////////////////////////
static bool element_data_read_cb(
	const char *id,
	const struct redisReply *reply,
	void *user_data)
{
	bool ret_val = false;
	struct element_data_read_info *info;

	// Cast the user data to a client listen stream info
	info = (struct element_data_read_info *)user_data;

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
//  @brief Allows the element to listen for data on a set of streams.
//			Each info specifies the stream to listen on as well as the expected
//			keys for each stream. The given data callback will then be called
//			with the redis_xread_kv_items indicating whether each item
//			was found and if so pointing to the base redisReply for the
//			item in the response
//
////////////////////////////////////////////////////////////////////////////////
enum atom_error_t element_data_read_loop(
	redisContext *ctx,
	struct element *elem,
	struct element_data_read_info *infos,
	size_t n_infos,
	bool loop,
	int timeout)
{
	int ret;
	struct redis_stream_info *stream_info = NULL;
	int i;
	char *stream_name;

	// Initialize the return to an internal error
	ret = ATOM_INTERNAL_ERROR;

	// Need to allocate the stream info where we have one info
	//	for each stream we want to listen to
	stream_info = malloc(n_infos * sizeof(struct redis_stream_info));
	assert(stream_info != NULL);
	memset(stream_info, 0, n_infos * sizeof(struct redis_stream_info));

	// Now we want to loop over the stream infos and initialize them
	//	with their respective data
	for (i = 0; i < n_infos; ++i) {

		// Get the full stream name for the data stream
		stream_name = atom_get_data_stream_str(
			infos[i].element, infos[i].stream, NULL);
		assert(stream_name != NULL);

		// And initialize the stream info for the stream
		redis_init_stream_info(
			ctx,
			&stream_info[i],
			stream_name,
			element_data_read_cb,
			NULL,
			&infos[i]);
	}

	// Now that we've initialized the stream info, we want to go ahead and
	//	call the XREAD! Pretty simple.
	while (true) {

		// Do the xread
		if (!redis_xread(ctx, stream_info, n_infos, timeout)) {
			fprintf(stderr, "Redis issue/timeout\n");
			ret = ATOM_REDIS_ERROR;
			goto done;
		}

		// And if we shouldn't be looping then break out
		if (!loop) {
			break;
		}
	}

	// If we got here then it was a success!
	ret = ATOM_NO_ERROR;

done:
	for (i = 0; i < n_infos; ++i) {
		free((char*)stream_info[i].name);
	}
	free(stream_info);
	return ret;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Get the N most recent items on a stream
//
////////////////////////////////////////////////////////////////////////////////
enum atom_error_t element_data_read_n(
	redisContext *ctx,
	struct element *elem,
	struct element_data_read_info *info,
	size_t n)
{
	int ret = ATOM_INTERNAL_ERROR;
	char stream_name[ATOM_NAME_MAXLEN];

	// Get the stream name
	atom_get_data_stream_str(info->element, info->stream, stream_name);

	// Want to initialize the stream info
	if (!redis_xrevrange(ctx, stream_name, element_data_read_cb, n, info)) {
		fprintf(stderr, "Failed to call XREVRANGE\n");
		ret = ATOM_REDIS_ERROR;
		goto done;
	}

	// Note the success
	ret = ATOM_NO_ERROR;

done:
	return ret;
}

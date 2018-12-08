////////////////////////////////////////////////////////////////////////////////
//
//  @file element_entry_read.c
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
static bool element_entry_read_cb(
	const char *id,
	const struct redisReply *reply,
	void *user_data)
{
	bool ret_val = false;
	struct element_entry_read_info *info;

	// Cast the user data
	info = (struct element_entry_read_info *)user_data;

	// Now, we want to parse the reply into the kv items
	if (!redis_xread_parse_kv(reply, info->kv_items, info->n_kv_items)) {
		atom_logf(NULL, NULL, LOG_ERR, "Failed to parse reply!");
		goto done;
	}

	// Send the kv items along to the user response
	if (!info->response_cb(id, info->kv_items, info->n_kv_items, info->user_data)) {
		atom_logf(NULL, NULL, LOG_ERR,
			"Failed to call user response callback with kv items");
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
enum atom_error_t element_entry_read_loop(
	redisContext *ctx,
	struct element *elem,
	struct element_entry_read_info *infos,
	size_t n_infos,
	bool loop_forever,
	int timeout)
{
	int ret;
	struct redis_stream_info *stream_info = NULL;
	int i;
	char *stream_name;
	bool done;

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
			element_entry_read_cb,
			NULL,
			&infos[i]);

		// Note that we haven't read any items yet
		infos[i].items_read = 0;
		infos[i].xreads = 0;
	}

	// If we want to loop forever
	if (loop_forever) {

		// Loop forever, XREADing
		while (true) {
			if (!redis_xread(
				ctx,
				stream_info,
				n_infos,
				timeout,
				REDIS_XREAD_NOMAXCOUNT))
			{
				atom_logf(ctx, elem, LOG_ERR, "Redis issue/timeout");
				ret = ATOM_REDIS_ERROR;
				goto done;
			}
		}

	// Otherwise we loop until we've read the min items
	//	on each stream
	} else {

		while (true) {
			// Do the XREAD
			if (!redis_xread(
				ctx,
				stream_info,
				n_infos,
				timeout,
				REDIS_XREAD_NOMAXCOUNT))
			{
				atom_logf(ctx, elem, LOG_ERR, "Redis issue/timeout");
				ret = ATOM_REDIS_ERROR;
				goto done;
			}

			// For each stream, note the number of items that
			//	we read
			done = true;
			for (i = 0; i < n_infos; ++i) {
				infos[i].items_read += stream_info[i].items_read;
				if (infos[i].items_read < infos[i].items_to_read) {
					done = false;
				}

				infos[i].xreads += 1;
			}

			// If we're done, then break
			if (done) {
				break;
			}
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
enum atom_error_t element_entry_read_n(
	redisContext *ctx,
	struct element *elem,
	struct element_entry_read_info *info,
	size_t n)
{
	int ret = ATOM_INTERNAL_ERROR;
	char stream_name[ATOM_NAME_MAXLEN];

	// Get the stream name
	atom_get_data_stream_str(info->element, info->stream, stream_name);

	// Want to initialize the stream info
	if (!redis_xrevrange(ctx, stream_name, element_entry_read_cb, n, info)) {
		atom_logf(ctx, elem, LOG_ERR, "Failed to call XREVRANGE");
		ret = ATOM_REDIS_ERROR;
		goto done;
	}

	// Note the success
	ret = ATOM_NO_ERROR;

done:
	return ret;
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
enum atom_error_t element_entry_read_since(
	redisContext *ctx,
	struct element *elem,
	struct element_entry_read_info *info,
	const char *last_id,
	int timeout,
	size_t maxcount)
{
	int ret;
	struct redis_stream_info stream_info;
	char stream_name[ATOM_NAME_MAXLEN];

	// Initialize the return to an internal error
	ret = ATOM_INTERNAL_ERROR;

	// Get the full stream name for the data stream
	atom_get_data_stream_str(info->element, info->stream, stream_name);

	// And initialize the stream info for the stream
	redis_init_stream_info(
		ctx,
		&stream_info,
		stream_name,
		element_entry_read_cb,
		(last_id != NULL) ? last_id : "$",
		info);

	// Do the XREAD
	if (!redis_xread(ctx, &stream_info, 1, timeout, maxcount)) {
		atom_logf(ctx, elem, LOG_ERR, "Redis issue/timeout");
		ret = ATOM_REDIS_ERROR;
		goto done;
	}

	// Note the success
	ret = ATOM_NO_ERROR;

done:
	return ret;
}

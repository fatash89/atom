////////////////////////////////////////////////////////////////////////////////
//
//  @file element_entry_write.c
//
//  @brief Implements data write functionality for an element
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
//  @brief Initializes a data write info. Will allocate the memory for the
//			info and get the name of the stream
//
////////////////////////////////////////////////////////////////////////////////
struct element_entry_write_info *element_entry_write_init(
	redisContext *ctx,
	struct element *elem,
	const char *name,
	int n_items)
{
	struct element_entry_write_info *info = NULL;

	// Allocate the memory for the stream
	info = malloc(sizeof(struct element_entry_write_info));
	assert(info != NULL);

	// Allocate the memory for the infos for the droplets
	info->items = malloc(
		sizeof(struct redis_xadd_info) *
			(n_items + DATA_N_ADDITIONAL_KEYS));
	assert(info->items != NULL);

	// Set up the stream name
	atom_get_data_stream_str(elem->name.str, name, info->stream);

	// Note the number of droplet items
	info->n_items = n_items;

	// Return the info
	return info;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Cleans up a data write info
//
////////////////////////////////////////////////////////////////////////////////
void element_entry_write_cleanup(
	redisContext *ctx,
	struct element_entry_write_info *info)
{
	if (info != NULL) {

		// Free the items
		if (info->items != NULL) {
			free(info->items);
		}

		// Remove the stream key
		redis_remove_key(ctx, info->stream, true);

		// Free the info itself
		free(info);
	}
}


////////////////////////////////////////////////////////////////////////////////
//
//  @brief Writes a piece of data to the system. Must write on a stream
//			info that's been initialized.
//
////////////////////////////////////////////////////////////////////////////////
enum atom_error_t element_entry_write(
	redisContext *ctx,
	struct element_entry_write_info *info,
	int timestamp,
	int maxlen)
{
	enum atom_error_t ret = ATOM_INTERNAL_ERROR;
	size_t n_items;
	char timestamp_buffer[64];
	size_t timestamp_buffer_len;

	// Initialize the number of infos to that of the stream itself
	n_items = info->n_items;

	// If the timestamp is not the default then we want to add it to
	//	the infos and note the new number of infos
	if (timestamp != ELEMENT_DATA_WRITE_DEFAULT_TIMESTAMP) {

		// Make the string
		timestamp_buffer_len = snprintf(
			timestamp_buffer, sizeof(timestamp_buffer), "%d", timestamp);

		// Add it to the droplet items
		// Initialize the timestamp key and key len
		info->items[n_items].key =
			DATA_KEY_TIMESTAMP_STR;
		info->items[n_items].key_len =
			CONST_STRLEN(DATA_KEY_TIMESTAMP_STR);
		info->items[n_items].data =
			(uint8_t*)timestamp_buffer;
		info->items[n_items].data_len =
			timestamp_buffer_len;

		// Note the new number of items
		++n_items;
	}

	// And we want to XADD the data to the stream to create it. This will
	//	also put the ID of the item in the stream that we added with our
	//	info into our last id
	if (!redis_xadd(
		ctx,
		info->stream,
		info->items,
		n_items,
		maxlen,
		ATOM_DEFAULT_APPROX_MAXLEN,
		NULL))
	{
		atom_logf(ctx, NULL, LOG_ERR, "Failed to XADD data to stream");
		ret = ATOM_REDIS_ERROR;
		goto done;
	}

	// Note the success
	ret = ATOM_NO_ERROR;

done:
	return ret;
}

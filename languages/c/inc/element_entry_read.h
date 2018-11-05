////////////////////////////////////////////////////////////////////////////////
//
//  @file element_entry_read.h
//
//  @brief Header for the element read data implementation
//
//  @copy 2018 Elementary Robotics. All rights reserved.
//
////////////////////////////////////////////////////////////////////////////////

#ifndef __ATOM_ELEMENT_DATA_READ_H
#define __ATOM_ELEMENT_DATA_READ_H

#ifdef __cplusplus
 extern "C" {
#endif

#include "atom.h"
#include "redis.h"

// Forward declaration of the element struct
struct element;

// Struct that defines all information for processing a data stream:
//	This struct is used both for the data loop and for getting the N
//	most recent pieces of data.
struct element_entry_read_info {
	const char *element;
	const char *stream;
	struct redis_xread_kv_item *kv_items;
	size_t n_kv_items;
	void *user_data;
	bool (*response_cb)(
		const struct redis_xread_kv_item *kv_items,
		int n_kv_items,
		void *user_data);
};

// Allows an element to listen for all data on streams
enum atom_error_t element_entry_read_loop(
	redisContext *ctx,
	struct element *elem,
	struct element_entry_read_info *infos,
	size_t n_infos,
	bool loop,
	int timeout);

// Allows an element to get the N most recent items on a stream
enum atom_error_t element_entry_read_n(
	redisContext *ctx,
	struct element *elem,
	struct element_entry_read_info *info,
	size_t n);

#ifdef __cplusplus
 }
#endif

#endif // __ATOM_ELEMENT_DATA_READ_H

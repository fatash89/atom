////////////////////////////////////////////////////////////////////////////////
//
//  @file element_entry_write.h
//
//  @brief Header for the element data write implementation
//
//  @copy 2018 Elementary Robotics. All rights reserved.
//
////////////////////////////////////////////////////////////////////////////////

#ifndef __ATOM_ELEMENT_DATA_WRITE_H
#define __ATOM_ELEMENT_DATA_WRITE_H

#ifdef __cplusplus
 extern "C" {
#endif

#include "atom.h"
#include "redis.h"

// Defaults for the data stream.
#define ELEMENT_DATA_WRITE_DEFAULT_TIMESTAMP 0
#define ELEMENT_DATA_WRITE_DEFAULT_MAXLEN 1024

// Forward declaration of the element struct
struct element;

// Element data stream struct. Will allocate the memory for the XADD infos
//	and initialize the stream for the droplets. Infos will be
//	allocated to hold some more info than the user requests
//	s.t. we can throw a timestamp and/or other things on there
struct element_entry_write_info {
	struct redis_xadd_info *items;
	size_t n_items;
	char stream[STREAM_ID_BUFFLEN];
};

// Initializes a stream. Once this is done
//	once, at startup, it will be quite lightweight
//	to update and publish the droplet.
struct element_entry_write_info *element_entry_write_init(
	redisContext *ctx,
	struct element *elem,
	const char *name,
	int n_keys);

// Cleans up a stream
void element_entry_write_cleanup(
	redisContext *ctx,
	struct element_entry_write_info *stream);

// Adds data to an element stream. The stream struct contains
//	an aray of XADD infos where the user will be responsible for filling
//	out the value for each piece of data.
enum atom_error_t element_entry_write(
	redisContext *ctx,
	struct element_entry_write_info *stream,
	int timestamp,
	int maxlen);

#ifdef __cplusplus
 }
#endif

#endif // __ATOM_ELEMENT_DATA_WRITE_H

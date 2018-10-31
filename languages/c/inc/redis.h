////////////////////////////////////////////////////////////////////////////////
//
//  @file redis.h
//
//  @brief Header for the redis interface
//
//  @copy 2018 Elementary Robotics. All rights reserved.
//
////////////////////////////////////////////////////////////////////////////////

#ifndef __SKILLS_REDIS_H
#define __SKILLS_REDIS_H

#ifdef __cplusplus
 extern "C" {
#endif

#include <hiredis/hiredis.h>
#include <stdbool.h>

// Default address and port of the local redis server
#define REDIS_DEFAULT_LOCAL_SOCKET "/shared/redis.sock"

// Default address and port of the remote redis server
#define REDIS_DEFAULT_REMOTE_ADDR "127.0.0.1"
#define REDIS_DEFAULT_REMOTE_PORT 6379

// Maximum length for a stream ID buffer. This should be roughly the number of
//	digits in a milliseond unix timestamp + a dash + 4 trailing values
//	to cover more or less any value that the IDs could be
#define STREAM_ID_BUFFLEN 32

// Constant string length. Useful for keys/values
#define CONST_STRLEN(x) (sizeof(x) - 1)

// Struct that contains all of the information about an XREAD stream
//	being monitored. The user is expected to fill out the stream name
//	and data_cb. data_cb should be a function that takes a redisReply
//	where the reply is an array type of key, value pairs that have
//	been received at a particular id. The stream info will also
//	be updated to keep track of the last ID seen on the stream s.t. subsequent
//	calls to the stream will block properly and get all of the data
struct redis_stream_info {
	const char *name;
	bool (*data_cb)(
		const char *id,
		const struct redisReply *reply,
		void *user_data);
	char last_id[STREAM_ID_BUFFLEN];
	void *user_data;
};

// Struct that contains info for data to be written. Each piece of data
//	written should be a (key, value) pair
struct redis_xadd_info {
	const char *key;
	size_t key_len;
	const uint8_t *data;
	size_t data_len;
};

// Struct for easier parsing of redis replies. We'll fill this out
//	with the fields we're interested in. The reply parser will then iterate
//	through the reply and fill out if the field is present, and if it
//	is present will fill out the redisReply pointer for its data
struct redis_xread_kv_item {
	const char *key;
	size_t key_len;
	bool found;
	redisReply *reply;
};

// Initializes a stream info s.t. it's ready for pub-sub like blocking
//	for xread. CTX may be NULL if last_id is provided. If last_id is NULL
//	then ctx will be used to get the current time and use that as the
//	last seen ID.
bool redis_init_stream_info(
	redisContext *ctx,
	struct redis_stream_info *info,
	const char *name,
	bool (*data_cb)(
		const char *id,
		const struct redisReply *reply,
		void *user_data),
	const char *last_id,
	void *user_data);

// Performs an XREAD of the streams in the infos structs, calling the callback
//	for each piece of data received. Will block for at most block milliseconds
//	while waiting for data, with 0 being blocking indefinitely
#define REDIS_XREAD_BLOCK_INDEFINITE 0
bool redis_xread(
	redisContext *ctx,
	struct redis_stream_info *infos,
	int n_infos,
	int block);

// Analyzes the key, value array returned in XREAD
bool redis_xread_parse_kv(
	const redisReply *reply,
	struct redis_xread_kv_item *items,
	size_t n_items);

// Performs an xrevrange call to redis in order to get the N most recent
//	elements on the stream. Similar to XREAD will loop over the streams
//	and call the callback passed. Takes a redis_stream_info like XREAD
//	but the last_seen_id field is ignored.
bool redis_xrevrange(
	redisContext *ctx,
	const char *stream_name,
	bool (*data_cb)(const char *id, const struct redisReply *reply, void *data),
	size_t n,
	void *user_data);

// Adds data to ,a stream with a given max length.
#define REDIS_XADD_NO_MAXLEN (-1)
bool redis_xadd(
	redisContext *ctx,
	const char *stream_name,
	struct redis_xadd_info *infos,
	size_t info_len,
	int maxlen,
	bool approx_maxlen,
	char ret_id[STREAM_ID_BUFFLEN]);

// Calls the callback with each key that matches the
//	pattern. NOTE: the scanning API currently can be prone
//	to duplicates. Returns the number of times the callback
//	function was called, i.e. how many keys (counting duplicates)
//	were found to match the pattern. user_data is also passed
//	to the callback
int redis_get_matching_keys(
	redisContext *ctx,
	const char *pattern,
	bool (*data_cb)(const char *key, void *user_data),
	void *user_data);

// Removes a key. Will either use UNLINK (preferred) or del based
//	on the boolean argument passed
bool redis_remove_key(
	redisContext *ctx,
	const char *key,
	bool unlink);

// Prints out a redis reply recursively. To print out a top-level
//	reply, call with (0, 0, reply).
void redis_print_reply(
	int depth,
	int elem,
	const redisReply *reply);

// Prints out kv items
void redis_print_xread_kv_items(
	const struct redis_xread_kv_item *items,
	size_t n_items);

// Gets a redis context
redisContext *redis_context_init(void);

// Frees a redis context
void redis_context_cleanup(redisContext *ctx);

#ifdef __cplusplus
 }
#endif

#endif // __SKILLS_REDIS_H

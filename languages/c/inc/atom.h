////////////////////////////////////////////////////////////////////////////////
//
//  @file atom.h
//
//  @brief General-purpose header for the atom library
//
//  @copy 2018 Elementary Robotics. All rights reserved.
//
////////////////////////////////////////////////////////////////////////////////

#ifndef __ATOM_ATOM_H
#define __ATOM_ATOM_H

#ifdef __cplusplus
 extern "C" {
#endif

#include <stdbool.h>
#include <hiredis/hiredis.h>
#include <syslog.h>

// This will determine whether we'll print logs
//	to stdout/stderr or just log them to the atom system.
//	this should be turned off in releases eventually
#define ATOM_PRINT_LOGS

struct element;

//
// Error codes. Need to provide the final
//	user error s.t. the compiler can put it
//	into a signed 32-bit integer.
//
enum atom_error_t {
	ATOM_NO_ERROR,
	ATOM_INTERNAL_ERROR,
	ATOM_REDIS_ERROR,
	ATOM_COMMAND_NO_ACK,
	ATOM_COMMAND_NO_RESPONSE,
	ATOM_COMMAND_INVALID_DATA,
	ATOM_COMMAND_UNSUPPORTED,
	ATOM_CALLBACK_FAILED,
	ATOM_LANGUAGE_ERRORS_BEGIN = 100,
	ATOM_USER_ERRORS_BEGIN = 1000,
};

#define ATOM_RESPONSE_STREAM_PREFIX "response:"
#define ATOM_COMMAND_STREAM_PREFIX "command:"
#define ATOM_DATA_STREAM_PREFIX "stream:"

#define ATOM_LOG_STREAM_NAME "log"

#define ATOM_VERSION_KEY "version"
#define ATOM_LANGUAGE_KEY "language"

#define ATOM_VERSION "v0.1.0"
#define ATOM_LANGUAGE "c"

#define ATOM_DEFAULT_MAXLEN 1024
#define ATOM_DEFAULT_APPROX_MAXLEN true

// Maximum length of a stream name
#define ATOM_NAME_MAXLEN 128

// Max length of a log string
#define ATOM_LOG_MAXLEN 1024

//
// Keys for sending a command to an element
//

#define COMMAND_KEY_ELEMENT_STR "element"
#define COMMAND_KEY_COMMAND_STR "cmd"
#define COMMAND_KEY_DATA_STR "data"

enum cmd_keys_t {
	CMD_KEY_ELEMENT,
	CMD_KEY_CMD,
	CMD_KEY_DATA,
	CMD_N_KEYS,
};

//
// Keys shared in each response from the element
//

#define STREAM_KEY_ELEMENT_STR "element"
#define STREAM_KEY_ID_STR "cmd_id"

enum stream_keys_t {
	STREAM_KEY_ELEMENT,
	STREAM_KEY_ID,
	STREAM_N_KEYS,
};


//
// Additional keys in the ACK response
//

#define ACK_KEY_TIMEOUT_STR "timeout"

enum ack_keys_t {
	ACK_KEY_TIMEOUT = STREAM_N_KEYS,
	ACK_N_KEYS,
};

//
// Additional keys in the command response
//

#define RESPONSE_KEY_CMD_STR "cmd"
#define RESPONSE_KEY_ERR_CODE_STR "err_code"
#define RESPONSE_KEY_ERR_STR_STR "err_str"
#define RESPONSE_KEY_DATA_STR "data"

enum command_keys_t {
	RESPONSE_KEY_CMD = STREAM_N_KEYS,
	RESPONSE_KEY_ERR_CODE,
	RESPONSE_KEY_ERR_STR,
	RESPONSE_KEY_DATA,
	RESPONSE_N_KEYS,
};

// Log keys
#define LOG_KEY_LEVEL_STR "level"
#define LOG_KEY_ELEMENT_STR "element"
#define LOG_KEY_MESSAGE_STR "msg"
#define LOG_KEY_HOST_STR "host"

enum atom_log_keys_t {
	LOG_KEY_LEVEL,
	LOG_KEY_ELEMENT,
	LOG_KEY_MESSAGE,
	LOG_KEY_HOST,
	LOG_N_KEYS
};

//
// Additional (optional) keys in the droplets
//
#define DATA_KEY_TIMESTAMP_STR "timestamp"

enum data_keys_t {
	DATA_KEY_TIMESTAMP,
	DATA_N_ADDITIONAL_KEYS
};

// Result list for calls to get elements/streams
struct atom_list_node {
	char *name;
	struct atom_list_node *next;
};

// Calls the associated data_cb for each element that's present in the system.
//	NOTE: duplicates may occur
enum atom_error_t atom_get_all_elements_cb(
	redisContext *ctx,
	bool (*data_cb)(const char *element, void* user_data),
	void *user_data);

// Calls the associated data_cb for all streams in the system. If element is
//	NULL then will return all streams in the ststem, else just streams
//	belonging to the passed element.
//	NOTE: duplicates may occur
enum atom_error_t atom_get_all_data_streams_cb(
	redisContext *ctx,
	const char *element,
	bool (*data_cb)(const char *stream, void* user_data),
	void *user_data);

// Returns a sorted list of all elements in the system without
//	duplicates. NOTE: the list must be freed
//	using atom_list_free()
enum atom_error_t atom_get_all_elements(
	redisContext *ctx,
	struct atom_list_node **result);

// Returns a sorted list of all data streams in the system
//	without duplicates. NOTE: the list must be freed
//	using atom_list_free()
enum atom_error_t atom_get_all_data_streams(
	redisContext *ctx,
	const char *element,
	struct atom_list_node **result);

// Frees a list of results from a query to the system
void atom_list_free(struct atom_list_node *list);

// Helper for getting the command response stream. If buffer
//	is non-NULL will write the name into the buffer,
//	else will allocate a string and return it.
char *atom_get_response_stream_str(
	const char *element,
	char buffer[ATOM_NAME_MAXLEN]);

// Helper for getting the command request stream. If buffer
//	is non-NULL will write the name into the buffer,
//	else will allocate a string and return it.
char *atom_get_command_stream_str(
	const char *element,
	char buffer[ATOM_NAME_MAXLEN]);

// Helper for getting the element data stream prefix. If buffer
//	is non-NULL will write the name into the buffer,
//	else will allocate a string and return it.
char *atom_get_data_stream_prefix_str(
	const char *element,
	char buffer[ATOM_NAME_MAXLEN]);

// Helper for getting a data stream. If buffer
//	is non-NULL will write the name into the buffer,
//	else will allocate a string and return it.
char *atom_get_data_stream_str(
	const char *element,
	const char *name,
	char buffer[ATOM_NAME_MAXLEN]);

// Logs a message to the standard log stream
enum atom_error_t atom_log(
	redisContext *ctx,
	struct element *element,
	int level,
	const char *msg,
	size_t msg_len);

// Logs a message to the standard log stream using variadic
//	args
enum atom_error_t atom_vlogf(
	redisContext *ctx,
	struct element *element,
	int level,
	const char *fmt,
	va_list args);

// Logs a message to the standard log stream using printf
//	style args
enum atom_error_t atom_logf(
	redisContext *ctx,
	struct element *element,
	int level,
	const char *fmt,
	...);

#ifdef __cplusplus
 }
#endif

#endif // __ATOM_ATOM_H

////////////////////////////////////////////////////////////////////////////////
//
//  @file skills.h
//
//  @brief Header for the general purpose skills interface
//
//  @copy 2018 Elementary Robotics. All rights reserved.
//
////////////////////////////////////////////////////////////////////////////////

#ifndef __SKILLS_SKILLS_H
#define __SKILLS_SKILLS_H

#ifdef __cplusplus
 extern "C" {
#endif

#include <stdbool.h>

//
// Error codes. Need to provide the final
//	user error s.t. the compiler can put it
//	into a signed 32-bit integer.
//
enum skills_error_t {
	SKILLS_NO_ERROR,
	SKILLS_INTERNAL_ERROR,
	SKILLS_REDIS_ERROR,
	SKILLS_COMMAND_NO_ACK,
	SKILLS_COMMAND_NO_RESPONSE,
	SKILLS_COMMAND_INVALID_DATA,
	SKILLS_COMMAND_UNSUPPORTED,
	SKILLS_CALLBACK_FAILED,
	SKILLS_LANGUAGE_ERRORS_BEGIN = 100,
	SKILLS_USER_ERRORS_BEGIN = 1000,
};

#define SKILLS_CLIENT_RESPONSE_STREAM_PREFIX "client:"
#define SKILLS_SKILL_COMMAND_STREAM_PREFIX "skill:"
#define SKILLS_SKILL_DATA_STREAM_PREFIX "stream:"

#define SKILLS_VERSION_KEY "version"
#define SKILLS_LANGUAGE_KEY "language"

#define SKILLS_VERSION "v0.1.0"
#define SKILLS_LANGUAGE "c"

#define STREAM_DEFAULT_MAXLEN 1024
#define STREAM_DEFAULT_APPROX_MAXLEN true

// Maximum length of a stream name
#define STREAM_NAME_MAXLEN 128

//
// Keys for sending a command to a skill
//

#define COMMAND_KEY_CLIENT_STR "client"
#define COMMAND_KEY_COMMAND_STR "cmd"
#define COMMAND_KEY_DATA_STR "data"

enum cmd_keys_t {
	CMD_KEY_CLIENT,
	CMD_KEY_CMD,
	CMD_KEY_DATA,
	CMD_N_KEYS,
};

//
// Keys shared in each response from the skill
//

#define STREAM_KEY_SKILL_STR "skill"
#define STREAM_KEY_ID_STR "cmd_id"

enum stream_keys_t {
	STREAM_KEY_SKILL,
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


//
// Additional (optional) keys in the droplets
//
#define DROPLET_KEY_TIMESTAMP_STR "timestamp"

enum droplet_keys_t {
	DROPLET_KEY_TIMESTAMP,
	DROPLET_N_ADDITIONAL_KEYS
};

// Calls the associated data_cb for each skill that's present in the system.
//	NOTE: duplicates may occur
bool skills_get_all_skills(
	redisContext *ctx,
	bool (*data_cb)(const char *skill));

// Calls the associated data_cb for all streams in the system. If skill is
//	NULL then will return all streams in the systems, else just streams
//	belonging to the passed skill.
//	NOTE: duplicates may occur
bool skills_get_all_streams(
	redisContext *ctx,
	bool (*data_cb)(const char *stream),
	const char *skill);

// Calls the associated data_cb for all clients in the system.
//	NOTE: duplicates may occur
bool skills_get_all_clients(
	redisContext *ctx,
	bool (*data_cb)(const char *skill));

// Helper for getting the client response stream. If buffer
//	is non-NULL will write the name into the buffer,
//	else will allocate a string and return it.
char *skills_get_client_response_stream(
	const char *client,
	char buffer[STREAM_NAME_MAXLEN]);

// Helper for getting the skill command stream. If buffer
//	is non-NULL will write the name into the buffer,
//	else will allocate a string and return it.
char *skills_get_skill_command_stream(
	const char *skill,
	char buffer[STREAM_NAME_MAXLEN]);

// Helper for getting the skill droplet prefix. If buffer
//	is non-NULL will write the name into the buffer,
//	else will allocate a string and return it.
char *skills_get_skill_droplet_prefix(
	const char *skill,
	char buffer[STREAM_NAME_MAXLEN]);

// Helper for getting a droplet stream. If buffer
//	is non-NULL will write the name into the buffer,
//	else will allocate a string and return it.
char *skills_get_droplet_stream(
	const char *skill,
	const char *droplet,
	char buffer[STREAM_NAME_MAXLEN]);


#ifdef __cplusplus
 }
#endif

#endif // __SKILLS_SKILLS_H

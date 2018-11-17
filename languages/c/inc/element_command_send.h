////////////////////////////////////////////////////////////////////////////////
//
//  @file element_command_send.h
//
//  @brief Header for the implementation of elements sending commands.
//
//  @copy 2018 Elementary Robotics. All rights reserved.
//
////////////////////////////////////////////////////////////////////////////////

#ifndef __ATOM_ELEMENT_COMMAND_SEND_H
#define __ATOM_ELEMENT_COMMAND_SEND_H

#ifdef __cplusplus
 extern "C" {
#endif

#include "atom.h"
#include "redis.h"

// Forward declaration of the element struct
struct element;

// Sends a command with the given data to the given stream. If
//	block is true, will wait until the response is completed. If response_cb
//	is also non-null then will call response_cb with the data in the response
//	s.t. the user can handle it.
enum atom_error_t element_command_send(
	redisContext *ctx,
	struct element *elem,
	const char *cmd_elem,
	const char *cmd,
	uint8_t *data,
	size_t data_len,
	bool block,
	bool (*response_cb)(
		const uint8_t *response,
		size_t response_len,
		void *user_data),
	void *user_data);

#ifdef __cplusplus
 }
#endif

#endif // __ATOM_ELEMENT_COMMAND_SEND_H

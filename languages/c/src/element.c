////////////////////////////////////////////////////////////////////////////////
//
//  @file element.c
//
//  @brief Implements basic element init and cleanup functions
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
//  @brief Initializes an element. MUST be cleaned up by passing the
//			struct returned to element_cleanup when done. Note that the context
//			isn't associated with the element. All functionaity is indifferent
//			to which redis context is being used.
//
////////////////////////////////////////////////////////////////////////////////
struct element *element_init(
	redisContext *ctx,
	const char *name)
{
	struct element *elem = NULL;
	struct redis_xadd_info element_info[2];

	// Make the new element
	elem = malloc(sizeof(struct element));
	assert(elem != NULL);

	// Put in the name of the element
	elem->name.str = strdup(name);
	assert(elem->name.str != NULL);
	elem->name.len = strlen(elem->name.str);

	// Set up the response stream
	elem->response.stream = atom_get_response_stream_str(name, NULL);
	assert(elem->response.stream != NULL);
	memset(elem->response.last_id, 0, sizeof(elem->response.last_id));

	// Set up the command stream
	elem->command.stream = atom_get_command_stream_str(name, NULL);
	assert(elem->command.stream != NULL);
	memset(elem->command.last_id, 0, sizeof(elem->command.last_id));

	// Clear out the hashtable for the element. This initializes
	//	all of the bins to empty
	memset(elem->command.hash, 0, sizeof(elem->command.hash));

	// Finally, make the redis context for the element to send responses
	//	to commands on. This is done since the context for receiving the command
	//	is in use
	elem->command.ctx = redis_context_init();
	if (elem->command.ctx == NULL) {
		fprintf(stderr, "Failed to create command response context!\n");
		goto err_cleanup;
	}

	// We want to initialize the element information and call an XADD
	//	to both the command stream and the response stream
	element_info[0].key = ATOM_LANGUAGE_KEY;
	element_info[0].key_len = CONST_STRLEN(ATOM_LANGUAGE_KEY);
	element_info[0].data = (uint8_t*)ATOM_LANGUAGE;
	element_info[0].data_len = CONST_STRLEN(ATOM_LANGUAGE);
	element_info[1].key = ATOM_VERSION_KEY;
	element_info[1].key_len = CONST_STRLEN(ATOM_VERSION_KEY);
	element_info[1].data = (uint8_t*)ATOM_VERSION;
	element_info[1].data_len = CONST_STRLEN(ATOM_VERSION);

	// And we want to XADD the data to the stream to create it. This will
	//	also put the ID of the item in the stream that we added with our
	//	info into our last id
	if (!redis_xadd(
		ctx, elem->response.stream, element_info, 2,
		ATOM_DEFAULT_MAXLEN, ATOM_DEFAULT_APPROX_MAXLEN,
		elem->response.last_id))
	{
		fprintf(stderr,
			"Failed to add initial element info to response stream\n");
		goto err_cleanup;
	}

	// And we want to XADD the data to the stream to create it. This will
	//	also put the ID of the item in the stream that we added with our
	//	info into our last id
	if (!redis_xadd(
		ctx, elem->command.stream, element_info, 2,
		ATOM_DEFAULT_MAXLEN, ATOM_DEFAULT_APPROX_MAXLEN,
		elem->command.last_id))
	{
		fprintf(stderr,
			"Failed to add initial element info to command stream\n");
		goto err_cleanup;
	}

	// If we got here, then we're good. Skip the error cleanup
	goto done;

err_cleanup:
	element_cleanup(ctx, elem);
	elem = NULL;
done:
	return elem;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Frees a command struct
//
////////////////////////////////////////////////////////////////////////////////
static void element_free_command(
	struct element_command *cmd)
{
	if (cmd != NULL) {
		if (cmd->name != NULL) {
			free(cmd->name);
		}
		free(cmd);
	}
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Frees a hashtable associated with a element
//
////////////////////////////////////////////////////////////////////////////////
static void element_free_command_hash(
	struct element_command *command_hash[ELEMENT_COMMAND_HASH_N_BINS])
{
	int i;
	struct element_command *iter, *to_delete;

	// Loop over the bins and free the entire linked list in the bin
	for (i = 0; i < ELEMENT_COMMAND_HASH_N_BINS; ++i) {
		iter = command_hash[i];
		while (iter != NULL) {
			to_delete = iter;
			iter = iter->next;
			element_free_command(to_delete);
		}
	}
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Cleans up a redis element. Will deallocate all memory associated
//			with it and do any other necessary cleanup.
//
////////////////////////////////////////////////////////////////////////////////
void element_cleanup(
	redisContext *ctx,
	struct element *elem)
{
	if (elem != NULL) {

		// Clean up the name
		if (elem->name.str != NULL) {
			free(elem->name.str);
		}

		// Clean up the response stream
		if (elem->response.stream != NULL) {
			redis_remove_key(ctx, elem->response.stream, true);
			free(elem->response.stream);
		}

		// Clean up the command stream
		if (elem->command.stream != NULL) {
			redis_remove_key(ctx, elem->command.stream, true);
			free(elem->command.stream);
		}

		// Clean up the response context
		if (elem->command.ctx != NULL) {
			redis_context_cleanup(elem->command.ctx);
		}

		// Clean up the hashtable
		element_free_command_hash(elem->command.hash);

		// And free the element itself
		free(elem);
	}
}

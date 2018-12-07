////////////////////////////////////////////////////////////////////////////////
//
//  @file element.h
//
//  @brief Header for the element implementation
//
//  @copy 2018 Elementary Robotics. All rights reserved.
//
////////////////////////////////////////////////////////////////////////////////
#ifndef __ATOM_CPP_ELEMENT_H
#define __ATOM_CPP_ELEMENT_H

#include <queue>
#include <mutex>
#include <syslog.h>

#include "atom/atom.h"
#include "atom/redis.h"
#include "atom/element_entry_write.h"
#include "element_response.h"
#include "element_read_map.h"

#define ELEMENT_DEFAULT_N_CONTEXTS 20

#define ELEMENT_INFINITE_COMMAND_LOOPS 0

// Entry value
typedef std::map<std::string, std::string> entry_t;

// Command Handler function
typedef bool (*element_command_handler_t)(
	const uint8_t *data,
	size_t data_len,
	ElementResponse *resp,
	void *user_data);

// Element class itself
class Element {

	// Name
	std::string name;

	// C element
	struct element *elem;

	// Redis context pool
	std::queue<redisContext *>context_pool;
	mutable std::mutex context_mutex;

	// Commands that the element supports
	std::map<std::string, std::pair<element_command_handler_t, void*>> commands;

	// Streams that we're currently publishing on
	std::map<std::string, struct element_entry_write_info *> streams;

	// Functions for getting redis contexts
	void initContextPool(
		int n_contexts);
	void cleanupContextPool();
	redisContext *getContext();
	void releaseContext(
		redisContext *ctx);

	// Function for converting a readMap into element_entry_read_info
	struct element_entry_read_info *readMapToEntryInfo(
		ElementReadMap &m);
	// Function for freeing entry info
	void freeEntryInfo(
		struct element_entry_read_info *info,
		size_t n_infos);

public:

	// Constructors
	Element(
		std::string n,
		int n_contexts = ELEMENT_DEFAULT_N_CONTEXTS);

	// Destructor
	~Element();

	// Returns the name of the element
	const std::string &getName();

	// Returns a list of all elements
	enum atom_error_t getAllElements(
		std::vector<std::string> &elem_list);

	// Returns either all streams or all streams associated with
	//	a given element
	enum atom_error_t getAllStreams(
		std::map<std::string, std::vector<std::string>> &stream_map);
	enum atom_error_t getAllStreams(
		std::vector<std::string> &stream_list,
		std::string element);

	// Adds support for a command. Takes a command name,
	//	handler function and timeout to be returned to callers of this
	//	command
	void addCommand(
		std::string name,
		element_command_handler_t fn,
		void *user_data,
		int timeout);

	// Processes incoming commands per the command
	//	handler table. If no args passed, then will loop indefinitely,
	//	else will handle only N commands and then will exit
	enum atom_error_t commandLoop(
		int n_loops = ELEMENT_INFINITE_COMMAND_LOOPS);

	// Sends a command to a given element
	enum atom_error_t sendCommand(
		ElementResponse &response,
		std::string element,
		std::string command,
		const uint8_t *data,
		size_t data_len,
		bool block = true);

	// Reads entries from the passed streams and passes the
	//	data onto the proper handlers
	enum atom_error_t entryReadLoop(
		ElementReadMap &m);

	// Reads N entries from the stream, returning them in order from
	//	newest to oldest. As such the most recent value is always
	//	at index 0 in the list
	enum atom_error_t entryReadN(
		std::string element,
		std::string stream,
		std::vector<std::string> &keys,
		size_t n,
		std::vector<entry_t> &ret);

	// Writes an entry to a data stream
	enum atom_error_t entryWrite(
		std::string stream,
		entry_t &data,
		int timestamp = ELEMENT_DATA_WRITE_DEFAULT_TIMESTAMP,
		int maxlen = ELEMENT_DATA_WRITE_DEFAULT_MAXLEN);

	// Writes an entry to the logs
	void log(
		int level,
		std::string msg);
	void log(
		int level,
		const char *fmt,
		...);

};

#endif // __ATOM_CPP_ELEMENT_H

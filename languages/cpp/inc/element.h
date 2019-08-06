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
#include <set>
#include <mutex>
#include <syslog.h>
#include <iostream>

#include "atom/atom.h"
#include "atom/redis.h"
#include "atom/element_entry_write.h"
#include "atom/element_entry_read.h"
#include "atom/element_command_server.h"
#include "atom/element_command_send.h"
#include "element_response.h"
#include "element_read_map.h"
#include "command.h"

#define ATOM_VERSION_CPP "v0.2.0"
#define ATOM_VERSION_COMMAND "version"
#define ATOM_HEALTHCHECK_COMMAND "healthcheck"
#define ATOM_HEALTHCHECK_RETRY_INTERVAL_MS 5000

#define ELEMENT_DEFAULT_N_CONTEXTS 20

#define ELEMENT_INFINITE_COMMAND_LOOPS 0

#define ELEMENT_INFINITE_READ_LOOPS 0

namespace atom {

// Entry value
typedef std::map<std::string, std::string> entry_data_t;

// Entry Class
class Entry {
	std::string id;
	entry_data_t data;

public:

	// Constructor/Destructor
	Entry(
		const char *xread_id);
	~Entry();

	// Add data to the entry
	void addData(
		const char *key,
		const char *data,
		size_t data_len);

	// Get the ID of the entry
	const std::string &getID();

	// Get the data of the entry
	const entry_data_t &getData();

	// Get the size of the entry
	size_t size();

	// Get a key in the entry
	const std::string &getKey(
		const std::string &key);
};

// Element class itself
class Element {

	// Name
	std::string name;

	// C element
	struct element *elem;

	// Redis context pool
	std::queue<redisContext *>context_pool;
	mutable std::mutex context_mutex;

	// Streams that we're currently publishing on
	std::map<std::string, struct element_entry_write_info *> streams;

	// List of commands we currently have support for
	std::map<std::string, Command *> commands;

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

	// Throws a std::runtime_error and also logs it to atom s.t. we can
	//	see in the logs why it happened
	void error(
		std::string str = "",
		bool log_atom = true);

	// Serializes Data
	template <typename Req>
	bool sendCommandSerialize(
		std::stringstream &buffer,
		Req &req_data,
		size_t &buffer_len)
	{
		try {
			msgpack::pack(buffer, req_data);
		} catch (...) {
			log(LOG_ERR, "Failed to serialize");
			return false;
		}

		// Get the buffer size and then seek it back
		//	to the beginning
		buffer.seekg(0, buffer.end);
		buffer_len = (size_t)buffer.tellg();
		buffer.seekg(0, buffer.beg);

		return true;
	}

	// Deserializes data
	template <typename Res>
	bool sendCommandDeserialize(
		ElementResponse &response,
		Res &res_data)
	{
		try {
			msgpack::object_handle oh = msgpack::unpack(
				response.getData().c_str(),
				response.getDataLen());

			msgpack::object deserialized = oh.get();
			deserialized.convert(res_data);
		// TODO: make this more specific
		} catch (...) {
			log(LOG_ERR, "Failed to deserialize");
			return false;
		}

		return true;
	}

	// Helper function for checking if another element meets version requirements
	bool checkElementVersion(
		std::string element,
		std::set<std::string> &supported_language_set,
		double supported_min_version);

public:

	// Constructors
	Element(
		std::string n,
		int n_contexts = ELEMENT_DEFAULT_N_CONTEXTS);

	// Destructor
	~Element();

	// Returns the name of the element
	const std::string &getName();

	// Returns version info for a given element in the system
	void getElementVersion(
		ElementResponse &response,
		std::map<std::string, std::string> &result,
		std::string element_name);

	// Blocks until all specified elements are up and reporting healthy
	void waitForElementsHealthy(
		std::vector<std::string> &elem_list,
		int retry_interval_ms = ATOM_HEALTHCHECK_RETRY_INTERVAL_MS,
		bool strict = true);

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

	// Adds support for a barebones command. Takes a command name,
	//	handler function and timeout to be returned to callers of this
	//	command
	void addCommand(
		std::string name,
		std::string description,
		command_handler_t fn,
		void *user_data,
		int timeout);

	// Adds support for a command class. Takes a reference
	//	to the class and does the rest internally
	void addCommand(
		Command *cmd);

	// Sets a custom healthcheck for this element.
	//	The user provided command_handler should return err code 0 if healthy,
	//	non 0 if unhealthy
	void healthcheckSet(
		command_handler_t fn,
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

	// Sends a commad using msgpack for serialization and deserialization
	template <typename Req, typename Res>
	enum atom_error_t sendCommand(
		ElementResponse &response,
		std::string element,
		std::string command,
		Req &req_data,
		Res &res_data,
		bool block = true)
	{
		// Pack the buffer
		std::stringstream buffer;
		size_t buffer_len;
		if (!sendCommandSerialize<Req>(buffer, req_data, buffer_len)) {
			return ATOM_SERIALIZATION_ERROR;
		}

		// Send the command using the packed buffer
		enum atom_error_t err = sendCommand(
			response,
			element,
			command,
			(uint8_t*)buffer.str().c_str(),
			buffer_len);
		if (err != ATOM_NO_ERROR) {
			return err;
		}

		if (!sendCommandDeserialize<Res>(response, res_data)) {
			return ATOM_DESERIALIZATION_ERROR;
		}

		// If we got here then we're all set
		return ATOM_NO_ERROR;
	}

	// Sends a commad using msgpack with no request data
	template <typename Res>
	enum atom_error_t sendCommandNoReq(
		ElementResponse &response,
		std::string element,
		std::string command,
		Res &res_data,
		bool block = true)
	{
		// Send the command using the packed buffer
		enum atom_error_t err = sendCommand(
			response,
			element,
			command,
			NULL,
			0);
		if (err != ATOM_NO_ERROR) {
			return err;
		}

		if (!sendCommandDeserialize<Res>(response, res_data)) {
			return ATOM_DESERIALIZATION_ERROR;
		}

		// If we got here then we're all set
		return ATOM_NO_ERROR;
	}

	// Sends a commad using msgpack with no response data
	template <typename Req>
	enum atom_error_t sendCommandNoRes(
		ElementResponse &response,
		std::string element,
		std::string command,
		Req &req_data,
		bool block = true)
	{
		// Pack the buffer
		std::stringstream buffer;
		size_t buffer_len;
		if (!sendCommandSerialize<Req>(buffer, req_data, buffer_len)) {
			return ATOM_SERIALIZATION_ERROR;
		}

		// Send the command using the packed buffer
		enum atom_error_t err = sendCommand(
			response,
			element,
			command,
			(uint8_t*)buffer.str().c_str(),
			buffer_len);
		if (err != ATOM_NO_ERROR) {
			return err;
		}

		// If we got here then we're all set
		return ATOM_NO_ERROR;
	}

	// Reads entries from the passed streams and passes the
	//	data onto the proper handlers
	enum atom_error_t entryReadLoop(
		ElementReadMap &m,
		int loops = ELEMENT_INFINITE_READ_LOOPS);

	// Reads N entries from the stream, returning them in order from
	//	newest to oldest. As such the most recent value is always
	//	at index 0 in the list
	enum atom_error_t entryReadN(
		std::string element,
		std::string stream,
		std::vector<std::string> &keys,
		size_t n,
		std::vector<Entry> &ret);

	// Reads at most N entries from the stream since the passed ID
	//	Default nonblocking. Pass 0 for timeout to block indefinitely,
	//	else a value in milliseconds
	enum atom_error_t entryReadSince(
		std::string element,
		std::string stream,
		std::vector<std::string> &keys,
		size_t n,
		std::vector<Entry> &ret,
		std::string last_id = "",
		int timeout=REDIS_XREAD_DONTBLOCK);

	// Writes an entry to a data stream
	enum atom_error_t entryWrite(
		std::string stream,
		entry_data_t &data,
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

} // namespace atom

#endif // __ATOM_CPP_ELEMENT_H

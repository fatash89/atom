////////////////////////////////////////////////////////////////////////////////
//
//  @file command.h
//
//  @brief Implements easy command class. Optionally can use
//			msgpack serialization and deserialization.
//
//  @copy 2018 Elementary Robotics. All rights reserved.
//
////////////////////////////////////////////////////////////////////////////////
#ifndef __ELEMENT_COMMAND_H
#define __ELEMENT_COMMAND_H

#include <sstream>
#include <msgpack.hpp>
#include <iostream>
#include "element_response.h"

namespace atom {

// Forward declaration of Element class s.t. we can have a pointer to it
//	in this class
class Element;

// Command Handler function
typedef bool (*command_handler_t)(
	const uint8_t *data,
	size_t data_len,
	ElementResponse *resp,
	void *user_data);

// Default command timeout of 1s
#define COMMAND_DEFAULT_TIMEOUT_MS 1000

// Base command class. Virtual deserialize and serialize
//	functions MUST be implemented by any inheriting class
class Command {
public:

	std::string name;
	std::string desc;

	int timeout_ms;

	Element *elem;
	ElementResponse *response;

	// Constructor takes a name, description and timeout
	Command(
		std::string n,
		std::string d,
		int t = COMMAND_DEFAULT_TIMEOUT_MS) :
		name(n),
		desc(d),
		timeout_ms(t),
		elem(NULL),
		response(NULL) {}

	// Virtual destructor. This is s.t. the derived classes
	//	can be properly destroyed
	virtual ~Command() {}

	// Add an element to the command
	void addElement(Element *element) {
		elem = element;
	}

	// Virtual init function. Do anything the
	//	class needs to do on a once-per-call basis
	virtual void init() { return; }

	// Set up function for each time we get
	//	a callback. Will call the inherited
	//	class's setup as well
	void _init() {
		response = new ElementResponse();
		init();
	}

	// Virtual cleanup function. Do anything the class
	//	needs to do on a once-per-call basis
	virtual void cleanup() { return; }

	// Cleanup function for each time we finish a callback.
	//	Will call the inherited class's cleanup as well
	void _cleanup() {
		delete response;
		cleanup();
	}

	// Deserialization function pointer
	virtual bool deserialize(
		const uint8_t *data,
		size_t data_len) = 0;

	// Serialization function
	virtual bool serialize() = 0;

	// Validation command
	virtual bool validate() = 0;

	// Run command
	virtual bool run() = 0;
};

// Command that executes a user callback with the
//	given callback function and data
class CommandUserCallback : public Command {
public:
	command_handler_t cb;
	void *udata;
	const uint8_t *req_data;
	size_t req_data_len;

	// Initialize the user callback command with the
	//	handler and the callback
	CommandUserCallback(
		std::string n,
		std::string d,
		command_handler_t handler,
		void *user_data,
		int t = COMMAND_DEFAULT_TIMEOUT_MS) :
		Command(n, d, t),
		cb(handler),
		udata(user_data) {}

	// No deserialization, just note the data
	virtual bool deserialize(
		const uint8_t *data,
		size_t data_len)
	{
		req_data = data;
		req_data_len = req_data_len;
		return true;
	}

	// Validator just passes everything
	virtual bool validate() { return true; }

	// Run function passes the data to the user callback
	virtual bool run() {
		return cb(req_data, req_data_len, response, udata);
	}

	// Serialization. Nothing to do here
	virtual bool serialize() { return true; }
};

// Msgpack message template with both request and response
template <class Req, class Res>
class CommandMsgpack : public Command {
public:
	// Request and response
	Req *req_data;
	Res *res_data;

	// Use the constructor and destructor from the base class
	CommandMsgpack(
		std::string n,
		std::string d,
		int t = COMMAND_DEFAULT_TIMEOUT_MS) :
		Command(n, d, t),
		req_data(NULL),
		res_data(NULL) {}

	// Init function. Allocate the request and response
	virtual void init() {
		req_data = new Req;
		res_data = new Res;
	}

	// Cleanup function. Free the request and response
	virtual void cleanup() {
		delete req_data;
		delete res_data;
	}

	// Deserialization function into req_data.
	virtual bool deserialize(
		const uint8_t *data,
		size_t data_len)
	{
        // Convert into the request data
        try {
			msgpack::object_handle oh =
				msgpack::unpack((const char *)data, data_len);
	        msgpack::object deserialized = oh.get();
        	deserialized.convert(*req_data);
        	return true;
        } catch (...) {
        	return false;
        }
	}

	// Serialization function
	virtual bool serialize()
	{
		std::stringstream buffer;

		// Try to serialize the data. This shouldn't
		//	ever fail since the class is templated
		try {
			msgpack::pack(buffer, *res_data);
			response->setData(buffer.str());
			return true;
		} catch (...) {
			return false;
		}
	}
};

// Msgpack message with no request data
template <class Res>
class CommandMsgpack<std::nullptr_t, Res> : public Command {
public:
	// Request and response
	Res *res_data;

	// Use the constructor and destructor from the base class
	CommandMsgpack(
		std::string n,
		std::string d,
		int t = COMMAND_DEFAULT_TIMEOUT_MS) :
		Command(n, d, t),
		res_data(NULL) {}

	// Init function. Allocate the request and response
	virtual void init() {
		res_data = new Res;
	}

	// Cleanup function. Free the request and response
	virtual void cleanup() {
		delete res_data;
	}

	// Deserialization function into req_data.
	virtual bool deserialize(
		const uint8_t *data,
		size_t data_len)
	{
        // Make sure we have no data
        return (data_len == 0);
	}

	// Validation function
	virtual bool validate() { return true; }

	// Serialization function
	virtual bool serialize()
	{
		std::stringstream buffer;

		// Try to serialize the data. This shouldn't
		//	ever fail since the class is templated
		try {
			msgpack::pack(buffer, *res_data);
			response->setData(buffer.str());
			return true;
		} catch (...) {
			return false;
		}
	}
};

// Msgpack message with no response data
template <class Req>
class CommandMsgpack<Req, std::nullptr_t>: public Command {
public:
	// Request and response
	Req *req_data;

	// Use the constructor and destructor from the base class
	CommandMsgpack(
		std::string n,
		std::string d,
		int t = COMMAND_DEFAULT_TIMEOUT_MS) :
		Command(n, d, t),
		req_data(NULL) {}

	// Init function. Allocate the request and response
	virtual void init() {
		req_data = new Req;
	}

	// Cleanup function. Free the request and response
	virtual void cleanup() {
		delete req_data;
	}

	// Deserialization function into req_data.
	virtual bool deserialize(
		const uint8_t *data,
		size_t data_len)
	{
        // Convert into the request data
        try {
			msgpack::object_handle oh =
				msgpack::unpack((const char *)data, data_len);
	        msgpack::object deserialized = oh.get();
        	deserialized.convert(*req_data);
        	return true;
        } catch (...) {
        	return false;
        }
	}

	// Serialization function
	virtual bool serialize()
	{
		return true;
	}
};

// Msgpack message with no request data
template <>
class CommandMsgpack<std::nullptr_t, std::nullptr_t> : public Command {
public:

	// Use the constructor and destructor from the base class
	using Command::Command;

	// Deserialization function into req_data.
	virtual bool deserialize(
		const uint8_t *data,
		size_t data_len)
	{
        // Make sure we have no data
        return (data_len == 0);
	}

	// Validation function
	virtual bool validate() { return true; }

	// Serialization function
	virtual bool serialize()
	{
		return true;
	}
};

} // namespace atom

#endif //__ELEMENT_COMMAND_H

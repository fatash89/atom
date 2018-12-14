////////////////////////////////////////////////////////////////////////////////
//
//  @file element_read_map.h
//
//  @brief Map of streams to handlers
//
//  @copy 2018 Elementary Robotics. All rights reserved.
//
////////////////////////////////////////////////////////////////////////////////

#ifndef __ATOM_CPP_ELEMENT_READ_MAP
#define __ATOM_CPP_ELEMENT_READ_MAP

#include "atom/atom.h"
#include "atom/redis.h"
#include "element_response.h"
#include <map>

namespace atom {

// Forward declaration for the entry class
class Entry;

// Read handler function
typedef bool (*readHandlerFn)(
	Entry &e,
	void *user_data);

// Typedef the tuple
typedef std::tuple<std::string, std::string, std::vector<std::string>, readHandlerFn, void*> handler_t;

// Response class
class ElementReadMap {
	std::vector<handler_t> handlers;

public:

	// Constructor and destructor
	ElementReadMap();
	~ElementReadMap();

	// Add in a handler
	void addHandler(
		std::string &element,
		std::string &stream,
		std::vector<std::string> &keys,
		readHandlerFn fn);

	// Add in a handler with user data
	void addHandler(
		std::string &element,
		std::string &stream,
		std::vector<std::string> &keys,
		readHandlerFn fn,
		void *user_data);

	// Gets the number of handlers
	size_t getNumHandlers();

	// Gets the info for a particular handler
	handler_t &getHandler(int n);
};

} // namespace atom

#endif // __ATOM_CPP_ELEMENT_READ_MAP

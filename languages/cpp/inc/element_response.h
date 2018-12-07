////////////////////////////////////////////////////////////////////////////////
//
//  @file element_response.h
//
//  @brief Header for the element response implementation
//
//  @copy 2018 Elementary Robotics. All rights reserved.
//
////////////////////////////////////////////////////////////////////////////////

#ifndef __ATOM_CPP_ELEMENT_RESPONSE_H
#define __ATOM_CPP_ELEMENT_RESPONSE_H

#include "atom/atom.h"
#include "atom/redis.h"
#include "element_response.h"
#include <queue>
#include <mutex>

// Response class
class ElementResponse {
	std::string data;
	int err;
	std::string err_str;

public:

	// Constructor
	ElementResponse();

	// Destructor
	~ElementResponse();

	// Sets the data
	void setData(
		const uint8_t *d,
		size_t l);
	void setData(
		std::string d);

	// Checks to see if the response has data
	bool hasData();

	// Sets the error
	void setError(
		int e,
		const char *s);
	void setError(
		int e,
		std::string s = "");

	// Gets the data pointer
	const uint8_t *getDataPtr();

	// Gets the data length
	size_t getDataLen();

	// Gets the data as a string
	const std::string &getData();

	// Gets the error
	int getError();

	// Checks to see if the response is an error
	bool isError();

	// Gets a pointer to the error string
	const uint8_t *getErrorStrPtr();

	// Gets the error string
	const std::string &getErrorStr();
};

#endif // __ATOM_CPP_ELEMENT_RESPONSE_H

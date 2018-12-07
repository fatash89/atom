////////////////////////////////////////////////////////////////////////////////
//
//  @file element.cc
//
//  @brief Element implementation atop the atom C library
//
//  @copy 2018 Elementary Robotics. All rights reserved.
//
////////////////////////////////////////////////////////////////////////////////
#include <mutex>
#include <queue>
#include <assert.h>
#include <string.h>
#include <iostream>

#include "atom/atom.h"
#include "atom/redis.h"
#include "atom/element.h"
#include "atom/element_command_send.h"
#include "element.h"
#include "element_response.h"

// Callbacks for atom C api need to be in an "extern C" block
extern "C" {

	bool getAllElementsStreamsCB(
		const char *element,
		void *user_data);

	bool sendCommandResponseCB(
		const uint8_t *response,
		size_t response_len,
		void *user_data);

	bool entryReadResponseCB(
		const struct redis_xread_kv_item *kv_items,
		int n_kv_items,
		void *user_data);

	int commandCB(
		uint8_t *data,
		size_t data_len,
		uint8_t **response,
		size_t *response_len,
		char **error_str,
		void *user_data);

	void commandCleanup(
		void *cleanup_ptr);
}

// Class for entry info from a handler to be passed to the callback function
class EntryReadInfo {
public:
	readHandlerFn fn;
	void *data;

	EntryReadInfo(
		readHandlerFn f,
		void *d) : fn(f), data(d)
	{

	}

	~EntryReadInfo()
	{

	}
};

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Initializes the context pool for an element. Creates a queue of
//			contexts that will be used to communicate with redis
//
////////////////////////////////////////////////////////////////////////////////
void Element::initContextPool(
	int n_contexts)
{
	std::lock_guard<std::mutex> lock(context_mutex);

	for (int i = 0; i < n_contexts; ++i) {
		redisContext *new_context = redis_context_init();
		context_pool.push(new_context);
	}
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Frees and cleans up all of the redis contexts we've created
//
////////////////////////////////////////////////////////////////////////////////
void Element::cleanupContextPool()
{
	std::lock_guard<std::mutex> lock(context_mutex);
	while (!context_pool.empty()) {
		redisContext *ctx = context_pool.front();
		redis_context_cleanup(ctx);
		context_pool.pop();
	}
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Gets a context from our context pool
//
////////////////////////////////////////////////////////////////////////////////
redisContext *Element::getContext()
{
	std::lock_guard<std::mutex> lock(context_mutex);
	redisContext *ctx = context_pool.front();
	context_pool.pop();
	return ctx;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Releases a context back to the context pool
//
////////////////////////////////////////////////////////////////////////////////
void Element::releaseContext(redisContext *ctx)
{
	std::lock_guard<std::mutex> lock(context_mutex);
	context_pool.push(ctx);
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Main constructor. Takes an element name and the number of
//			contexts to keep in the pool
//
////////////////////////////////////////////////////////////////////////////////
Element::Element(
	std::string n,
	int n_contexts) : context_pool(), context_mutex()
{
	// Copy over the name
	name = n;

	// Initialize the context pool
	initContextPool(n_contexts);

	// Get a context
	redisContext *ctx = getContext();

	// Make an element
	elem = element_init(ctx, name.c_str());

	// Release the context
	releaseContext(ctx);
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Destructor. Cleans up the element and all associated
//			contexts.
//
////////////////////////////////////////////////////////////////////////////////
Element::~Element()
{
	redisContext *ctx = getContext();

	// Need to clean up all of the stream infos that we're publishing
	for (auto const &x : streams) {
		element_entry_write_cleanup(ctx, x.second);
	}

	element_cleanup(ctx, elem);
	releaseContext(ctx);
	cleanupContextPool();
}


////////////////////////////////////////////////////////////////////////////////
//
//  @brief Returns the name of the element
//
////////////////////////////////////////////////////////////////////////////////
const std::string &Element::getName()
{
	return name;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Callback for when we get a new element in the scan
//
////////////////////////////////////////////////////////////////////////////////
bool getAllElementsStreamsCB(
	const char *element,
	void *user_data)
{
	std::vector<std::string> *elem_list = (std::vector<std::string> *)user_data;

	elem_list->push_back(std::string(element));
	return true;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Returns a list of all elements
//
////////////////////////////////////////////////////////////////////////////////
enum atom_error_t Element::getAllElements(
	std::vector<std::string> &elem_list)
{
	// Get a context
	redisContext *ctx = getContext();

	// Call the function to get all elements
	enum atom_error_t err = atom_get_all_elements_cb(
		ctx,
		getAllElementsStreamsCB,
		(void*)&elem_list);

	releaseContext(ctx);

	return err;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Returns a list of all streams for a given element
//
////////////////////////////////////////////////////////////////////////////////
enum atom_error_t Element::getAllStreams(
	std::vector<std::string> &stream_list,
	std::string element)
{
	// Get a context
	redisContext *ctx = getContext();

	// Call the function to get all streams
	enum atom_error_t err = atom_get_all_data_streams_cb(
		ctx,
		element.c_str(),
		getAllElementsStreamsCB,
		(void*)&stream_list);

	releaseContext(ctx);

	return err;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Returns a map of all streams in the system with all elements
//
////////////////////////////////////////////////////////////////////////////////
enum atom_error_t Element::getAllStreams(
	std::map<std::string, std::vector<std::string>> &stream_map)
{
	// Get a context
	redisContext *ctx = getContext();

	// Make the list for all of the strings
	std::vector<std::string> stream_list;

	// Call the function to get all streams
	enum atom_error_t err = atom_get_all_data_streams_cb(
		ctx,
		NULL,
		getAllElementsStreamsCB,
		(void*)&stream_list);

	releaseContext(ctx);

	// Now, parse the list down into the map
	for (auto const &x: stream_list) {

		// Find the delimiter
		auto delim = x.find(":");
		if (delim == std::string::npos) {
			throw std::runtime_error("Invalid stream");
		}

		// Get the element and stream
		std::string element = x.substr(0, delim);
		std::string stream = x.substr(delim + 1, x.size());

		// If the element isn't in the stream, we want to make the vector
		if (stream_map.find(element) == stream_map.end()) {
			stream_map[element] = { std::move(stream) };
		} else {
			stream_map[element].emplace_back(std::move(stream));
		}
	}

	return err;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Response callback for when we send a command. This will just
//			allocate the ElementResponse and pass it back to us
//
////////////////////////////////////////////////////////////////////////////////
bool sendCommandResponseCB(
	const uint8_t *response,
	size_t response_len,
	void *user_data)
{
	// Make the response
	ElementResponse *resp = (ElementResponse *)user_data;
	resp->setData(response, response_len);

	return true;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Cleanup for a command being called
//
////////////////////////////////////////////////////////////////////////////////
void commandCleanup(
	void *cleanup_ptr)
{
	delete (ElementResponse *)cleanup_ptr;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Callback for when we get a command
//
////////////////////////////////////////////////////////////////////////////////
int commandCB(
	uint8_t *data,
	size_t data_len,
	uint8_t **response,
	size_t *response_len,
	char **error_str,
	void *user_data,
	void **cleanup_ptr)
{
	// Cast the user data to the pair of command handler and other
	//	user data
	std::pair<element_command_handler_t, void *> *udata =
		(std::pair<element_command_handler_t, void *> *)user_data;

	// Make the response and then call the command handler
	ElementResponse *r = new ElementResponse();
	if (!udata->first(data, data_len, r, udata->second)) {
		throw std::runtime_error("User callback failed");
	}

	// Copy over response data, if any
	if (!r->isError()) {
		if (r->hasData()) {
			*response = (uint8_t*)r->getDataPtr();
			*response_len = r->getDataLen();
		} else {
			*response = NULL;
			*response_len = 0;
		}
	} else {
		*error_str = (char*)r->getErrorStrPtr();
	}

	// Note the cleanup pointer
	*cleanup_ptr = (void*)r;

	// And return the response code
	return r->getError();
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Reads N pieces of data from each stream passed
//
////////////////////////////////////////////////////////////////////////////////
void Element::addCommand(
	std::string name,
	element_command_handler_t fn,
	void *user_data,
	int timeout)
{
	commands.emplace(name, std::make_pair(fn, user_data));

	if (!element_command_add(
		elem,
		name.c_str(),
		commandCB,
		commandCleanup,
		(void*)&(commands.find(name)->second),
		timeout))
	{
		throw std::runtime_error("Failed to add command");
	}
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Loops, handling all commands
//
////////////////////////////////////////////////////////////////////////////////
enum atom_error_t Element::commandLoop(
	int n_loops)
{
	redisContext *ctx = getContext();
	enum atom_error_t err;

	if (n_loops == ELEMENT_INFINITE_COMMAND_LOOPS) {
		err = element_command_loop(
			ctx,
			elem,
			true,
			ELEMENT_COMMAND_LOOP_NO_TIMEOUT);
	} else {
		for (int i = 0; i < n_loops; ++i) {
			err = element_command_loop(
				ctx,
				elem,
				false,
				ELEMENT_COMMAND_LOOP_NO_TIMEOUT);
			if (err != ATOM_NO_ERROR) {
				break;
			}
		}
	}
	releaseContext(ctx);
	return err;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Sends a command to another element. Note that the caller needs to
//			delete this response upon receiving it.
//
////////////////////////////////////////////////////////////////////////////////
enum atom_error_t Element::sendCommand(
	ElementResponse &response,
	std::string element,
	std::string command,
	const uint8_t *data,
	size_t data_len,
	bool block)
{
	// Want to be able to get the error string
	char *error_str = NULL;

	// Get a redis context
	redisContext *ctx = getContext();

	// Attempt to send the command
	enum atom_error_t err = element_command_send(
		ctx,
		elem,
		element.c_str(),
		command.c_str(),
		data,
		data_len,
		block,
		sendCommandResponseCB,
		(void*)&response,
		&error_str);

	// Release the context
	releaseContext(ctx);

	// If there's an error we want to update the response with that info
	if (err != ATOM_NO_ERROR) {
		response.setError(err, error_str);
	}

	// If there's an error string returned from the API then we want to
	//	free it
	if (error_str != NULL) {
		free(error_str);
	}

	return err;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Callback for when we get info from a stream
//
////////////////////////////////////////////////////////////////////////////////
bool entryReadResponseCB(
	const struct redis_xread_kv_item *kv_items,
	int n_kv_items,
	void *user_data)
{
	// Cast the user data to the proper handler function
	EntryReadInfo *udata = (EntryReadInfo *)user_data;

	// Convert the kv items into the ElementReadData
	entry_t data;
	for (int i = 0; i < n_kv_items; ++i) {
		if (kv_items[i].found) {
			std::string new_str(kv_items[i].reply->str, kv_items[i].reply->len);
			data.emplace(kv_items[i].key, std::move(new_str));
		} else {
			throw std::runtime_error("Couldn't find key");
		}
	}

	// Now, we want to call the user callback
	if (!udata->fn(data, udata->data)) {
		throw std::runtime_error("User callback failed");
	}

	return true;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Reads in a loop from the handlers in the ElementReadMap
//
////////////////////////////////////////////////////////////////////////////////
struct element_entry_read_info *Element::readMapToEntryInfo(
	ElementReadMap &m)
{
	struct element_entry_read_info *read_infos;

	// Need to fill out the read info.
	size_t n_infos = m.getNumHandlers();
	read_infos = (struct element_entry_read_info *)
		malloc(n_infos * sizeof(struct element_entry_read_info));
	assert(read_infos != NULL);

	// Loop over the infos and fill them out
	for (size_t i = 0; i < n_infos; ++i) {
		auto handler = m.getHandler(i);

		// First is element, second is stream, third
		read_infos[i].element = std::get<0>(handler).c_str();
		read_infos[i].stream = std::get<1>(handler).c_str();

		// Get the keys
		auto keys = std::get<2>(handler);
		size_t n_keys = keys.size();

		// Make the KV items
		read_infos[i].kv_items = (struct redis_xread_kv_item *)
			malloc(n_keys * sizeof(struct redis_xread_kv_item));
		read_infos[i].n_kv_items = n_keys;

		// Fill in the kv items
		for (size_t j = 0; j < n_keys; ++j) {
			read_infos[i].kv_items[j].key = keys[j].c_str();
			read_infos[i].kv_items[j].key_len = keys[j].size();
		}

		// Fill in the handler and response callback
		read_infos[i].user_data = (void*)new EntryReadInfo(
			std::get<3>(handler),
			std::get<4>(handler));
		read_infos[i].response_cb = entryReadResponseCB;
	}

	return read_infos;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Reads in a loop from the handlers in the ElementReadMap
//
////////////////////////////////////////////////////////////////////////////////
void Element::freeEntryInfo(
	struct element_entry_read_info *info,
	size_t n_infos)
{
	// And go ahead and free all of the info
	if (info != NULL) {
		for (size_t i = 0; i < n_infos; ++i) {
			if (info[i].kv_items != NULL) {
				free(info[i].kv_items);
			}
			if (info[i].user_data != NULL) {
				delete (EntryReadInfo *)info[i].user_data;
			}
		}
		free(info);
	}
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Reads in a loop from the handlers in the ElementReadMap
//
////////////////////////////////////////////////////////////////////////////////
enum atom_error_t Element::entryReadLoop(
	ElementReadMap &m)
{
	struct element_entry_read_info *read_infos = readMapToEntryInfo(m);
	size_t n_infos = m.getNumHandlers();

	// And now call element_entry_read_loop
	redisContext *ctx = getContext();
	enum atom_error_t err = element_entry_read_loop(
		ctx,
		elem,
		read_infos,
		n_infos,
		true,
		ELEMENT_ENTRY_READ_LOOP_FOREVER);

	// Put the context back
	releaseContext(ctx);

	// And free the entry info we made
	freeEntryInfo(read_infos, n_infos);

	return err;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Copies the data into the vector passed in user_data
//
////////////////////////////////////////////////////////////////////////////////
bool entryCopyCB(
	entry_t &keys,
	void *user_data)
{
	std::vector<entry_t> *user_vector =
		(std::vector<entry_t>*)user_data;

	user_vector->emplace_back(std::move(keys));

	return true;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Reads N pieces of data from each stream passed
//
////////////////////////////////////////////////////////////////////////////////
enum atom_error_t Element::entryReadN(
	std::string element,
	std::string stream,
	std::vector<std::string> &keys,
	size_t n,
	std::vector<entry_t> &ret)
{
	struct element_entry_read_info read_info;

	// Fill in the read info
	read_info.element = element.c_str();
	read_info.stream = stream.c_str();

	// Get the keys
	size_t n_keys = keys.size();

	// Make the KV items
	read_info.kv_items = (struct redis_xread_kv_item *)
		malloc(n_keys * sizeof(struct redis_xread_kv_item));
	assert(read_info.kv_items != NULL);
	read_info.n_kv_items = n_keys;

	// Fill in the kv items
	for (size_t j = 0; j < n_keys; ++j) {
		read_info.kv_items[j].key = keys[j].c_str();
		read_info.kv_items[j].key_len = keys[j].size();
	}

	// Fill in the handler and response callback
	read_info.user_data = (void*)new EntryReadInfo(entryCopyCB, (void*)&ret);
	read_info.response_cb = entryReadResponseCB;

	// And now call element_entry_read_n
	redisContext *ctx = getContext();
	enum atom_error_t err = element_entry_read_n(
		ctx,
		elem,
		&read_info,
		n);

	// Put the context back
	releaseContext(ctx);

	// And clean up the memory we allocated
	delete (EntryReadInfo *)read_info.user_data;
	free(read_info.kv_items);

	return err;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Writes an entry to a stream
//
////////////////////////////////////////////////////////////////////////////////
enum atom_error_t Element::entryWrite(
	std::string stream,
	entry_t &data,
	int timestamp,
	int maxlen)
{
	redisContext *ctx = getContext();

	// Try to find the write info for the stream
	auto exists = streams.find(stream);
	struct element_entry_write_info *info = NULL;

	// We did not find the write info or the number of keys was off
	if ((exists == streams.end()) ||
		(exists->second->n_items != data.size()))
	{
		// If the stream info exists we want to clean it up
		if (exists != streams.end()) {
			element_entry_write_cleanup(ctx, exists->second);
		}

		// Make the info
		info = element_entry_write_init(
			ctx,
			elem,
			stream.c_str(),
			data.size());
		assert(info != NULL);

		// Fill in the keys in the info
		int idx = 0;
		for (auto const &x: data) {

			// Fill in the write info
			info->items[idx].key = x.first.c_str();
			info->items[idx].key_len = x.first.size();

			// Increment the index
			idx += 1;
		}

		streams.emplace(stream, info);

	// We found the write info
	} else {
		info = exists->second;
	}


	// Loop over the keys in the info
	for (size_t idx = 0; idx < info->n_items; ++idx) {

		// Find the item in the input dict
		auto item = data.find(info->items[idx].key);
		if (item == data.end()) {
			std::runtime_error("Invalid key for stream");
		}

		// Fill in the data size and length
		info->items[idx].data = (const uint8_t*)item->second.c_str();
		info->items[idx].data_len = item->second.size();
	}

	// Do the write
	enum atom_error_t err = element_entry_write(
		ctx,
		info,
		timestamp,
		maxlen);

	// Return the context
	releaseContext(ctx);

	// And return the error
	return err;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Writes a log message
//
////////////////////////////////////////////////////////////////////////////////
void Element::log(
	int level,
	std::string msg)
{
	redisContext *ctx = getContext();
	if (atom_log(ctx, elem, level, msg.c_str(), msg.size()) != ATOM_NO_ERROR) {
		throw std::runtime_error("Failed to log");
	}
	releaseContext(ctx);
}

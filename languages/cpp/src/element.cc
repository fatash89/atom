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

namespace atom {

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
		const char *id,
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
//  @brief Entry constructor. Make it with an ID and then add data for each
//			key we receive
//
////////////////////////////////////////////////////////////////////////////////
Entry::Entry(
	const char *xread_id)
{
	id = std::string(xread_id);
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Entry destructor. Not much to do
//
////////////////////////////////////////////////////////////////////////////////
Entry::~Entry()
{

}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Add data to an entry
//
////////////////////////////////////////////////////////////////////////////////
void Entry::addData(
	const char *k,
	const char *d,
	size_t l)
{
	std::string new_str(d, l);
	data.emplace(k, std::move(new_str));
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Get ID of an entry
//
////////////////////////////////////////////////////////////////////////////////
const std::string &Entry::getID()
{
	return id;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Get data of an entry
//
////////////////////////////////////////////////////////////////////////////////
const entry_data_t &Entry::getData()
{
	return data;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Get key in data
//
////////////////////////////////////////////////////////////////////////////////
const std::string &Entry::getKey(
	const std::string &key)
{
	return data.at(key);
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Get size
//
////////////////////////////////////////////////////////////////////////////////
size_t Entry::size()
{
	return data.size();
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Initializes the context pool for an element. Creates a queue of
//			contexts that will be used to communicate with redis
//
////////////////////////////////////////////////////////////////////////////////
void Element::initContextPool(
	socketType type,
	int n_contexts)
{
	std::lock_guard<std::mutex> lock(context_mutex);

	for (int i = 0; i < n_contexts; ++i) {
		redisContext *new_context =
			redis_context_init_default(type);
		context_pool.push(new_context);
	}
}

void Element::initContextPool(
	char* socket,
	int n_contexts)
{
	std::lock_guard<std::mutex> lock(context_mutex);

	for (int i = 0; i < n_contexts; ++i) {
		redisContext *new_context = redis_context_init_config(
										LOCAL,
										socket
										);
		context_pool.push(new_context);
	}
}

void Element::initContextPool(
	char* addr,
	int port,
	int n_contexts)
{
	std::lock_guard<std::mutex> lock(context_mutex);

	for (int i = 0; i < n_contexts; ++i) {
		redisContext *new_context = redis_context_init_config(
										REMOTE,
										addr, port
										);
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
	initContextPool(REDIS_DEFAULT_SOCKET_TYPE, n_contexts);

	// Get a context
	redisContext *ctx = getContext();

	// Make an element
	elem = element_init(ctx, name.c_str());

	// Release the context
	releaseContext(ctx);
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Constructor specifying use of local or remote redis server.
//			Contexts initialized with default local socket name or remote
//			socket address and port
//
////////////////////////////////////////////////////////////////////////////////
Element::Element(
	std::string n,
	socketType type,
	int n_contexts) : context_pool(), context_mutex()
{
	// Copy over the name
	name = n;

	// Initialize the context pool
	initContextPool(type, n_contexts);

	// Get a context
	redisContext *ctx = getContext();

	// Make an element
	elem = element_init(ctx, name.c_str());

	// Release the context
	releaseContext(ctx);
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Constructor specifying socket for local redis server
//
////////////////////////////////////////////////////////////////////////////////
Element::Element(
	std::string n,
	char* socket,
	int n_contexts) : context_pool(), context_mutex()
{
	// Copy over the name
	name = n;

	// Initialize the context pool
	initContextPool(socket, n_contexts);

	// Get a context
	redisContext *ctx = getContext();

	// Make an element
	elem = element_init(ctx, name.c_str());

	// Release the context
	releaseContext(ctx);
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Constructor specifying address and port for remote redis server
//
////////////////////////////////////////////////////////////////////////////////
Element::Element(
	std::string n,
	char* addr,
	int port,
	int n_contexts) : context_pool(), context_mutex()
{
	// Copy over the name
	name = n;

	// Initialize the context pool
	initContextPool(addr, port, n_contexts);

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
		struct element_entry_write_info *info = x.second;
		for (size_t i = 0; i < info->n_items; ++i) {
			free((char*)info->items[i].key);
		}
		element_entry_write_cleanup(ctx, x.second);
	}

	//Need to delete all of the command classes associated with us
	for (auto &cmd : commands) {
		delete cmd.second;
	}

	element_cleanup(ctx, elem);
	releaseContext(ctx);
	cleanupContextPool();
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Handles throwing errors and making sure that they're logged to
//			the atom system if log_atom is true. Mainly need this s.t. in the
//			log functions we don't go into a recursive loop
//
////////////////////////////////////////////////////////////////////////////////
void Element::error(
	std::string str,
	bool log_atom)
{
	// Log it to atom
	if (log_atom) {
		log(LOG_ERR, str);
	}

	// Throw the error
	throw std::runtime_error(str);
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
			error("Invalid stream");
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
	// Cast the user data into a command
	Command *cmd = (Command *)cleanup_ptr;

	// Clean up anything the command allocated
    cmd->_cleanup();
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
	int error = 0;

	const char *deserializeError = "Failed to deserialize";
	const char *validateError = "Failed to validate";
	const char *runError = "Failed to run";
	const char *serializeError = "Failed to serialize";

	// We'll need to call the _cleanup function for the
	//	command after it's done
	*cleanup_ptr = user_data;

	// Cast the user data into a command
	Command *cmd = (Command *)user_data;

	// Initialize the command
	cmd->_init();

	// Run through the command functions
    if (!cmd->deserialize(data, data_len)) {
        *error_str = (char*)deserializeError;
        error = 101;
        goto done;
    }
    if (!cmd->validate()) {
        *error_str = (char*)validateError;
        error = 102;
        goto done;
    }
    if (!cmd->run()) {
        *error_str = (char*)runError;
        error = 103;
        goto done;
    }
    if (!cmd->serialize()) {
        *error_str = (char*)serializeError;
        error = 104;
        goto done;
    }

	// If we had a successful handler call
	if (!cmd->response->isError()) {

		// Copy over the data, if any
		if (cmd->response->hasData()) {
			*response = (uint8_t*)cmd->response->getDataPtr();
			*response_len = cmd->response->getDataLen();
		} else {
			*response = NULL;
			*response_len = 0;
		}

	// Otherwise get the error string and log the error
	} else {
		*error_str = (char*)cmd->response->getErrorStrPtr();
	}

	error = cmd->response->getError();

done:
	if (error != 0) {
		cmd->elem->log(LOG_ERR, "Command %s: Error code %d: '%s'",
			cmd->name.c_str(),
			error,
			(*error_str != NULL) ? *error_str : "");
	} else {
		cmd->elem->log(LOG_DEBUG, "Command %s: Success", cmd->name.c_str());
	}

	// And return the response code
	return error;
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Adds a command and its handler to the map of supported commands
//
////////////////////////////////////////////////////////////////////////////////
void Element::addCommand(
	std::string name,
	std::string description,
	command_handler_t fn,
	void *user_data,
	int timeout)
{
	std::cout << "Creating command with name " << name << std::endl;

	// Make the new user callback command
	Command *new_cmd = new CommandUserCallback(
		name,
		description,
		fn,
		user_data,
		timeout);
	new_cmd->addElement(this);

	// Put the command in the map
	commands.emplace(name, new_cmd);

	if (!element_command_add(
		elem,
		name.c_str(),
		commandCB,
		commandCleanup,
		new_cmd,
		timeout))
	{
		error("Failed to add command");
	}
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Adds a command class to the element. Note that the command MUST
//			continue to stay in scope throughut commandLoop().
//
////////////////////////////////////////////////////////////////////////////////
void Element::addCommand(
	Command *cmd)
{
	cmd->addElement(this);
	commands.emplace(cmd->name, cmd);

	if (!element_command_add(
		elem,
		cmd->name.c_str(),
		commandCB,
		commandCleanup,
		cmd,
		cmd->timeout_ms))
	{
		error("Failed to add command");
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
	const char *id,
	const struct redis_xread_kv_item *kv_items,
	int n_kv_items,
	void *user_data)
{
	// Cast the user data to the proper handler function
	EntryReadInfo *udata = (EntryReadInfo *)user_data;

	// Convert the kv items into the ElementReadData
	Entry e(id);
	for (int i = 0; i < n_kv_items; ++i) {
		if (kv_items[i].found) {
			e.addData(kv_items[i].key, kv_items[i].reply->str, kv_items[i].reply->len);
		} else {
			atom_logf(NULL, NULL, LOG_ERR, "Couldn't find key");
		}
	}

	// Now, we want to call the user callback
	if (!udata->fn(e, udata->data)) {
		atom_logf(NULL, NULL, LOG_ERR, "User callback failed");
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
	// Need to fill out the read info.
	size_t n_infos = m.getNumHandlers();

	struct element_entry_read_info *read_infos = (struct element_entry_read_info *)
		malloc(n_infos * sizeof(struct element_entry_read_info));
	assert(read_infos != NULL);

	// Loop over the infos and fill them out
	for (size_t i = 0; i < n_infos; ++i) {
		auto handler = m.getHandler(i);

		// First is element, second is stream, third
		std::string &element = std::get<0>(handler);
		read_infos[i].element = (element.size() > 0) ? strdup(element.c_str()) : NULL;
		read_infos[i].stream = strdup(std::get<1>(handler).c_str());

		// Get the keys
		auto keys = std::get<2>(handler);
		size_t n_keys = keys.size();

		// Make the KV items
		read_infos[i].kv_items = (struct redis_xread_kv_item *)
			malloc(n_keys * sizeof(struct redis_xread_kv_item));
		read_infos[i].n_kv_items = n_keys;

		// Fill in the kv items
		for (size_t j = 0; j < n_keys; ++j) {
			read_infos[i].kv_items[j].key = strdup(keys[j].c_str());
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
			if (info[i].element != NULL) {
				free((void*)info[i].element);
			}
			if (info[i].stream != NULL) {
				free((void*)info[i].stream);
			}
			if (info[i].kv_items != NULL) {
				for (size_t j = 0; j < info[i].n_kv_items; ++j) {
					free((void*)info[i].kv_items[j].key);
				}
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
	ElementReadMap &m,
	int n_loops)
{
	struct element_entry_read_info *read_infos = readMapToEntryInfo(m);
	size_t n_infos = m.getNumHandlers();

	// And now call element_entry_read_loop
	redisContext *ctx = getContext();

	// And if we're looping infinitely
	enum atom_error_t err;
	if (n_loops == ELEMENT_INFINITE_READ_LOOPS) {
		err = element_entry_read_loop(
			ctx,
			elem,
			read_infos,
			n_infos,
			true,
			ELEMENT_ENTRY_READ_LOOP_FOREVER);
	} else {
		for (size_t i = 0; i < n_infos; ++i) {
			read_infos[i].items_to_read = n_loops;
		}

		err = element_entry_read_loop(
			ctx,
			elem,
			read_infos,
			n_infos,
			false,
			ELEMENT_ENTRY_READ_LOOP_FOREVER);
	}

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
	Entry &e,
	void *user_data)
{
	std::vector<Entry> *user_vector =
		(std::vector<Entry>*)user_data;

	user_vector->emplace_back(std::move(e));

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
	std::vector<Entry> &ret)
{
	struct element_entry_read_info read_info;

	// Fill in the read info
	read_info.element = (element.size() > 0) ? element.c_str() : NULL;
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
//  @brief Reads at most N entries from the stream since the passed ID.
//			Default nonblocking
//
////////////////////////////////////////////////////////////////////////////////
enum atom_error_t Element::entryReadSince(
	std::string element,
	std::string stream,
	std::vector<std::string> &keys,
	size_t n,
	std::vector<Entry> &ret,
	std::string last_id,
	int timeout)
{
	struct element_entry_read_info read_info;

	// Fill in the read info
	read_info.element = (element.size() > 0) ? element.c_str() : NULL;
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

	// And now call element_entry_read_since
	redisContext *ctx = getContext();
	enum atom_error_t err = element_entry_read_since(
		ctx,
		elem,
		&read_info,
		(last_id.size() > 0) ? last_id.c_str() : NULL,
		timeout,
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
	entry_data_t &data,
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
			info = exists->second;
			for (size_t i = 0; i < info->n_items; ++i) {
				free((char*)info->items[i].key);
			}
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
			info->items[idx].key = strdup(x.first.c_str());
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
	enum atom_error_t err = atom_log(ctx, elem, level, msg.c_str(), msg.size());
	releaseContext(ctx);
	if (err != ATOM_NO_ERROR) {
		error("Failed to log", false);
	}
}

////////////////////////////////////////////////////////////////////////////////
//
//  @brief Writes a log message using variadic format
//
////////////////////////////////////////////////////////////////////////////////
void Element::log(
	int level,
	const char *fmt,
	...)
{
	va_list args;
	va_start(args, fmt);

	redisContext *ctx = getContext();
	enum atom_error_t err = atom_vlogf(ctx, elem, level, fmt, args);
	releaseContext(ctx);
	if (err != ATOM_NO_ERROR) {
		error("Failed to log", false);
	}
}

} // namespace atom

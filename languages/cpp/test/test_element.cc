////////////////////////////////////////////////////////////////////////////////
//
//  @file atom_test_element.cc
//
//  @brief Redis element tests for atom
//
//  @copy 2018 Elementary Robotics. All rights reserved.
//
////////////////////////////////////////////////////////////////////////////////
#include <gtest/gtest.h>
#include <string.h>
#include <list>
#include <hiredis/hiredis.h>
#include <thread>
#include <unistd.h>
#include <limits.h>
#include "atom/atom.h"
#include "atom/redis.h"
#include "element.h"
#include "element_response.h"
#include "element_read_map.h"
#include <cpp_redis/cpp_redis>

// Need to use the atom namespace
using namespace atom;

//
// Tests for valid element names
//
class ElementTest : public testing::Test
{

protected:
	Element *element;

	virtual void SetUp() {
		// Get a context and send a flushAll to remove all existing keys
		redisContext *ctx = redis_context_init();
		redisReply *reply = (redisReply *)redisCommand(ctx, "FLUSHALL");
		ASSERT_NE(reply, (redisReply*)NULL);
		freeReplyObject(reply);
		redis_context_cleanup(ctx);

		// Set up the new element
		element = new Element("testing");
	};

	virtual void TearDown() {
		delete element;
	};
};

// Tests the SetUp and TearDown functions which
//	create an element and then clean it up. Not testing much,
//	but enough that we can connect to the redis server and handle
//	the XADDs on the command/response streams and the subsequent DELs
//	on those streams when we clean up
TEST_F(ElementTest, setup_teardown) {
	ASSERT_EQ(1, 1);
}

// Tests getting all of the elements present
TEST_F(ElementTest, get_all_elements) {
	Element hello("hello");
	Element world("world");

	std::vector<std::string> elements;
	ASSERT_EQ(element->getAllElements(elements), ATOM_NO_ERROR);


	std::map<std::string, bool> found;
	found["testing"] = false;
	found["hello"] = false;
	found["world"] = false;

	for (auto const &x : elements) {
		ASSERT_NE(found.find(x), found.end()) << "Received unexpected element " << x;
		found[x] = true;
	}

	for (auto const &x : found) {
		ASSERT_EQ(x.second, true) << "Didn't find element " << x.first;
	}
}

// Tests writing data to a stream and then reading it back
TEST_F(ElementTest, single_entry_single_key) {

	// Make the data to write
	entry_data_t data;
	data["hello"] = "world";

	// Do the write
	ASSERT_EQ(element->entryWrite("foobar", data), ATOM_NO_ERROR);

	// Do the read back
	std::vector<Entry> ret;
	std::vector<std::string> keys = {"hello"};
	ASSERT_EQ(element->entryReadN(
		"testing",
		"foobar",
		keys,
		1,
		ret), ATOM_NO_ERROR);

	// Make sure we read back one value
	ASSERT_EQ(ret.size(), 1);

	// Within that value make sure there's one key
	ASSERT_EQ(ret[0].size(), data.size());

	for (auto const &x : ret[0].getData()) {
		ASSERT_NE(data.find(x.first), data.end()) << "Read back key " << x.first << " which was not data";
		ASSERT_EQ(data[x.first], x.second);
	}
}

// Tests writing data to a stream and then reading it back
TEST_F(ElementTest, single_entry_multiple_keys) {

	// Make the data to write
	entry_data_t data;
	data["hello"] = "world";
	data["foo"] = "bar";
	data["elementary"] = "robotics";

	// Do the write
	ASSERT_EQ(element->entryWrite("foobar", data), ATOM_NO_ERROR);

	// Do the read back
	std::vector<Entry> ret;
	std::vector<std::string> keys = {"hello", "foo", "elementary"};
	ASSERT_EQ(element->entryReadN(
		"testing",
		"foobar",
		keys,
		1,
		ret), ATOM_NO_ERROR);

	// Make sure there are the same number of keys
	ASSERT_EQ(ret.size(), 1);
	ASSERT_EQ(ret[0].size(), data.size());

	for (auto const &x : ret[0].getData()) {
		ASSERT_NE(data.find(x.first), data.end()) << "Read back key " << x.first << " which was not data";
		ASSERT_EQ(data[x.first], x.second);
	}
}

// Tests writing data to a stream and then reading it back
TEST_F(ElementTest, multiple_entry_multiple_keys) {

	// Make the data to write
	entry_data_t data;

	// Write the three keys 5 times each
	for (int i = 0; i < 5; ++i) {
		data["hello"] = "world" + std::to_string(i);
		data["foo"] = "bar" + std::to_string(i);
		data["elementary"] = "robotics" + std::to_string(i);

		// Do the write
		ASSERT_EQ(element->entryWrite("foobar", data), ATOM_NO_ERROR);
	}


	// Do the read back
	std::vector<Entry> ret;
	std::vector<std::string> keys = {"hello", "foo", "elementary"};
	ASSERT_EQ(element->entryReadN(
		"testing",
		"foobar",
		keys,
		5,
		ret), ATOM_NO_ERROR);

	// Make sure we got 5 values back
	ASSERT_EQ(ret.size(), 5);

	// Loop over each value in the return
	for (int i = 0; i < 5; ++i) {

		// Get the value
		auto val = ret.at(i).getData();

		// Make sure the keys have the right data
		data["hello"] = "world" + std::to_string(4 - i);
		data["foo"] = "bar" + std::to_string(4 - i);
		data["elementary"] = "robotics" + std::to_string(4 - i);

		// Make sure there are the same number of keys
		ASSERT_EQ(val.size(), data.size());

		for (auto const &x : val) {
			ASSERT_NE(data.find(x.first), data.end()) << "Read back key " << x.first << " which was not data";
			ASSERT_EQ(data[x.first], x.second);
		}
	}
}

// Tests writing data to multiple streams
TEST_F(ElementTest, multiple_streams) {

	// Make the data to write
	entry_data_t data1;
	entry_data_t data2;

	data1["hello"] = "world";
	data2["foo"] = "bar";

	// Write data1 to stream "elementary"
	ASSERT_EQ(element->entryWrite("elementary", data1), ATOM_NO_ERROR);
	// Write data2 to stream "robotics"
	ASSERT_EQ(element->entryWrite("robotics", data2), ATOM_NO_ERROR);

	// Now, do the reads back
	std::vector<Entry> ret1;
	std::vector<std::string> keys1 = {"hello"};
	ASSERT_EQ(element->entryReadN(
		"testing",
		"elementary",
		keys1,
		1,
		ret1), ATOM_NO_ERROR);

	std::vector<Entry> ret2;
	std::vector<std::string> keys2 = {"foo"};
	ASSERT_EQ(element->entryReadN(
		"testing",
		"robotics",
		keys2,
		1,
		ret2), ATOM_NO_ERROR);

	// And make sure everything worked as expected
	ASSERT_EQ(ret1.size(), 1);
	ASSERT_EQ(ret1[0].size(), 1);
	ASSERT_EQ(ret1[0].getKey("hello"), "world");

	ASSERT_EQ(ret2.size(), 1);
	ASSERT_EQ(ret2[0].size(), 1);
	ASSERT_EQ(ret2[0].getKey("foo"), "bar");
}

// Tests getAllStreams
TEST_F(ElementTest, get_all_streams_single_element_all_streams) {

	// Make the data to write
	entry_data_t data;
	data["hello"] = "world";

	// List of streams to write
	std::vector<std::string> streams =
		{"hello", "world", "elementary", "robotics"};
	std::map<std::string, bool> expected_streams;

	// Write the data to all of the "testing" element's streams
	for (auto const &x: streams) {
		ASSERT_EQ(element->entryWrite(x, data), ATOM_NO_ERROR);
		expected_streams[x] = false;
	}

	// Now, we want to get all streams
	std::vector<std::string> stream_list;
	ASSERT_EQ(element->getAllStreams(stream_list, "testing"), ATOM_NO_ERROR);

	// Make sure we got the same number we were expecting
	ASSERT_EQ(stream_list.size(), expected_streams.size());

	// Make sure we found all of the ones we were interested in
	for (auto const &x: stream_list) {
		ASSERT_NE(expected_streams.find(x), expected_streams.end()) << "Received unexpected stream " << x;
		expected_streams[x] = true;
	}

	for (auto const &x : expected_streams) {
		ASSERT_EQ(x.second, true) << "Didn't find stream " << x.first;
	}
}

// Tests getAllStreams
TEST_F(ElementTest, get_all_streams_single_element_all_filtered_valid) {

	// Make the data to write
	entry_data_t data;
	data["hello"] = "world";

	// List of streams to write
	std::vector<std::string> streams =
		{"hello", "world", "elementary", "robotics"};
	std::map<std::string, bool> expected_streams;

	// Write the data to all of the "testing" element's streams
	for (auto const &x: streams) {
		ASSERT_EQ(element->entryWrite(x, data), ATOM_NO_ERROR);
		expected_streams[x] = false;
	}

	// Now, we want to get all streams
	std::vector<std::string> stream_list;
	ASSERT_EQ(element->getAllStreams(stream_list, "testing"), ATOM_NO_ERROR);

	// Make sure we got the same number we were expecting
	ASSERT_EQ(stream_list.size(), expected_streams.size());

	// Make sure we found all of the ones we were interested in
	for (auto const &x: stream_list) {
		ASSERT_NE(expected_streams.find(x), expected_streams.end()) << "Received unexpected stream " << x;
		expected_streams[x] = true;
	}

	for (auto const &x : expected_streams) {
		ASSERT_EQ(x.second, true) << "Didn't find stream " << x.first;
	}
}

// Tests getAllStreams
TEST_F(ElementTest, get_all_streams_single_element_all_filtered_invalid) {

	// Make the data to write
	entry_data_t data;
	data["hello"] = "world";

	// List of streams to write
	std::vector<std::string> streams =
		{"hello", "world", "elementary", "robotics"};
	std::map<std::string, bool> expected_streams;

	// Write the data to all of the "testing" element's streams
	for (auto const &x: streams) {
		ASSERT_EQ(element->entryWrite(x, data), ATOM_NO_ERROR);
		expected_streams[x] = false;
	}

	// Now, we want to get all streams
	std::vector<std::string> stream_list;
	ASSERT_EQ(element->getAllStreams(stream_list, "other"), ATOM_NO_ERROR);

	// Make sure we got the same number we were expecting
	ASSERT_EQ(stream_list.size(), 0);
}

// Tests getAllStreams
TEST_F(ElementTest, get_all_streams_multiple_elements_all_streams) {

	// Make the data to write
	entry_data_t data;
	data["hello"] = "world";

	// List of streams to write
	std::vector<std::string> streams =
		{"hello", "world", "elementary", "robotics"};
	std::map<std::string, std::map<std::string, bool>> expected_streams;

	// Write the data to all of the "testing" element's streams
	for (auto const &x: streams) {
		ASSERT_EQ(element->entryWrite(x, data), ATOM_NO_ERROR);
		expected_streams[element->getName()][x] = false;
	}

	// Make a new element and do the same
	Element new_elem("new_elem");
	for (auto const &x: streams) {
		ASSERT_EQ(new_elem.entryWrite(x, data), ATOM_NO_ERROR);
		expected_streams[new_elem.getName()][x] = false;
	}

	// Now, we want to get all streams
	std::map<std::string, std::vector<std::string>> stream_map;
	ASSERT_EQ(element->getAllStreams(stream_map), ATOM_NO_ERROR);

	// Make sure we got the same number we were expecting
	ASSERT_EQ(stream_map.size(), 2);
	ASSERT_EQ(stream_map["testing"].size(), streams.size());
	ASSERT_EQ(stream_map["new_elem"].size(), streams.size());

	// Make sure we found all of the ones we were interested in
	for (auto const &x: stream_map) {
		for (auto const &key : x.second) {
			ASSERT_NE(expected_streams[x.first].find(key), expected_streams[x.first].end()) << "Received unexpected stream " << key;
			expected_streams[x.first][key] = true;
		}
	}

	for (auto const &x : expected_streams) {
		for (auto const &key : x.second) {
			ASSERT_EQ(key.second, true) << "Didn't find stream " << key.first;
		}
	}
}

bool hello_callback_fn(
	const uint8_t *data,
	size_t data_len,
	ElementResponse *resp,
	void *user_data)
{
	resp->setData("world");
	return true;
}

bool test_err_callback_fn(
	const uint8_t *data,
	size_t data_len,
	ElementResponse *resp,
	void *user_data)
{
	resp->setError(1);
	return true;
}

bool test_err_str_callback_fn(
	const uint8_t *data,
	size_t data_len,
	ElementResponse *resp,
	void *user_data)
{
	resp->setError(2, "this is an error!");
	return true;
}

class MsgpackHello : public CommandMsgpack<std::string, std::string> {
public:
	using CommandMsgpack<std::string, std::string>::CommandMsgpack;

	virtual bool validate() {
		if (*req_data != "hello") {
			return false;
		}
		return true;
	}

	virtual bool run() {
		*res_data = "world";
		return true;
	}
};

class MsgpackNoReq : public CommandMsgpack<std::nullptr_t, std::string> {
public:
	using CommandMsgpack<std::nullptr_t, std::string>::CommandMsgpack;

	virtual bool run() {
		*res_data = "noreq";
		return true;
	}
};

class MsgpackNoRes : public CommandMsgpack<std::string, std::nullptr_t> {
public:
	using CommandMsgpack<std::string, std::nullptr_t>::CommandMsgpack;

	virtual bool validate() {
		if (*req_data != "nores") {
			return false;
		}
		return true;
	}

	virtual bool run() {
		return true;
	}
};

class MsgpackNoReqNoRes : public CommandMsgpack<std::nullptr_t, std::nullptr_t> {
public:
	using CommandMsgpack<std::nullptr_t, std::nullptr_t>::CommandMsgpack;

	virtual bool run() {
		return true;
	}
};


// Thread that creates a command element
void* command_element(void *data)
{
	Element elem("test_cmd");
	elem.addCommand("hello", "hello, world", hello_callback_fn, NULL, 1000);
	elem.addCommand("test_err", "tests an error", test_err_callback_fn, NULL, 1000);
	elem.addCommand("test_err_str", "tests an error string", test_err_str_callback_fn, NULL, 1000);

	// Add a class-based command with msgapck. This will test msgpack
	//	as well as any memory allocations associated with it
	elem.addCommand(
		new MsgpackHello("hello_msgpack", "tests msgpack hello world", 1000));

	// Test variants of no request and no response
	elem.addCommand(
		new MsgpackNoReq("noreq", "Tests msgpack with no request", 1000));
	elem.addCommand(
		new MsgpackNoRes("nores", "Tests msgpack with no response", 1000));
	elem.addCommand(
		new MsgpackNoReqNoRes("noreqnores", "Tests msgpack no request or response", 1000));

	elem.commandLoop(1);
	return NULL;
}

// Tests sendCommand and commandLoop
TEST_F(ElementTest, basic_commands) {
	ElementResponse resp;

	// Start the command thread
	pthread_t cmd_thread;
	ASSERT_EQ(pthread_create(&cmd_thread, NULL, command_element, NULL), 0);

	// Wait until the command element is alive
	while (true) {
		std::vector<std::string> elements;
		ASSERT_EQ(element->getAllElements(elements), ATOM_NO_ERROR);
		if (std::find(elements.begin(), elements.end(), "test_cmd") != elements.end()) {
			break;
		}
		usleep(100000);
	}

	// Send it the command
	ASSERT_EQ(element->sendCommand(resp, "test_cmd", "hello", NULL, 0), ATOM_NO_ERROR);
	ASSERT_EQ(resp.getError(), ATOM_NO_ERROR);
	ASSERT_EQ(resp.isError(), false);
	ASSERT_EQ(resp.getData(), "world");

	// Wait for the command thread to finish
	void *ret;
	ASSERT_EQ(pthread_join(cmd_thread, &ret), 0);
}

// Tests messagepack command
TEST_F(ElementTest, msgpack_command) {
	ElementResponse resp;

	// Start the command thread
	pthread_t cmd_thread;
	ASSERT_EQ(pthread_create(&cmd_thread, NULL, command_element, NULL), 0);

	// Wait until the command element is alive
	while (true) {
		std::vector<std::string> elements;
		ASSERT_EQ(element->getAllElements(elements), ATOM_NO_ERROR);
		if (std::find(elements.begin(), elements.end(), "test_cmd") != elements.end()) {
			break;
		}
		usleep(100000);
	}

	std::string req = "hello";
	std::string res;
	enum atom_error_t err = element->sendCommand<std::string, std::string>(resp, "test_cmd", "hello_msgpack", req, res);
	ASSERT_EQ(err, ATOM_NO_ERROR);
	ASSERT_EQ(res, "world");

	// Wait for the command thread to finish
	void *ret;
	ASSERT_EQ(pthread_join(cmd_thread, &ret), 0);
}

// Tests no request
TEST_F(ElementTest, msgpack_noreq) {
	ElementResponse resp;

	// Start the command thread
	pthread_t cmd_thread;
	ASSERT_EQ(pthread_create(&cmd_thread, NULL, command_element, NULL), 0);

	// Wait until the command element is alive
	while (true) {
		std::vector<std::string> elements;
		ASSERT_EQ(element->getAllElements(elements), ATOM_NO_ERROR);
		if (std::find(elements.begin(), elements.end(), "test_cmd") != elements.end()) {
			break;
		}
		usleep(100000);
	}

	std::string res;
	enum atom_error_t err = element->sendCommandNoReq<std::string>(resp, "test_cmd", "noreq", res);
	ASSERT_EQ(err, ATOM_NO_ERROR);
	ASSERT_EQ(res, "noreq");

	// Wait for the command thread to finish
	void *ret;
	ASSERT_EQ(pthread_join(cmd_thread, &ret), 0);
}

// Tests no response
TEST_F(ElementTest, msgpack_nores) {
	ElementResponse resp;

	// Start the command thread
	pthread_t cmd_thread;
	ASSERT_EQ(pthread_create(&cmd_thread, NULL, command_element, NULL), 0);

	// Wait until the command element is alive
	while (true) {
		std::vector<std::string> elements;
		ASSERT_EQ(element->getAllElements(elements), ATOM_NO_ERROR);
		if (std::find(elements.begin(), elements.end(), "test_cmd") != elements.end()) {
			break;
		}
		usleep(100000);
	}

	std::string req = "nores";
	enum atom_error_t err = element->sendCommandNoRes<std::string>(resp, "test_cmd", "nores", req);
	ASSERT_EQ(err, ATOM_NO_ERROR);

	// Wait for the command thread to finish
	void *ret;
	ASSERT_EQ(pthread_join(cmd_thread, &ret), 0);
}

// Tests no request and no response
TEST_F(ElementTest, msgpack_noreqnores) {
	ElementResponse resp;

	// Start the command thread
	pthread_t cmd_thread;
	ASSERT_EQ(pthread_create(&cmd_thread, NULL, command_element, NULL), 0);

	// Wait until the command element is alive
	while (true) {
		std::vector<std::string> elements;
		ASSERT_EQ(element->getAllElements(elements), ATOM_NO_ERROR);
		if (std::find(elements.begin(), elements.end(), "test_cmd") != elements.end()) {
			break;
		}
		usleep(100000);
	}

	enum atom_error_t err = element->sendCommand(resp, "test_cmd", "noreqnores", NULL, 0);
	ASSERT_EQ(err, ATOM_NO_ERROR);

	// Wait for the command thread to finish
	void *ret;
	ASSERT_EQ(pthread_join(cmd_thread, &ret), 0);
}



// Tests command with an error response
TEST_F(ElementTest, err_command) {
	ElementResponse resp;

	// Start the command thread
	pthread_t cmd_thread;
	ASSERT_EQ(pthread_create(&cmd_thread, NULL, command_element, NULL), 0);

	// Wait until the command element is alive
	while (true) {
		std::vector<std::string> elements;
		ASSERT_EQ(element->getAllElements(elements), ATOM_NO_ERROR);
		if (std::find(elements.begin(), elements.end(), "test_cmd") != elements.end()) {
			break;
		}
		usleep(100000);
	}

	// Send it the command
	ASSERT_EQ(element->sendCommand(resp, "test_cmd", "test_err", NULL, 0), ATOM_USER_ERRORS_BEGIN + 1);
	ASSERT_EQ(resp.isError(), true);
	ASSERT_EQ(resp.getError(), ATOM_USER_ERRORS_BEGIN + 1);

	// Wait for the command thread to finish
	void *ret;
	ASSERT_EQ(pthread_join(cmd_thread, &ret), 0);
}

// Tests command with an error response
TEST_F(ElementTest, err_string) {
	ElementResponse resp;

	// Start the command thread
	pthread_t cmd_thread;
	ASSERT_EQ(pthread_create(&cmd_thread, NULL, command_element, NULL), 0);

	// Wait until the command element is alive
	while (true) {
		std::vector<std::string> elements;
		ASSERT_EQ(element->getAllElements(elements), ATOM_NO_ERROR);
		if (std::find(elements.begin(), elements.end(), "test_cmd") != elements.end()) {
			break;
		}
		usleep(100000);
	}

	// Send it the command
	ASSERT_EQ(element->sendCommand(resp, "test_cmd", "test_err_str", NULL, 0), ATOM_USER_ERRORS_BEGIN + 2);
	ASSERT_EQ(resp.isError(), true);
	ASSERT_EQ(resp.getError(), ATOM_USER_ERRORS_BEGIN + 2);
	ASSERT_EQ(resp.getErrorStr(), "this is an error!");

	// Wait for the command thread to finish
	void *ret;
	ASSERT_EQ(pthread_join(cmd_thread, &ret), 0);
}

// Tests sending a log. We'll read it back with a redis XREVRANGE command
//	 on the log stream
TEST_F(ElementTest, basic_log) {
	element->log(LOG_DEBUG, "testing: 1, 2, 3");
}

// Tests sending a variadic log
TEST_F(ElementTest, variadic_log) {
	for (int i = LOG_EMERG; i <= LOG_DEBUG; ++i) {
		element->log(i, "testing: level %d", i);
	}
}

// Tests to make sure only the proper log levels are allower
TEST_F(ElementTest, invalid_logs) {
	ASSERT_THROW(element->log(LOG_EMERG - 1, "testing: 1, 2, 3"), std::runtime_error);
	ASSERT_THROW(element->log(-1, "testing: 1, 2, 3"), std::runtime_error);
	ASSERT_THROW(element->log(LOG_DEBUG + 1, "testing: 1, 2, 3"), std::runtime_error);
	ASSERT_THROW(element->log(8, "testing: 1, 2, 3"), std::runtime_error);
}

// Tests readSince API
TEST_F(ElementTest, readSinceLog) {
	char hostname[HOST_NAME_MAX + 1];

	// Get the hostname
	ASSERT_EQ(gethostname(hostname, sizeof(hostname)), 0);

	for (int i = 0; i < 10; ++i) {
		element->log(0, "%d", i);
	}

	// Do the read back
	std::vector<Entry> ret;
	std::vector<std::string> keys = {"level", "element", "msg", "host"};
	ASSERT_EQ(element->entryReadSince(
		"",
		"log",
		keys,
		2,
		ret,
		ENTRY_READ_SINCE_BEGIN_WITH_OLDEST_ID), ATOM_NO_ERROR);

	// Make sure we got 2 pieces of data
	ASSERT_EQ(ret.size(), 2);

	// For each piece of data make sure there's 4 keys
	for (int i = 0; i < 2; ++i) {
		Entry &x = ret.at(i);

		// Make sure that we have the right number of keys
		ASSERT_EQ(x.size(), keys.size());

		// Make sure that the keys are correct
		ASSERT_EQ(x.getKey("level"), "0");
		ASSERT_EQ(x.getKey("host"), std::string(hostname));
		ASSERT_EQ(x.getKey("element"), "testing");
		ASSERT_EQ(x.getKey("msg"), std::to_string(i));
	}

	// Clear the response and start again
	std::string last = std::string(ret[1].getID());
	ret.clear();
	ASSERT_EQ(element->entryReadSince(
		"",
		"log",
		keys,
		3,
		ret,
		last), ATOM_NO_ERROR);

	// Make sure we got 3 pieces of data
	ASSERT_EQ(ret.size(), 3);

	// For each piece of data make sure there's 4 keys
	for (int i = 0; i < 3; ++i) {
		Entry &x = ret.at(i);

		// Make sure that we have the right number of keys
		ASSERT_EQ(x.size(), keys.size());

		// Make sure that the keys are correct
		ASSERT_EQ(x.getKey("level"), "0");
		ASSERT_EQ(x.getKey("host"), std::string(hostname));
		ASSERT_EQ(x.getKey("element"), "testing");
		ASSERT_EQ(x.getKey("msg"), std::to_string(2 + i));
	}

	// Do the final chunk
	last = std::string(ret[2].getID());
	ret.clear();
	ASSERT_EQ(element->entryReadSince(
		"",
		"log",
		keys,
		5,
		ret,
		last), ATOM_NO_ERROR);

	// Make sure we got 5 pieces of data
	ASSERT_EQ(ret.size(), 5);

	// For each piece of data make sure there's 4 keys
	for (int i = 0; i < 5; ++i) {
		Entry &x = ret.at(i);

		// Make sure that we have the right number of keys
		ASSERT_EQ(x.size(), keys.size());

		// Make sure that the keys are correct
		ASSERT_EQ(x.getKey("level"), "0");
		ASSERT_EQ(x.getKey("host"), std::string(hostname));
		ASSERT_EQ(x.getKey("element"), "testing");
		ASSERT_EQ(x.getKey("msg"), std::to_string(5 + i));
	}
}

// Tests readSince API with element
TEST_F(ElementTest, readSinceElement) {

	// Make the data to write
	entry_data_t data;

	// Write 10 pieces of data to the element stream
	for (int i = 0; i < 10; ++i) {
		data["world"] = std::to_string(i);

		ASSERT_EQ(element->entryWrite("hello", data), ATOM_NO_ERROR);
	}

	// Do the read back
	std::vector<Entry> ret;
	std::vector<std::string> keys = {"world"};
	ASSERT_EQ(element->entryReadSince(
		"testing",
		"hello",
		keys,
		4,
		ret,
		ENTRY_READ_SINCE_BEGIN_WITH_OLDEST_ID), ATOM_NO_ERROR);

	// Make sure we got 2 pieces of data
	ASSERT_EQ(ret.size(), 4);

	// For each piece of data make sure there's 4 keys
	for (int i = 0; i < 4; ++i) {
		Entry &x = ret.at(i);

		// Make sure that we have the right number of keys
		ASSERT_EQ(x.size(), keys.size());

		// Make sure that the keys are correct
		ASSERT_EQ(x.getKey("world"), std::to_string(i));
	}

	// Clear the response and start again
	std::string last = std::string(ret[3].getID());
	ret.clear();
	ASSERT_EQ(element->entryReadSince(
		"testing",
		"hello",
		keys,
		1,
		ret,
		last), ATOM_NO_ERROR);

	// Make sure we got 3 pieces of data
	ASSERT_EQ(ret.size(), 1);

	// For each piece of data make sure there's 4 keys
	for (int i = 0; i < 1; ++i) {
		Entry &x = ret.at(i);

		// Make sure that we have the right number of keys
		ASSERT_EQ(x.size(), keys.size());

		// Make sure that the keys are correct
		ASSERT_EQ(x.getKey("world"), std::to_string(4 + i));
	}

	// Do the final chunk
	last = std::string(ret[0].getID());
	ret.clear();
	ASSERT_EQ(element->entryReadSince(
		"testing",
		"hello",
		keys,
		5,
		ret,
		last), ATOM_NO_ERROR);

	// Make sure we got 5 pieces of data
	ASSERT_EQ(ret.size(), 5);

	// For each piece of data make sure there's 4 keys
	for (int i = 0; i < 5; ++i) {
		Entry &x = ret.at(i);

		// Make sure that we have the right number of keys
		ASSERT_EQ(x.size(), keys.size());

		// Make sure that the keys are correct
		ASSERT_EQ(x.getKey("world"), std::to_string(5 + i));
	}
}

bool readerHandler(
	Entry &e,
	void *user_data)
{
	std::cout << "In reader handler" << std::endl;
	int *i = (int *)user_data;

    std::cout<<"user_data: " << *i << " e.size: " << e.size()<<std::endl;

	if ((e.size() == 1) && (e.getKey("foo") == "bar")) {
        std::cout<<"found foo"<<std::endl;
		*i += 1;
	}
/*     else if ((e.size() == 1) && (e.getKey("foo2") == "bar2"))
    {
        std::cout<<"found foo2"<<std::endl;
        *i += 1;
    } */
    
	return true;
}

// Thread that creates a command element
void reader_element(int &i)
{
	Element elem("reader");
	ElementReadMap m;
	m.addHandler("testing", "reader", { "foo" }, readerHandler, &i); //with user data
//    m.addHandler("testing", "reader", { "foo2" }, readerHandler); //without user data
	elem.entryReadLoop(m, 3);
}

// Tests readLoop API -- possible race condition! #TODO: fix it.
 TEST_F(ElementTest, readLoop) {

 	// Make the reader thread
 	int count = 0;
 	std::thread reader(reader_element, std::ref(count));
    Element element1("one");
	Element element2("two");

 	// Wait until the reader element is alive
 	while (true) {
 		std::vector<std::string> elements;
 		ASSERT_EQ(element->getAllElements(elements), ATOM_NO_ERROR);
 		if (std::find(elements.begin(), elements.end(), "reader") != elements.end()) {
            std::cout<<"Found reader"<<std::endl;
            
            if(std::find(elements.begin(), elements.end(), "one") != elements.end()){
                std::cout<<"Found one!"<<std::endl;
                
                if(std::find(elements.begin(), elements.end(), "two") != elements.end()){
                    std::cout<<"Found two!" <<std::endl;
                    break;
                } else{ std::cout<<"Didn't find two."<<std::endl;}
                break;

            } else{ std::cout<<"Didn't find one."<<std::endl;}
            break;
 		}
        break;
 		usleep(100000);
 	}
    std::cout<<"out of loop"<<std::endl;

 	// Publish "foo" : "bar" on our "reader" stream
 	entry_data_t data;
 	data["foo"] = "bar";
    //data["foo2"] = "bar2";
 	for (int i = 0; i < 3; ++i) {
 		ASSERT_EQ(element->entryWrite("reader", data), ATOM_NO_ERROR);
 	}

 	// Wait for the reader thread to finish up
 	reader.join();

 	ASSERT_EQ(count, 3);
 }

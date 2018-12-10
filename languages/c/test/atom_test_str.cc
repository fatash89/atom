////////////////////////////////////////////////////////////////////////////////
//
//  @file atom_test.cc
//
//  @brief Unit tests for atom-level library functionality
//
//  @copy 2018 Elementary Robotics. All rights reserved.
//
////////////////////////////////////////////////////////////////////////////////
#include <gtest/gtest.h>
#include <string.h>
#include "atom.h"

//
// Tests for valid element names
//
class AtomStreamStrValidTest :
    public testing::TestWithParam<const char*>
{

protected:
	void check_response_stream(
		const char *name,
		const char *test_result)
	{
		std::string expected_name = "response:" + std::string(name);
		EXPECT_EQ(std::string(test_result), expected_name);
	}

	void check_command_stream(
		const char *name,
		const char *test_result)
	{
		std::string expected_name = "command:" + std::string(name);
		EXPECT_EQ(std::string(test_result), expected_name);
	}

	void check_data_stream(
		const char *name,
		const char *data,
		const char *test_result)
	{
		std::string expected_name = "stream:" + std::string(name) + ":" + std::string(data);
		EXPECT_EQ(std::string(test_result), expected_name);
	}
};

// Test creation of response stream with static buffer
TEST_P(AtomStreamStrValidTest, response_static_alloc)
{
	char buffer[ATOM_NAME_MAXLEN];
	EXPECT_EQ(atom_get_response_stream_str(GetParam(), buffer), buffer);
	check_response_stream(GetParam(), buffer);
}

// Test creation of command stream with static buffer
TEST_P(AtomStreamStrValidTest, command_static_alloc)
{
	char buffer[ATOM_NAME_MAXLEN];
	EXPECT_EQ(atom_get_command_stream_str(GetParam(), buffer), buffer);
	check_command_stream(GetParam(), buffer);
}

// Test creation of data stream with static buffer
TEST_P(AtomStreamStrValidTest, data_static_alloc)
{
	char buffer[ATOM_NAME_MAXLEN];
	EXPECT_EQ(atom_get_data_stream_str(GetParam(), "some_data", buffer), buffer);
	check_data_stream(GetParam(), "some_data", buffer);
}

// Test creation of response stream with dynamic buffer
TEST_P(AtomStreamStrValidTest, response_dynamic_alloc)
{
	char *stream;
	stream = atom_get_response_stream_str(GetParam(), NULL);
	EXPECT_NE(stream, (char*)NULL);
	check_response_stream(GetParam(), stream);
}

// Test creation of command stream with dynamic buffer
TEST_P(AtomStreamStrValidTest, command_dynamic_alloc)
{
	char *stream;
	stream = atom_get_command_stream_str(GetParam(), NULL);
	EXPECT_NE(stream, (char*)NULL);
	check_command_stream(GetParam(), stream);
}

// Test creation of data stream with dynamic buffer
TEST_P(AtomStreamStrValidTest, data_dynamic_alloc)
{
	char *stream;
	stream = atom_get_data_stream_str(GetParam(), "some_data", NULL);
	EXPECT_NE(stream, (char*)NULL);
	check_data_stream(GetParam(), "some_data", stream);
}

// Actually test the case
const char *valid_element_names[] =
{
	"hello",
	"world",
	"a",
	"b",
	"c",
	"0",
	"this_is_a_really_long_name",
	"this_is_the_max_length_name"
};

INSTANTIATE_TEST_CASE_P(
	valid_stream_names,
	AtomStreamStrValidTest,
	::testing::ValuesIn(valid_element_names));

//
// Tests for invalid element names
//
class AtomStreamStrInvalidTest :
    public testing::TestWithParam<const char*>
{

};

// Test creation of response stream with static buffer
TEST_P(AtomStreamStrInvalidTest, response_static_alloc)
{
	char buffer[ATOM_NAME_MAXLEN];
	EXPECT_EQ(atom_get_response_stream_str(GetParam(), buffer), (char*)NULL);
}

// Test creation of command stream with static buffer
TEST_P(AtomStreamStrInvalidTest, command_static_alloc)
{
	char buffer[ATOM_NAME_MAXLEN];
	EXPECT_EQ(atom_get_command_stream_str(GetParam(), buffer), (char*)NULL);
}

// Test creation of data stream with static buffer
TEST_P(AtomStreamStrInvalidTest, data_static_alloc)
{
	char buffer[ATOM_NAME_MAXLEN];
	EXPECT_EQ(atom_get_data_stream_str(GetParam(), "some_data", buffer), (char*)NULL);
}

// Test creation of response stream with dynamic buffer
TEST_P(AtomStreamStrInvalidTest, response_dynamic_alloc)
{
	char *stream;
	stream = atom_get_response_stream_str(GetParam(), NULL);
	EXPECT_EQ(stream, (char*)NULL);
}

// Test creation of command stream with dynamic buffer
TEST_P(AtomStreamStrInvalidTest, command_dynamic_alloc)
{
	char *stream;
	stream = atom_get_command_stream_str(GetParam(), NULL);
	EXPECT_EQ(stream, (char*)NULL);
}

// Test creation of data stream with dynamic buffer
TEST_P(AtomStreamStrInvalidTest, data_dynamic_alloc)
{
	char *stream;
	stream = atom_get_data_stream_str(GetParam(), "some_data", NULL);
	EXPECT_EQ(stream, (char*)NULL);
}

// Actually test the case
const char *invalid_element_names[] =
{
	"",
	"\0",
};

INSTANTIATE_TEST_CASE_P(
	invalid_stream_names,
	AtomStreamStrInvalidTest,
	::testing::ValuesIn(invalid_element_names));

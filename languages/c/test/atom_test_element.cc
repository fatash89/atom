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
#include "atom.h"
#include "redis.h"
#include "element.h"

//
// Tests for valid element names
//
class AtomElementTest : public testing::Test
{

protected:
	redisContext *ctx;
	struct element *elem;

	virtual void SetUp() {
		ctx = redisConnectUnix("/shared/redis.sock");
		elem = element_init(ctx, "test_element");
		ASSERT_NE(elem, (struct element *)NULL);
	};

	virtual void TearDown() {
		element_cleanup(ctx, elem);
		redisFree(ctx);
		ctx = NULL;
		elem = NULL;
	};
};

// Tests the SetUp and TearDown functions which
//	create an element and then clean it up. Not testing much,
//	but enough that we can connect to the redis server and handle
//	the XADDs on the command/response streams and the subsequent DELs
//	on those streams when we clean up
TEST_F(AtomElementTest, setup_teardown) {
	ASSERT_EQ(1, 1);
}

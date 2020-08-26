////////////////////////////////////////////////////////////////////////////////
//
//  @file test_Serialization.cc
//
//  @unit tests for Serialization.cc
//
//  @copy 2020 Elementary Robotics. All rights reserved.
//
////////////////////////////////////////////////////////////////////////////////
#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <iostream>

#include <boost/asio.hpp>
#include <bredis.hpp>

#include "Serialization.h"
#include "Redis.h"

class SerializationTest : public testing::Test {

public:

    // unix socket types
    using socket_t = boost::asio::local::stream_protocol::socket;
    using endpoint_t = boost::asio::local::stream_protocol::endpoint;

    // bredis communication types
    using Buffer = boost::asio::streambuf;
    using Iterator = typename bredis::to_iterator<Buffer>::iterator_t;
    using Policy = bredis::parsing_policy::keep_result;

    SerializationTest() :  serialization(), redis(io_con, "/shared/redis.sock", 20, 500){

    }

	virtual void SetUp() {

        //connect to redis
        atom::error err;
        redis.connect(err);
        if(err){
            std::cout<<"error: " << err.message()<<std::endl;
        }


	};

	virtual void TearDown() {
	};

    ~SerializationTest(){
    }
    
    std::string stream_name = "Serialization_test";
    std::string id;
    boost::asio::io_context io_con;
    atom::Serialization serialization;
    atom::Redis<socket_t, endpoint_t, Buffer, Iterator, Policy> redis;
};


TEST_F(SerializationTest, serialize_msgpack){

    //make test data
    using my_type = msgpack::type::tuple<int, bool, std::string>;
    my_type test_data(100, false, "Hello World!");

    std::stringstream buff;
    serialization.serialize<my_type, std::stringstream>(test_data, buff);

    EXPECT_THAT(buff.str(), ::testing::HasSubstr("d\xC2\xACHello World!"));
}


TEST_F(SerializationTest, deserialize_msgpack){

    //make test data
    using my_type = msgpack::type::tuple<int, bool, std::string>;
    my_type test_data(100, false, "Hello World!");

    //serialize here
    std::stringstream buff;
    serialization.serialize<my_type, std::stringstream>(test_data, buff);
    EXPECT_THAT(buff.str(), ::testing::HasSubstr("d\xC2\xACHello World!"));

    //send serialized data via redis    
    atom::error err;
    atom::redis_reply<boost::asio::streambuf> reply = redis.xadd(stream_name, "test_msgpack", buff, err);
    if(err){
        FAIL();
    }

    //grab the id
    auto out1 = boost::get<atom::reply_type::flat_response>(reply.parsed_reply);
    id = std::string(*out1.first.get(), out1.second);

    redis.release_rx_buffer(reply); 

    //read serialized data via redis    
    err.clear();
    atom::redis_reply<boost::asio::streambuf> reply_ = redis.xrange(stream_name, id, "+", "1", err);
    if(err){
        FAIL();
    }
    auto out2 = boost::get<atom::reply_type::entry_response>(reply_.parsed_reply);

    //test the deserialization:
    std::stringstream serialized_msgpack(*out2[id][1].first.get());
    my_type deserialized = serialization.deserialize<my_type, std::stringstream>(serialized_msgpack);
    
    redis.release_rx_buffer(reply_); 
    //expect that data read back from redis is equivalent to the data we sent
    EXPECT_EQ(deserialized, test_data);
}






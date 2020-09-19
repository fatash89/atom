////////////////////////////////////////////////////////////////////////////////
//
//  @file test_ClientElement.cc
//
//  @unit tests for ClientElement.cc
//
//  @copy 2020 Elementary Robotics. All rights reserved.
//
////////////////////////////////////////////////////////////////////////////////
#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <iostream>
#include <thread>


#include "Client_Element.h"
#include "Serialization.h"

using my_type = msgpack::type::tuple<int, bool, std::string>;


class ClientElementTest : public testing::Test {

public:

    ClientElementTest() : 
        ip("172.20.0.2"),
        client_elem(iocon, 100, 1000, ip, ser, 10, 1000, 5, 5, std::cout, "ClientElement"),
        redis(iocon, "/shared/redis.sock", 5, 1000) {
    }

	virtual void SetUp() {
        atom::error err;
        redis.connect(err);
	};

	virtual void TearDown() {

	};

    ~ClientElementTest(){
    }
    
    boost::asio::io_context iocon;
    std::string ip;
    int num_buffers = 20;
    int buffer_timeout = 1;
    atom::Serialization ser;
    atom::Client_Element<atom::ConnectionPool::UNIX_Redis, atom::ConnectionPool::Buffer_Type> client_elem;
    atom::ConnectionPool::UNIX_Redis redis;

};

TEST_F(ClientElementTest, init_ClientElement){

}

TEST_F(ClientElementTest, entry_read_n_msgpack){

    std::string stream_name = "stream:MyElem:client_stream";
    atom::error err;

    //serialize and write an entry like server element would
    std::vector<std::string> my_data = {"hello", "world", "ice_cream", "chocolate"};
    std::stringstream ss;
    msgpack::pack(ss, my_data[1]);
    my_data[1] = ss.str();
    std::stringstream ss2;
    msgpack::pack(ss2, my_data[3]);
    my_data[3] = ss2.str();

    atom::redis_reply<atom::ConnectionPool::Buffer_Type> reply1 = redis.xadd(stream_name,"msgpack", my_data, err);
    atom::redis_reply<atom::ConnectionPool::Buffer_Type> reply2 = redis.xrevrange(stream_name, "+", "-", "2", err);

    //read the entry
    auto entries = client_elem.entry_read_n<msgpack::type::variant>("MyElem", "client_stream", 1, err, "msgpack", false);

    //verify keys
    EXPECT_THAT(entries[0].data[0].key(), my_data[0]);
    EXPECT_THAT(entries[0].data[2].key(), my_data[2]);

    //verify values
    auto deser_data = entries[0].data[1].value();
    msgpack::type::variant  expected("world");
    msgpack::type::variant received = *deser_data.get();
    EXPECT_THAT(received, expected);

    auto deser_data1 = entries[0].data[3].value();
    msgpack::type::variant  expected1("chocolate");
    msgpack::type::variant received1 = *deser_data1.get();
    EXPECT_THAT(received1, expected1);

    //cleanup
    reply1.cleanup();
    reply2.cleanup();

}

TEST_F(ClientElementTest, entry_read_n_none){

    std::string stream_name = "stream:MyElem:client_stream";
    atom::error err;

    //serialize and write an entry like server element would
    std::vector<std::string> my_data = {"hello", "world", "ice_cream", "chocolate"};
    atom::redis_reply<atom::ConnectionPool::Buffer_Type> reply1 = redis.xadd(stream_name,"none", my_data, err);
    atom::redis_reply<atom::ConnectionPool::Buffer_Type> reply2 = redis.xrevrange(stream_name, "+", "-", "1", err);

    /* auto data1 = reply1.flat_response();
    auto id = atom::reply_type::to_string(data1);
    auto data2 = reply2.entry_response(); */
    //atom::entry_type::object<const char *>(data2.at(id)[0].first, data2.at(id)[0].second);

    //read the entry - TODO: fix const char * case.
    auto entries = client_elem.entry_read_n</* const */ char *>("MyElem", "client_stream", 1, err, "none", false);

     //verify keys
    EXPECT_THAT(entries[0].data[0].key(), my_data[0]);
    EXPECT_THAT(entries[0].data[2].key(), my_data[2]);

    /* //verify values
    auto received = entries[0].data[1].value();
    std::string expected = "world";
    EXPECT_THAT(*received.get(), expected);

    auto received1 = entries[0].data[3].value();
    std::string expected1 = "chocolate";
    EXPECT_THAT(*received1.get(), expected1); */

    //cleanup
    reply1.cleanup();
    reply2.cleanup();

}

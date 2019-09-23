#work in progress, began translating from c library tests
using LibAtom, Test

struct AtomRedisTest
	keys_created::Vector{String}
	ctx::redisContext
	atom_list::atom_list_node
end

function SetUp()
	ctx = redisConnectUnix("/shared/redis.sock");
	ASSERT_NE(ctx, (void*)NULL);
	# Initialize the atom_list to an invalid value. This ensures
	#	that the list creation takes care of it
	atom_list = (struct atom_list_node*)0xDEADBEEF;
end

function TearDown()
	redisReply *reply;

	for (auto const& i: keys_created) {
		std::string del_str = "DEL " + i;
		reply = (redisReply *)redisCommand(ctx, del_str.c_str());
		ASSERT_NE(reply, (redisReply*)NULL) << "Redis doesn't seem to be working...";
		EXPECT_NE(reply->type, REDIS_REPLY_ERROR);
	end
	redisFree(ctx);
	atom_list_free(atom_list);
end

# Adds a key to redis
function add_stream(std::string name)
	redisReply *reply;

	std::string command_str = "XADD " + name + " MAXLEN ~ 1024 * foo bar";
	reply = (redisReply *)redisCommand(ctx, command_str.c_str());
	ASSERT_NE(reply, (redisReply *)NULL) << "Redis doesn't seem to be working...";
	ASSERT_NE(reply->type, REDIS_REPLY_ERROR) << "Failed to XADD key";
	keys_created.push_back(name);
end

# Adds an element's streams to the system
function add_element(std::string name)
	add_stream("command:" + name);
	add_stream("response:" + name);
end

# Makes a data stream name from a name and data
function get_data_stream(std::string name, std::string data)
	return name + ":" + data;
end

# Adds a data stream to the system
function add_data_stream(std::string name, std::string data)
	add_stream("stream:" + get_data_stream(name, data));
end

# Checks a linked list coming from atom to make sure
#	all of the elements appear in the right order
function check_list(struct atom_list_node *list, std::vector<std::string> expected)
	for (auto const& i: expected) {
		ASSERT_NE(list, (struct atom_list_node *)NULL) << "Extra items in expected!";
		EXPECT_EQ(strcmp(list->name, i.c_str()), 0) << "Name: " << list->name << ", Expected: " << i;
		list = list->next;
	end
	# This check makes sure there aren't more items in the list
	EXPECT_EQ(list, (struct atom_list_node *)NULL) << "Extra items in list!";
end

# Tests adding a single element and then getting all of the
#	elements
TEST_F(AtomRedisTest, single_element) {
	add_element("test_element");
	EXPECT_EQ(atom_get_all_elements(ctx, &atom_list), ATOM_NO_ERROR);
	check_list(atom_list, std::vector<std::string>{"test_element"});
end

# Tests no elements
TEST_F(AtomRedisTest, no_elements) {
	EXPECT_EQ(atom_get_all_elements(ctx, &atom_list), ATOM_NO_ERROR);
	EXPECT_EQ(atom_list, (struct atom_list_node*)NULL);
end

# Tests adding a single element multiple times. We should only
#	get one copy in the list
TEST_F(AtomRedisTest, repeated_single_element) {
	add_element("repeated_test");
	add_element("repeated_test");
	add_element("repeated_test");
	add_element("repeated_test");
	EXPECT_EQ(atom_get_all_elements(ctx, &atom_list), ATOM_NO_ERROR);
	check_list(atom_list, std::vector<std::string>{"repeated_test"});
end

# Tests multiple elements
TEST_F(AtomRedisTest, multiple_elements_in_order) {
	add_element("a");
	add_element("b");
	add_element("c");
	add_element("d");
	EXPECT_EQ(atom_get_all_elements(ctx, &atom_list), ATOM_NO_ERROR);
	check_list(atom_list, std::vector<std::string>{"a", "b", "c", "d"});
end

# Tests multiple elements in reverse order
TEST_F(AtomRedisTest, multiple_elements_reverse_order) {
	add_element("d");
	add_element("c");
	add_element("b");
	add_element("a");
	EXPECT_EQ(atom_get_all_elements(ctx, &atom_list), ATOM_NO_ERROR);
	check_list(atom_list, std::vector<std::string>{"a", "b", "c", "d"});
end

# Tests multiple elements in mixed order
TEST_F(AtomRedisTest, multiple_elements_mixed_order) {
	add_element("c");
	add_element("a");
	add_element("d");
	add_element("b");
	EXPECT_EQ(atom_get_all_elements(ctx, &atom_list), ATOM_NO_ERROR);
	check_list(atom_list, std::vector<std::string>{"a", "b", "c", "d"});
end

# Tests no streams with a filter
TEST_F(AtomRedisTest, no_streams_filter) {
	EXPECT_EQ(atom_get_all_data_streams(ctx, "filter", &atom_list), ATOM_NO_ERROR);
	EXPECT_EQ(atom_list, (struct atom_list_node*)NULL);
end

# Tests no streams
TEST_F(AtomRedisTest, no_streams_no_filter) {
	EXPECT_EQ(atom_get_all_data_streams(ctx, NULL, &atom_list), ATOM_NO_ERROR);
	EXPECT_EQ(atom_list, (struct atom_list_node*)NULL);
end

# Tests a single data stream
TEST_F(AtomRedisTest, single_stream_no_filter) {
	add_data_stream("test_elem", "some_data");
	EXPECT_EQ(atom_get_all_data_streams(ctx, NULL, &atom_list), ATOM_NO_ERROR);
	check_list(atom_list, std::vector<std::string>{
		get_data_stream("test_elem", "some_data"),
		});
end

# Tests multiple data streams for the same element without an element filter in order
TEST_F(AtomRedisTest, multiple_streams_same_element_no_filter_in_order) {
	add_data_stream("test_elem", "cool_data");
	add_data_stream("test_elem", "other_data");
	add_data_stream("test_elem", "some_data");
	EXPECT_EQ(atom_get_all_data_streams(ctx, NULL, &atom_list), ATOM_NO_ERROR);
	check_list(atom_list, std::vector<std::string>{
		get_data_stream("test_elem", "cool_data"),
		get_data_stream("test_elem", "other_data"),
		get_data_stream("test_elem", "some_data"),
	});
end

# Tests multiple data streams for multiple elements without an element filter
TEST_F(AtomRedisTest, multiple_streams_multiple_elements) {
	add_data_stream("test_elem", "cool_data");
	add_data_stream("test_elem", "other_data");
	add_data_stream("test_elem", "some_data");
	add_data_stream("foo_elem", "hello");
	add_data_stream("bar_elem", "world");
	add_data_stream("baz_elem", "testing");
	EXPECT_EQ(atom_get_all_data_streams(ctx, NULL, &atom_list), ATOM_NO_ERROR);
	check_list(atom_list, std::vector<std::string>{
		get_data_stream("bar_elem", "world"),
		get_data_stream("baz_elem", "testing"),
		get_data_stream("foo_elem", "hello"),
		get_data_stream("test_elem", "cool_data"),
		get_data_stream("test_elem", "other_data"),
		get_data_stream("test_elem", "some_data"),
	});
end

# Tests multiple data streams
TEST_F(AtomRedisTest, multiple_streams_same_element_no_filter_reverse_order) {
	add_data_stream("test_elem", "some_data");
	add_data_stream("test_elem", "other_data");
	add_data_stream("test_elem", "cool_data");
	EXPECT_EQ(atom_get_all_data_streams(ctx, NULL, &atom_list), ATOM_NO_ERROR);
	check_list(atom_list, std::vector<std::string>{
		get_data_stream("test_elem", "cool_data"),
		get_data_stream("test_elem", "other_data"),
		get_data_stream("test_elem", "some_data"),
	});
end

# Tests multiple data streams for the same element with an element filter in order
TEST_F(AtomRedisTest, multiple_streams_same_element_valid_filter_in_order) {
	add_data_stream("test_elem", "cool_data");
	add_data_stream("test_elem", "other_data");
	add_data_stream("test_elem", "some_data");
	EXPECT_EQ(atom_get_all_data_streams(ctx, "test_elem", &atom_list), ATOM_NO_ERROR);
	check_list(atom_list, std::vector<std::string>{
		"cool_data",
		"other_data",
		"some_data"
	});
end

# Tests multiple data streams for the same element with an element filter in order
TEST_F(AtomRedisTest, multiple_streams_multiple_elements_with_filter) {
	add_data_stream("test_elem", "cool_data");
	add_data_stream("test_elem", "other_data");
	add_data_stream("test_elem", "some_data");
	add_data_stream("foo_elem", "hello");
	add_data_stream("bar_elem", "world");
	add_data_stream("baz_elem", "testing");
	EXPECT_EQ(atom_get_all_data_streams(ctx, "foo_elem", &atom_list), ATOM_NO_ERROR);
	check_list(atom_list, std::vector<std::string>{
		"hello"
	});
end

#include <stdio.h>
#include <pthread.h>
#include <stdbool.h>
#include <string.h>
#include <unistd.h>
#include "redis.h"
#include "skills.h"
#include "client.h"
#include "skill.h"
#include <gtest/gtest.h>


#define N_TESTS 10
#define STREAM1_NAME "STREAM1"
#define STREAM2_NAME "stream2"

#define STREAM1_KEY1 "hello1"
#define STREAM1_DATA1 "world1"
#define STREAM1_KEY2 "foo1"
#define STREAM1_DATA2 "bar1"

#define STREAM2_KEY1 "hello2"
#define STREAM2_DATA1 "world2"
#define STREAM2_KEY2 "foo2"
#define STREAM2_DATA2 "bar2"

int stream1_count = 0;
int stream2_count = 0;
int stream1_xrevrange_count = 0;
int stream2_xrevrange_count = 0;

// stream1 callback
bool stream1_cb(const char *id, const struct redisReply *reply, void *data) {
	++stream1_count;
	fprintf(stderr, STREAM1_NAME ": id: %s, count: %d\n",
		id, stream1_count);
	return true;
}

// stream2 callback
bool stream2_cb(const char *id, const struct redisReply *reply, void *data) {
	++stream2_count;
	fprintf(stderr, STREAM2_NAME ": id: %s, count: %d\n",
		id, stream2_count);
	return true;
}

// stream1 callback
bool stream1_xrevrange_cb(const char *id, const struct redisReply *reply, void *data) {
	++stream1_xrevrange_count;
	fprintf(stderr, "XREVRANGE " STREAM1_NAME ": id: %s, count: %d\n",
		id, stream1_xrevrange_count);
	return true;
}

// stream2 callback
bool stream2_xrevrange_cb(const char *id, const struct redisReply *reply, void *data) {
	++stream2_xrevrange_count;
	fprintf(stderr, "XREVRANGE " STREAM2_NAME ": id: %s, count: %d\n",
		id, stream2_xrevrange_count);
	return true;
}

void *producer_thread(
	void *data)
{
	redisContext *ctx;
	struct redis_xadd_info stream1_data[2];
	struct redis_xadd_info stream2_data[2];

	// Connect to redis
	ctx = redis_context_init();

	// Fill in the data
	stream1_data[0].key = STREAM1_KEY1;
	stream1_data[0].key_len = CONST_STRLEN(STREAM1_KEY1);
	stream1_data[0].data = (const uint8_t*)STREAM1_DATA1;
	stream1_data[0].data_len = CONST_STRLEN(STREAM1_DATA1);
	stream1_data[1].key = STREAM1_KEY2;
	stream1_data[1].key_len = CONST_STRLEN(STREAM1_KEY2);
	stream1_data[1].data = (const uint8_t*)STREAM1_DATA2;
	stream1_data[1].data_len = CONST_STRLEN(STREAM1_DATA2);

	stream2_data[0].key = STREAM2_KEY1;
	stream2_data[0].key_len = CONST_STRLEN(STREAM2_KEY1);
	stream2_data[0].data = (const uint8_t*)STREAM2_DATA1;
	stream2_data[0].data_len = CONST_STRLEN(STREAM2_DATA1);
	stream2_data[1].key = STREAM2_KEY2;
	stream2_data[1].key_len = CONST_STRLEN(STREAM2_KEY2);
	stream2_data[1].data = (const uint8_t*)STREAM2_DATA2;
	stream2_data[1].data_len = CONST_STRLEN(STREAM2_DATA2);

	// Loop, producing XADD commands
	while(true) {
		if (!redis_xadd(ctx, STREAM1_NAME, stream1_data, 2, 1024, true, NULL)) {
			fprintf(stderr, "Failed to XADD to stream1!\n");
			break;
		}
		if (!redis_xadd(ctx, STREAM2_NAME, stream2_data, 2, 1024, true, NULL)) {
			fprintf(stderr, "Failed to XADD to stream2!\n");
			break;
		}
	}

	redis_context_cleanup(ctx);

	return NULL;
}

bool skill_client_cb(const char *key) {
	fprintf(stderr, "skill/client: %s\n", key);
	return true;
}

bool cmd_response_cb(const uint8_t *response, size_t response_len)
{
	fprintf(stderr, "Response: %s\n", (const char*)response);
	return true;
}


// Tests XREAD on multiple streams
void test_xread(
	redisContext *ctx)
{
	pthread_t producer;
	struct redis_stream_info infos[2];

	// Set up the stream infos
	redis_init_stream_info(ctx, &infos[0], STREAM1_NAME, stream1_cb, NULL, NULL);
	redis_init_stream_info(ctx, &infos[1], STREAM2_NAME, stream2_cb, NULL, NULL);

	// Spin up the producer
	pthread_create(&producer, NULL, producer_thread, NULL);

	// Want to loop until we've gotten all of the replies
	while ((stream1_count < N_TESTS) || (stream2_count < N_TESTS)) {
		if (!redis_xread(ctx, infos, 2, 10000)) {
			fprintf(stderr, "Failed to xread!\n");
			return;
		}
	}

	// Now, we want to get the most recent 3 things from each stream
	redis_xrevrange(ctx, STREAM1_NAME, stream1_xrevrange_cb, 3, NULL);
	redis_xrevrange(ctx, STREAM2_NAME, stream2_xrevrange_cb, 3, NULL);

}

// Tests sending a command
void test_send_command(
	redisContext *ctx)
{
	struct client *clnt;

	clnt = client_init(ctx, "elementary");
	if (clnt == NULL) {
		fprintf(stderr, "Failed to create client!\n");
		return;
	}

	// Attempt to send a command
	fprintf(stderr, "command status: %d\n",
		client_send_command(
			ctx, clnt, "test_skill", "test_command",
			(uint8_t*)"hello", 6, true, cmd_response_cb));

	client_cleanup(ctx, clnt);
}

bool robot_position_data_cb(
	const struct redis_xread_kv_item *kv_items,
	int n_kv_items,
	void *user_data)
{
	int i;
	bool ret_val = false;

	fprintf(stderr, "Got robot position data!\n");

	// Get the KV items and make sure they're all there
	redis_print_xread_kv_items(kv_items, n_kv_items);
	for (i = 0; i < n_kv_items; ++i) {
		if (!kv_items[i].found) {
			goto done;
		}
	}

	// Note the success
	ret_val = true;

done:
	return ret_val;
}

bool realsense_data_cb(
	const struct redis_xread_kv_item *kv_items,
	int n_kv_items,
	void *user_data)
{
	int i;
	bool ret_val = false;

	fprintf(stderr, "Got realsense data!\n");

	// Get the KV items and make sure they're all there
	redis_print_xread_kv_items(kv_items, n_kv_items);
	for (i = 0; i < n_kv_items; ++i) {
		if (!kv_items[i].found) {
			goto done;
		}
	}

	// Note the success
	ret_val = true;

done:
	return ret_val;
}
// Tests droplet loop
void test_droplet_loop(
	redisContext *ctx)
{
	struct client_droplet_info infos[2];
	struct redis_xread_kv_item droplet1_items[3];
	struct redis_xread_kv_item droplet2_items[2];
	struct client *clnt;

	clnt = client_init(ctx, "elementary");
	if (clnt == NULL) {
		fprintf(stderr, "Failed to create client!\n");
		return;
	}

	infos[0].skill = "robot";
	infos[0].stream = "position";
	infos[0].kv_items = droplet1_items;
	infos[0].n_kv_items = sizeof(droplet1_items) / sizeof(struct redis_xread_kv_item);
	infos[0].response_cb = robot_position_data_cb;
	infos[0].user_data = NULL;

	droplet1_items[0].key = "position";
	droplet1_items[0].key_len = strlen(droplet1_items[0].key);
	droplet1_items[1].key = "velocity";
	droplet1_items[1].key_len = strlen(droplet1_items[1].key);
	droplet1_items[2].key = "acceleration";
	droplet1_items[2].key_len = strlen(droplet1_items[2].key);

	infos[1].skill = "realsense";
	infos[1].stream = "data";
	infos[1].kv_items = droplet2_items;
	infos[1].n_kv_items = sizeof(droplet2_items) / sizeof(struct redis_xread_kv_item);
	infos[1].response_cb = realsense_data_cb;
	infos[1].user_data = NULL;

	droplet2_items[0].key = "rgb";
	droplet2_items[0].key_len = strlen(droplet2_items[0].key);
	droplet2_items[1].key = "depth";
	droplet2_items[1].key_len = strlen(droplet2_items[1].key);

	fprintf(stderr, "return: %d\n",
		client_droplet_loop(
			ctx, clnt, infos, 2, true, 0));

	client_cleanup(ctx, clnt);
}

// Tests getting the N most recent droplets
void test_droplet_get_n_most_recent(
	redisContext *ctx)
{
	struct client_droplet_info info;
	struct redis_xread_kv_item droplet1_items[3];
	struct client *clnt;

	clnt = client_init(ctx, "elementary");
	if (clnt == NULL) {
		fprintf(stderr, "Failed to create client!\n");
		return;
	}

	info.skill = "robot";
	info.stream = "position";
	info.kv_items = droplet1_items;
	info.n_kv_items = sizeof(droplet1_items) / sizeof(struct redis_xread_kv_item);
	info.response_cb = robot_position_data_cb;
	info.user_data = NULL;

	droplet1_items[0].key = "position";
	droplet1_items[0].key_len = strlen(droplet1_items[0].key);
	droplet1_items[1].key = "velocity";
	droplet1_items[1].key_len = strlen(droplet1_items[1].key);
	droplet1_items[2].key = "acceleration";
	droplet1_items[2].key_len = strlen(droplet1_items[2].key);

	fprintf(stderr, "return: %d\n",
		client_droplet_get_n_most_recent(
			ctx, clnt, &info, 3));

	client_cleanup(ctx, clnt);
}

void test_get_all_clients(
	redisContext *ctx)
{
	fprintf(stderr, "Found %d clients\n", skills_get_all_clients(ctx, skill_client_cb));
}

void test_get_all_skills(
	redisContext *ctx)
{
	fprintf(stderr, "Found %d skills\n", skills_get_all_skills(ctx, skill_client_cb));
}

void test_skill_init(
	redisContext *ctx)
{
	struct skill *skl;

	skl = skill_init(ctx, "elem_test");
	if (skl != NULL) {
		fprintf(stderr, "Made skill!\n");
	}
}

void test_skill_cleanup(
	redisContext *ctx)
{
	struct skill *skl;

	skl = skill_init(ctx, "elem_test");
	if (skl != NULL) {
		fprintf(stderr, "Made skill!\n");
	}

	skill_cleanup(ctx, skl);
	fprintf(stderr, "Cleaned up skill!\n");
}

int move_joints_callback(
	uint8_t *data,
	size_t data_len,
	uint8_t **response,
	size_t *response_len,
	char **err_str)
{
	fprintf(stderr, "move joints got data %s, len %lu\n",
		(char *)data, data_len);
	asprintf((char**)response, "response string");
	*response_len = strlen(*((char**)response));
	asprintf(err_str, "no error!");
	return 0;
}

void test_skill_command_loop(
	redisContext *ctx)
{
	struct skill *skl;

	// Make the skill
	skl = skill_init(ctx, "robot");
	if (skl != NULL) {
		fprintf(stderr, "Made skill!\n");
	}

	// Add the move_joints command
	if (!skill_add_command(skl, "move_joints", move_joints_callback, 5000)) {
		fprintf(stderr, "Failed to add command!\n");
		return;
	}

	skill_command_loop(ctx, skl, true, 0);

	fprintf(stderr, "Command loop returned!\n");
}

void *skill_test_command_and_response(
	void *data)
{
	redisContext *ctx;
	struct skill *skl;

	ctx = redis_context_init();
	skl = skill_init(ctx, "robot");
	skill_add_command(skl, "move_joints", move_joints_callback, 5000);
	skill_command_loop(ctx, skl, true, 0);
	return NULL;
}

bool test_command_response_cb(
	const uint8_t *response,
	size_t response_len)
{
	fprintf(stderr, "Got response %s, len %lu\n", (char*)response, response_len);
	return true;
}

void test_command_and_response(
	redisContext *ctx)
{
	pthread_t skill;
	struct client *clnt;
	int i;

	// Create the skill thread
	pthread_create(&skill, NULL, skill_test_command_and_response, NULL);

	usleep(1000000);

	// Now, as a client I want to call the skill N times and print the
	//	response
	clnt = client_init(ctx, "testing_client");

	for (i = 0; i < 10; ++i) {
		client_send_command(ctx, clnt, "robot", "move_joints",
			(uint8_t*)"hello, world", sizeof("hello, world") - 1, true, test_command_response_cb);
	}
}

void test_stream(
	redisContext *ctx)
{
	struct skill *skill;
	struct skill_stream *stream;
	int i;
	char item1_buf[64];
	size_t item1_len;
	char item2_buf[64];
	size_t item2_len;


	skill = skill_init(ctx, "test1");
	stream = skill_init_stream(ctx, skill, "data", 2);

	// Set up the droplets
	stream->droplet_items[0].key = "item1";
	stream->droplet_items[0].key_len = strlen("item1");
	stream->droplet_items[1].key = "item2";
	stream->droplet_items[1].key_len = strlen("item2");

	for (i = 0; i < 100; ++i) {
		item1_len = snprintf(item1_buf, sizeof(item1_buf), "item1: %d", i);
		stream->droplet_items[0].data = (uint8_t*)item1_buf;
		stream->droplet_items[0].data_len = item1_len;

		item2_len = snprintf(item2_buf, sizeof(item2_buf), "item2: %d", i);
		stream->droplet_items[1].data = (uint8_t*)item2_buf;
		stream->droplet_items[1].data_len = item2_len;

		// Publish the droplet
		fprintf(stderr, "added droplet: %d\n",
			skill_add_droplet(
				ctx, stream, SKILL_DROPLET_DEFAULT_TIMESTAMP,
				SKILL_DROPLET_DEFAULT_MAXLEN));
	}

	// skill_cleanup_stream(ctx, stream);
	// skill_cleanup(ctx, skill);
}

TEST(basic_test, boolean)
{
	ASSERT_EQ(1, 1);
}

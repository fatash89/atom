# SDK Specification and API

This section contains the atom spec. It will cover at a high-level the functions that each language client is expected to implement and then at a low-level how it is implemented in redis.

## Element Initialization

```c
#include <atom/redis.h>
#include <atom/element.h>
#include <assert.h>

//
// A note about redis: In the C API we explicitly pass around
//  redis handles. These are automatically managed using a pool
//  the C++ API. The idea of a redis handle is a single connection
//  to the redis server and a single memory pool for redis
//  commands and responses. A handle should only ever be used by
//  one thread at a time. In this example we'll show how to make
//  the redis context. In the other examples we'll pass on including
//  this and trust the user.
//

redisContext *ctx = redis_context_init();
assert(ctx != NULL);

struct element *my_element = element_init(ctx, "my_element");
assert(my_element != NULL);

```

```cpp
#include <atomcpp/element.h>

atom::Element my_element("my_element");
```

```python
from atom import Element

my_element = Element("my_element")
```

Creates a new element.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `name`    | string | Name for the element |

### Return Value

Element created (none if a class constructor)

### Spec

First, make a response stream named `response:$name` and a command stream named `command:$name` by XADDing the following `key:value` pairs to the streams:

| Key | Value |
|-----|-------|
| `language` | Name of language client |
| `version` | Version string for language client |

## Element Cleanup

```c
#include <atom/element.h>

element_cleanup(ctx, my_element);
```

```cpp
// Only needed if created with "new"
delete my_element;
```

```python
del my_element
```

Called in class destructor or when we're done with an element

### API

| Parameter | Type | Description |
|-----------|------|-------------|

### Return Value

None

### Spec

Delete the following redis streams using `UNLINK`:

- `response:$name`
- `command:$name`
- Any data streams the element created

## Write Entry

```c
#include <atom/element.h>
#include <atom/element_entry_write.h>

// Number of keys we're going to write to the stream
int n_keys = 2;

// First, we need to create the struct that will hold
//  the info for the write
struct element_entry_write_info *info =
    element_entry_write_init(
        ctx,                    // redis context
        my_element,             // Element pointer
        "stream",               // stream name
        n_keys);                // Number of keys for the stream

// Now, for each key in the stream, we want to initialize
//  the key string. This only needs to be done once, when the stream
//  is initialized. The memory for this was taken care of
//  in element_entry_write_init()
info->items[0].key = "hello";
info->items[0].key_len = strlen(info->items[0].key);
info->items[1].key = "world";
info->items[1].key_len = strlen(info->items[1].key);

// Now, we can go ahead and fill in the data. When we do this
//  in a loop, only this part need be repeated
info->items[0].data = some_ptr;
info->items[0].data_len = some_len;
info->items[1].data = some_other_ptr;
info->items[1].data_len = some_other_len;

// Finally we can go ahead and publish
enum atom_error_t err = element_entry_write(
    ctx,                                    // Redis context
    info,                                   // Stream info
    ELEMENT_DATA_WRITE_DEFAULT_TIMESTAMP,   // Timestamp
    ELEMENT_DATA_WRITE_DEFAULT_MAXLEN);     // Max len of stream in redis
```

```cpp
#include <atomcpp/element.h>

// Make the entry_data map. entry_data_t is a typedef
// for a std::map<std::string,std::string>
atom::entry_data_t data;

// Fill in some fields and values
data["field_1"] = "value_1";
data["field_2"] = "value_2";

// And publish it
enum atom_error_t err = my_element.entryWrite("my_stream", data);
```

```python
# The field_data_map is used to populate a entry with any number of fields of data
# The key of the map will allow elements who receive the entry to easily access the relevant field of data
field_data_map = {"my_field": "my_value"}
my_element.entry_write("my_stream", field_data_map, maxlen=512)


# If you would like to publish non-string data types (int, list, dict, etc.), you can serialize the data using the serialize flag
# Just remember to pass the deserialize flag when reading the data!
field_data_map = {"hello": 0, "atom": ["a", "t", "o", "m"]}
my_element.entry_write("my_stream", field_data_map, maxlen=512, serialize=True)
```

Publish a piece of data to a stream.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Stream name |
| `data` | map | key:value pairs of data to publish |
| `maxlen` | int | Maximum length of stream. Optional. Default 1024 |

### Return Value

Error code

### Spec

`XADD stream:$element:$name MAXLEN ~ $maxlen * k1 v1 k2 v2 ...`

Note the `~` in the `MAXLEN` command. This is an important performance feature as it tells redis to keep *at least* `$maxlen` entries around but not necessarily *exactly* that many. Redis will remove entries when performant/convenient.

Note the `*` as well, it tells redis to auto-generate a stream ID for the entry. By default redis will make this a millisecond-level UNIX timestamp appended with `-0` at the end. If multiple entries have the same timestamp, redis will bump the `-0` to `-1` and so on.

## Read N most recent entries

```c
#include <atom/redis.h>
#include <atom/element.h>
#include <atom/element_entry_read.h>

//
// Note: For all "read" APIs, the C language client is entirely
//  zero-copy. As such, it is based exclusively around callbacks
//  and it is up to the user to perform any copies as necessary
//  if desired.
//
//  The read APIs all focus around the
//  struct element_entry_read_info, explained below:
//
//    const char *element;                      -- element name
//    const char *stream;                       -- stream name
//    struct redis_xread_kv_item *kv_items;     -- keys to read
//    size_t n_kv_items;                        -- number of keys
//    void *user_data;                          -- user pointer
//    bool (*response_cb)(                      -- response callback
//        const char *id,
//        const struct redis_xread_kv_item *kv_items,
//        int n_kv_items,
//        void *user_data);
//
enum expected_keys_t {
    EXPECTED_KEY_FOO,
    EXPECTED_KEY_BAR,
    N_EXPECTED_KEYS
};

#define EXPECTED_KEY_FOO_STR "foo"
#define EXPECTED_KEY_BAR_STR "bar"

// Read callback with following args:
//
//  id -- Redis ID of the entry read
//  kv_items -- pointer to same array of items created in the read info
//  n_kv_items -- how many kv items there are
//  user_data -- user pointer
bool callback(
    const char *id,
    const struct redis_xread_kv_item *kv_items,
    int n_kv_items,
    void *user_data)
{
    // Make sure that the keys were found in the data
    if (!kv_items[EXPECTED_KEY_FOO].found ||
        !kv_items[EXPECTED_KEY_BAR].found)
    {
        return false;
    }

    // Do something with the key data. Each item
    //  has a redisReply field which will have a data pointer
    //  and a length.
    char *foo_data = kv_items[EXPECTED_KEY_FOO].reply->str;
    size_t foo_data_len = kv_items[EXPECTED_KEY_FOO].reply->len;

    // Note the success
    return true;
}

// Make the info on the stack
struct element_entry_read_info info;

// Fill in the info
info.element = "element";
info.stream = "stream";
info.kv_items = malloc(
    N_EXPECTED_KEYS * sizeof(struct redis_xread_kv_item));
info.n_kv_items = N_EXPECTED_KEYS;
info.user_data = NULL;
info.response_cb = callback;

// Fill in the expected keys. The API is designed s.t. the user
//  specifies the keys they're looking for and the atom library
//  will fill in if the key is found and if so the data for it.
//  In this way we can be zero-copy above the hiredis API
info.kv_items[EXPECTED_KEY_FOO].key =
    EXPECTED_KEY_FOO_STR;
info.kv_items[EXPECTED_KEY_FOO].key_len =
    sizeof(EXPECTED_KEY_FOO_STR) - 1;
info.kv_items[EXPECTED_KEY_BAR].key =
    EXPECTED_KEY_BAR_STR;
info.kv_items[EXPECTED_KEY_BAR].key_len =
    sizeof(EXPECTED_KEY_BAR_STR) - 1;

// Now we're ready to go ahead and do the read
enum atom_error_t err = element_entry_read_n(
    ctx,
    my_element,
    &info,
    n);
```

```cpp
#include <atomcpp/element.h>

// Make the vector of Entry classes that the call ill return
std::vector<atom::Entry> ret;

// Make the vector of keys that we're expecting. This is a bit
//  of a legacy of the underlying C api and will hopefully
//  be removed in the future
std::vector<std::string> expected_keys = { "key1", "key2"};

// Number of entries to read
int n_entries = 1;

// Perform the read
enum atom_error_t err = my_element.entryReadN(
    "element",
    "stream",
    expected_keys,
    n_entries,
    ret);
```

```python
# This gets the 5 most recent entries from your_stream
entries = my_element.entry_read_n("your_element", "your_stream", 5)

# If the element is publishing serialized entries, they can be deserialized
entries = my_element.entry_read_n("your_element", "your_stream", 5, deserialize=True)
```

Reads N entries from a stream in a nonblocking fashion. Returns the N most recent entries.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `element` | string | Element whose stream we want to read |
| `name` | string | Stream name |
| `n` | int | How many entries to read |

### Return Value

List of entry objects. Each entry should have an "ID" field with the redis ID of the entry as well as a field for the key:value map returned from the read. Objects should be returned with the newest (most recent) at index 0 and then on.

### Spec

`XREVRANGE stream:$element:$name + - COUNT N`

Uses XREVRANGE to get the most recent N items.

## Read up to the next N entries

```c
#include <atom/redis.h>
#include <atom/element.h>
#include <atom/element_entry_read.h>

//
// Note: see element_entry_read_n spec for the basics on
//  the read APIs.
//

struct element_entry_read_info info;

// ... Fill in the info ...

// Now we're ready to go ahead and do the read
enum atom_error_t err = element_entry_read_since(
    ctx,
    my_element,
    &info,
    ENTRY_READ_SINCE_BEGIN_BLOCKING_WITH_NEWEST_ID,
    timeout,
    n);
```

```cpp
#include <atomcpp/element.h>

// Make the vector of Entry classes that the call ill return
std::vector<atom::Entry> ret;

// Make the vector of keys that we're expecting. This is a bit
//  of a legacy of the underlying C api and will hopefully
//  be removed in the future
std::vector<std::string> expected_keys = { "key1", "key2"};

// Max number of entries to read
int max_entries = 100;

// String keeping track of last ID. If this is the first time
//  we're going to be doing the read, we want to leave this as ""
//  but note that we MUST SPECIFY A BLOCK TIME. After this,
//  we want to keep track of the final ID that was returned to us
//  in the API call and pass that through to the next call.
std::string last_id = "";

// How long to block waiting for any data
int block_ms = 1000;

// Do the read
enum atom_error_t err = element.entryReadSince(
    "element",
    "stream",
    expected_keys,
    max_entries,
    ret,
    last_id,
    block_ms);
```

```python
# This will get the 10 oldest entries from your_stream since the beginning of time.
entries = my_element.entry_read_since("your_element", "your_stream", last_id="0", n=10)

# If the element is publishing serialized entries, they can be deserialized
entries = my_element.entry_read_since("your_element", "your_stream", last_id="0", n=10, deserialize=True)
```

Allows user to traverse a stream without missing any data. Reads all entries on the stream (or up to at most N), since the last piece we have read.

If `last_id` is not passed, this call will return the first new piece
of data that's been written after our call.

If `block` is passed this API will block until new data is available.

This API can be used to traverse the stream in a blocking pub-sub fashion if `block` is true. Each time the call returns, loop over the list of entries, process them, then pass the final ID back in and wait for more data.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `element` | string | Element whose stream we want to read |
| `name` | string | Stream name |
| `n` | int | How many entries to read |
| `last_id` | string | Optional. If passed, Redis ID of last entry we read. If not passed we will return the first piece of data that is written to the stream after this call is made.  |
| `block` | bool | If true, will block until we can return at least 1 piece of data. If false, can return with no data if none has been written. |

### Return Value

List of entry objects. Each entry should have an "ID" field with the redis ID of the entry as well as a field for the key:value map returned from the read. Objects should be returned with the oldest at index 0 and then on. Note that this order *is the opposite* of the order of the "Read N most recent" spec. This is intentional since it lends itself to the usage paradigms.

### Spec

`XREAD COUNT N (BLOCK $T) STREAMS stream:$element:name $last_id`

Use XREAD (with optional block call and some default timeout) since the last ID on the stream. If `last_id` is not passed, use `$` as this is the special symbol for `XREAD` to let it know to return the *next piece* of data. Note that if `$` is passed, (and therefore the user did not specify `last_id`) **you must use BLOCK in the XREAD**.

#### Future Improvement

This API should move to using [consumer groups](https://redis.io/commands/XREADGROUP) since this would allow us to not need to specify the `last_id` and simply specify the consumer and group. This would also automagically allow us to scale/load balance if were already using consumer groups since if another consumer is added to the same group redis will automatically take care of it.

## Read entries with callbacks

```c
#include <atom/redis.h>
#include <atom/element.h>
#include <atom/element_entry_read.h>

//
// Note: see element_entry_read_n spec for the basics on
//  the read APIs.
//
#define N_INFOS 3

struct element_entry_read_info infos[N_INFOS];

// ... fill in the infos ...

enum atom_error_t err = element_entry_read_loop(
    ctx,                                // redis context
    my_element,                         // element struct
    infos,                              // array of infos
    N_INFOS,                            // number of infos in the array
    true,                               // boolean to loop forever
    ELEMENT_ENTRY_READ_LOOP_FOREVER);   // timeout

```

```cpp
#include <atomcpp/element.h>

// Callback handler for when we get a new piece of data on the
//  stream. Passed a reference to the entry that was read as
//  well as the user data pointer
bool callback(
    Entry &e,
    void *user_data)
{
    ...
}

// Make the ReadMap for handling the commands
atom::ElementReadMap m;

// User data pointer
void *user_data = NULL;

// Add the handler.
m.addHandler(
    "element",              // Element which publishes stream
    "stream",               // stream name
    { "key1", "key2" },     // expected keys
    callback,               // callback function
    user_data);             // user data pointer.

// This function will never return. If passing an integer instead
//  of `ELEMENT_INFINITE_READ_LOOPS` will return after that many
//  piecesof data have been read
enum atom_error_t err = my_element.entryReadLoop(
    m,
    ELEMENT_INFINITE_READ_LOOPS);

```

```python
# This will print any entries that are published on stream_0 and stream_1
your_stream_0_handler = StreamHandler("your_element_0", "your_stream_0", print)
your_stream_1_handler = StreamHandler("your_element_1", "your_stream_1", print)
my_element.entry_read_loop([your_stream_0_handler, your_stream_1_handler])

# If the element is publishing serialized entries, they can be deserialized
my_element.entry_read_loop([your_stream_0_handler, your_stream_1_handler], deserialize=True)
```

This API is used to monitor multiple streams with a single thread. The user registers all streams that they're interested in along with the desired callback to use.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `handlers` | map | Map of (element, stream) keys to handler values. Could also be a list of (element, stream, handler) tuples |
| `n_loops` | int | Optional. Maximum number of loops. If passed, function will return after `n_loops` XREADS. Note that this doesn't necessarily guarantee that `n_loops` pieces of data have been read on a given stream, since each `XREAD` can yield multiple pieces of data on a given stream. |
| `timeout` | int | Optional. Max timeout between calls to `XREAD`. If 0, will never time out. Otherwise, max number of milliseconds to wait for any data after which we'll return an error. Default 0, i.e. no timeout |

### Return Value

Error code

### Spec

In a loop for up to `n_loops` iterations (or indefinitely if `n_loops` indicates):

1. Use `XREAD BLOCK $timeout COUNT Y STREAMS stream:$elem1:$name1 stream:$elem2:$name2 ... id1 id2 ...`, where each stream in the handler map corresponds to `stream:$elemX:$nameX` and `idX`. Note that you'll need to keep track of the stream IDs internally s.t. with each call we're only getting new data. Note the `COUNT Y` statement in here: this limits the max number of entries returned in each call and can help if we get backlogged. It's optional and up the language client if this should be added but will safeguard against network and memory bursts.
2. When the `XREAD` returns, loop over the data.
3. For each piece of data, pass the ID and a key, value map to the handler indicated for that stream.

#### Future Improvement

Again, it's likely better to move this to `XREADGROUP` so that we don't need to internally track the IDs and we can let redis do that for us.

## Add Command

```c
#include <atom/element.h>
#include <atom/element_command_server.h>

//
// Form 1: command_callback allocates response using malloc()
//

// Command callback, taking the following params:
//
//  data -- user data
//  data_len -- user data length
//  response -- response buffer, to be allocated using malloc() by this function. Will be freed by the API.
//  response_len -- length of response buffer
//  error_str -- if allocated, will send the error string to the user
//  user_data -- user pointer
int command_callback(
    uint8_t *data,
    size_t data_len,
    uint8_t **response,
    size_t *response_len,
    char **error_str,
    void *user_data)
{
    // Make the response
    *response = malloc(some_len);
    *response_len = some_len;

    // Note the success
    return 0;
}

// Add the command
element_command_add(
    my_element,             // Element struct
    "command",              // Command string
    command_callback,       // Callback function
    NULL,                   // Cleanup pointer -- none needed
    NULL,                   // User data -- none used here
    1000);                  // timeout

//
// Form 2: Using a custom cleanup function
//

void cleanup_callback(
    void *ptr)
{
    // Do some fancy cleanup with ptr
    fancy_free(ptr);
}

// Command callback, taking the following params:
//
//  data -- user data
//  data_len -- user data length
//  response -- response buffer, will be passed to cleanup_callback
//      since we did some complicated allocation
//  response_len -- length of response buffer
//  error_str -- if allocated, will send the error string to the user
//  user_data -- user pointer
int command_callback(
    uint8_t *data,
    size_t data_len,
    uint8_t **response,
    size_t *response_len,
    char **error_str,
    void *user_data)
{
    // Make the response using some fancy, non-standard
    //  allocation, likely a C++ object using this API.
    *response = facy_alloc(some_len);
    *response_len = some_len;

    // Note the success
    return 0;
}

// Add the command
element_command_add(
    my_element,             // Element struct
    "command",              // Command string
    command_callback,       // Callback function
    cleanup_callback,       // Cleanup function
    NULL,                   // User data -- none used here
    1000);                  // timeout
```

```cpp
#include <atomcpp/element.h>

//
// NOTE: All command handling APIs work with the ElementResponse
//          class as this is what they generally return.
//          The ElementResponse has the following APIs:
//

// Sets the data
void setData(
    const uint8_t *d,
    size_t l);
void setData(
    std::string d);

// Sets the error
void setError(
    int e,
    const char *s);
void setError(
    int e,
    std::string s = "");

//
// NOTE: There are three ways to use the addCommand API in C++:
//      1. Calback-based
//      2. Class-based
//      3. Class-based with msgpack serialization/deserialization
//
//  Both are shown in these docs
//

//
// 1. Callback-based addCommand
//

bool command_callback(
    const uint8_t *data,
    size_t data_len,
    ElementResponse *resp,
    void *user_data)
{
    // Set the data in the response
    resp->setData("some_data");

    // Note success/failure of the callback
    return true;
}

// Add the command
enum atom_error_t err = my_element.addCommand(
    "command_name",                 // Command name
    "command description string",   // Description string
    command_callback,               // Callback function
    user_data,                      // User data pointer
    1000);                          //timeout, in milliseconds

//
// 2. Class-based addCommand
//

enum atom_error_t err = my_element.addCommand(
    new CommandUserCallback(
        "command_name",
        "command description string",
        command_callback,
        user_data,
        1000));

//
// 3. Class-based addCommand with msgpack
//

// Define your class that implements the CommandMsgpack template.
//  In this template you'll find the following:
class MsgpackHello : public CommandMsgpack<
    std::string, // Request type
    std::string> // Response type
{
public:
    using CommandMsgpack<std::string, std::string>::CommandMsgpack;

    // Validate the request data. There is a Req *req_data
    //  in the class
    virtual bool validate() {
        if (*req_data != "hello") {
            return false;
        }
        return true;
    }

    // Run the command. Can use both the Req* req_data and
    //  should set Res* res_data.
    virtual bool run() {
        *res_data = "world";
        return true;
    }
};

// Add a class-based command with msgapck. This will test msgpack
//  as well as any memory allocations associated with it
enum atom_error_t err = my_element.addCommand(
    new MsgpackHello(
        "hello_msgpack",
        "example messagepack-based hello, world command",
        1000));
```

```python
from atom.messages import Response

# Let's add a command to our element that will add 1 to the input data
# Notice that the developer is responsible for converting the data sent from the element
# Also notice that every command must return a Response object
def add_1(data):
    return Response(int(data) + 1)

# Since this command is simple, we can set the timeout fairly low
my_element.command_add("add_1", add_1, timeout=50)

# Alternatively, we could use serialization to keep from having to convert data types.
def add_2(data):
    return Response(data + 2, serialize=True)

# The deserialize flag will allow the data to be deserialized before it is sent to the add_2 function
my_element.command_add("add_2", add_2, timeout=50, deserialize=True)
```

Adds a command to an element. The element will then "support" this command, allowing other elements to call it.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Name of the new command |
| `handler` | function | Handler to call when command is called by another element. Handler should take command data as an argument and return some combination of response data and an error code. |
| `timeout` | int | Timeout to pass to callers in ACK packet. When a command is called by another element, the caller gets an ACK with this timeout telling them how long to wait before timing out if they're going to do a blocking wait for the response |

### Return Value

Error Code

### Spec

Adds command info to internal data structure so that we can effectively use it when we get command requests from other elements. Typically best to use a map of some sort internally, but up to the language client to determine how to do it.

## Handle Commands

```c
#include <atom/element.h>
#include <atom/element_command_server.h>

enum atom_error_t err = element_command_loop(
    ctx,
    my_element,
    true,
    ELEMENT_COMMAND_LOOP_NO_TIMEOUT);
```

```cpp
#include <atomcpp/element.h>

// Loop forever, handling commands. If passing an integer instead
//  of ELEMENT_INFINITE_COMMAND_LOOPS, will return after N commands
//  have been dispatched.
enum atom_error_t err = my_element.commandLoop(
    ELEMENT_INFINITE_COMMAND_LOOPS);
```

```python
my_element.command_loop()
```

Puts the current thread into a command-handling loop. The thread will now serve command requests from other elements for commands that have been previously added using the "Add Command" API.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `n_loops` | int | Optional. Number of loops to handle before returning. If 0, loop indefinitely. |
| `n_threads` | int | Not currently supported. Optional. Specifies the number of command handling threads to spin up |

### Return Value

Error Code

### Spec

In a loop for up to `n_loops` iterations (or indefinitely if `n_loops` indicates):

1. `XREAD BLOCK 0 STREAMS command:$self $id`. This will do a blocking read on our command stream.
2. For each command request that we get from the command stream, perform the steps below. Note that when doing the `XREAD` from the command stream we get a unique command ID (the entry ID) which when coupled with the element's name makes a globally unique command identifier in the system `(element, Entry ID)`.
3. Check to see if the command is supported. If not, send an error response on their response stream, `response:$caller`. Otherwise, proceed.
4. Send an ACK packet back to the caller on their response stream, `response:$caller`. In the ACK specify the timeout that was given to us when the user called the "Add Command" API. Also specify the entry ID and our element name s.t. the caller knows for which command the ACK is intended.
5. Process the command, calling the registered callback and passing any data received to it.
6. Send a response packet back to the caller on their response stream, `response:$caller`. The response will contain the response data from the callback as well as an error code. It will again also contain our element name as well as the entry ID so that the caller knows for which command this response is intended.

All writes to response streams are done with `XADD response:$caller * ...` where `$caller` is the name of the element that called our command. See below for expected key, value pairs in the command sequence.

Note that when we're referencing a "packet" here we're talking about a single entry on either a command or response stream.

Ideally this is moved to use XREADGROUP so that we can multi-thread this by just spinning up multiple copies of the handler thread in the same consumer group with different consumer IDs. This will also allow us to not need to keep track of the IDs on the stream with the XREADs.

All handlers should be written with the idea that this is a multi-thread safe call, i.e. we can handle multiple commands simultaneously.

#### Command Packet Data

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `element` | String | yes | Name of element calling the command, i.e. the caller |
| `cmd` | String | yes | Name of the command to call |
| `data` | binary/unspecified | no | Data payload for the command. No serialization/deserialization enforced. All language clients should support reads/writes of raw binary |

#### Acknowledge Packet Data

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `element` | String | yes | Name of element responding to the command, i.e. the responder |
| `cmd_id` | String | yes | Redis entry ID from the responder's command stream. Note that the (element, cmd_id) tuple is a global unique command identifier in the system |
| `timeout` | int | yes | Millisecond timeout for caller to wait for a response packet |

#### Response Packet Data

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `element` | String | yes | Name of element responding to the command, i.e. the responder |
| `cmd_id` | String | yes | Redis entry ID from the responder's command stream. Note that the (element, cmd_id) tuple is a global unique command identifier in the system |
| `cmd` | String | yes | Name of the command that was executed. This isn't strictly necessary to identify the command but is useful for debug/logging purposes |
| `err_code` | int | yes | Error code for the command |
| `data` | binary/unspecified | no | Response data. No serialization/deserialization enforced. All language clients should support reads/writes of raw binary |
| `err_str` | string | no | Error string for the command |

## Send Command

```c
#include <atom/element.h>
#include <atom/element_command_send.h>

// Response callback with parameters:
//
//  response -- data from command element
//  response_len -- length of response from command element
//  user_data -- user pointer passed to element_command_send
bool response_callback(
    const uint8_t *response,
    size_t response_len,
    void *user_data),

uint8_t *data;
size_t data_len;
char *error_str = NULL;

// Send the command
enum atom_error_t err = element_command_send(
    ctx,                    // redis context
    my_element,             // element struct
    "command_element",      // name of element we're sending command to
    "command",              // command we're calling
    data,                   // data to send to the command
    data_len,               // length of data to the command
    true,                   // whether or not to wait for the response
    response_callback,      // callback to call when we get a response
    NULL,                   // user pointer
    &error_str);            // pointer to error string

// Free the error string if we got one
if (error_str) {
    free(error_str);
}
```

```cpp
#include <atomcpp/element.h>

//
// NOTE: there are two APIs through which commands can be sent
//      1. Using a data pointer, data length and response reference
//      2. Using a msgpack template
//

//
// 1. Using data and response
//

// Make the response that will be filled in
atom::ElementResponse resp;

// Send the command
enum atom_error_t err = my_element.sendCommand(
    resp,               // Response reference
    "element",          // Element name
    "command",          // Command name
    NULL,               // Command data
    0);                 // Command data length

//
// 2. Using msgpack
//

// Make the response that will be filled in
atom::ElementResponse resp;

std::string req = "hello";
std::string res;
enum atom_error_t err = element.sendCommand<std::string, std::string>(
    resp,               // Response reference
    "element",          // Element name
    "command",          // Command name
    req,                // Request reference
    res);               // Response reference

```

```python
response = my_element.command_send("your_element", "your_command", data, block=True)

# If serialized data is expected by the command, pass the serialize flag to the function.
# If the response of the command is serialized, it can be deserialized with the deserialize flag.
response = my_element.command_send("your_element", "your_command", data, block=True, serialize=True, deserialize=True)
```

Sends a command to another element

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `element` | String | Name of element to which we want to send the command |
| `command` | String | Command we want to call |
| `data` | binary/unspecified | Optional data payload for the command |
| `block` | bool | Optional value to wait for the response to the command. If false will only wait for the ACK from the element and not the response packet, else if true will wait for both the ACK and the response |

### Return Value

Object containing error code and response data. Implementation to be specified by the language client.

### Spec

Perform the following steps:

1. `XADD command:$element * ...` where `...` is the "Command Packet Data" from the "Handle Commands" spec. This sends the command to the element. This XADD will return an entry ID that uniquely identifies it and is based on a global millisecond-level redis timestamp. This ID will be used in a few places and will be referred to as `cmd_id`.
2. `XREAD BLOCK 1000 STREAMS response:$self $cmd_id`. This performs a blocking read on our response stream for the ACK packet. Note that we're reading for all entries since our command packet which works nicely since the entry IDs use a global redis timestamp.
3. If (2) times out, return an error, i.e. we didn't get an ACK
4. If (2) returns data, loop over the data and look for a packet with matching `element` and `cmd_id` fields.
5. If (4) didn't find a match, go back to 2, subtracting the current time off of the timeout and updating the ID to be that of the most recent entry we received.
6. If (4) found a match, this is our ACK. If `block` is false then we're done, else proceed.
7. `XREAD BLOCK $timeout STREAMS response:$self $ack_id`, where `$timeout` is the timeout specified in the ACK and `$ack_id` is the entry ID of the ACK which we got on our response stream. This will read all data since the ACK on the response stream.
8. If (7) times out, return an error, i.e. we didn't get a response.
9. If (7) returns data, loop over the data and look for a packet with matching `element` and `cmd_id` fields.
10. If (9) didn't find a match, go back to (7), subtracting the current time off of the timeout and updating the ID to that of the most recent entry we received.
11. If (9) did find a match, this is our response. Process the packet and return the proper data to the user.

Note that if implemented correctly, per the spec, this is a thread-safe process, i.e. multiple threads in the same element can be monitoring and using the response stream without any issue.

## Log

```c
#include <atom/atom.h>
#include <syslog.h>

//
// 3 APIs to log:
//  1. Using printf format + args
//  2. using string + length
//  3. Using vfprintf format + variadic args
//

// 1. Using format
enum atom_error_t err = atom_logf(
    ctx
    my_element
    LOG_DEBUG,
    "I %s to log!",
    "love");

// 2. Using msg + len
enum atom_error_t err = atom_log(
    ctx
    my_element
    LOG_DEBUG,
    "some_msg",
    9);

// 3. Using va_list.
enum atom_error_t err = atom_vlogf(
    ctx
    my_element
    LOG_DEBUG,
    "I %s to log!",
    args);
```

```cpp
#include <atomcpp/element.h>
#include <syslog.h>

// Log with a log level and using printf-style formatting
my_element.log(LOG_DEBUG, "testing: level %d", LOG_DEBUG);
```

```python
from atom.messages import LogLevel

my_element.log(LogLevel.INFO, "Hello, world!", stdout=True)
```

Writes a log message to the global `atom` log stream.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `level` | int | Level indicating severity of log. Must conform to [syslog level standard](http://man7.org/linux/man-pages/man2/syslog.2.html). |
| `msg` | string | Log string |

### Return Value

Error Code

### Spec

`XADD log * ...` where `...` are keys and values conforming to the below packet:

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `element` | string | yes | Name of the element sending the log |
| `level` | int | yes | syslog level of the log |
| `msg` | string | yes | log string |
| `host` | string | yes | Hostname of the container/computer running the element, i.e. contents of `/etc/hostname`. When run in a docker container this will be a unique container ID |

## Element Discovery

```c
#include <atom/atom.h>

struct atom_list_node *elements = NULL;

enum atom_error_t err = atom_get_all_elements(
    ctx,
    &elements);

if (elements != NULL) {
    struct atom_list_node *iter = elements;
    while (iter != NULL) {
        fprintf(stderr, "Element name: %s", iter->name);
        iter = iter->next;
    }

    atom_list_free(elements);
}
```

```cpp
#include <atomcpp/element.h>

std::vector<std::string> elements;

enum atom_error_t err = my_element.getAllElements(elements);
```

```python
elements = my_element.get_all_elements()
```

Queries for all elements in the system

### API

| Parameter | Type | Description |
|-----------|------|-------------|

### Return Value

List of all elements in the system

### Spec

Use `SCAN` to traverse all streams starting with `response:` and all streams starting with `command:`. Return the intersection of both lists. Do not use `KEYS` as this is dangerous to do in production systems

## Stream Discovery


```c
#include <atom/atom.h>

struct atom_list_node *streams = NULL;

enum atom_error_t err = atom_get_all_data_streams(
    ctx,        // redis context
    "",         // element name. Leave empty for all elements
    &streams);  //

if (streams != NULL) {
    struct atom_list_node *iter = streams;
    while (iter != NULL) {
        fprintf(stderr, "Stream name: %s", iter->name);
        iter = iter->next;
    }

    // Loop over streams
    atom_list_free(streams);
}
```

```cpp
#include <atomcpp/element.h>

//
// 1. For all elements
//

// Map of (element, [streams])
std::map<std::string, std::vector<std::string>> stream_map;

// Will fill in the map
enum atom_error_t err = my_element.getAllStreams(stream_map);

//
// 2. For a particular element
//

std::vector<std::string> stream_vec;

enum atom_error_t err = my_element.getAllStreams(
    "element",
    stream_vec);
```

```python
streams = my_element.get_all_streams(element="your_element")
```

Queries for all streams in the system

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `element` | String | Optional. Specifies if streams returned should only be for a single element or for all elements |

### Return Value

List of all streams in the system, either for the element (if specified), or for all elements.

### Spec

Use `SCAN` to traverse all streams starting with a prefix. If `element` is not specified, use prefix of `stream:`. Else, use prefix of  `stream:$element`.

## Get Element Version

Allows user to query any given element for its atom version and language.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `element` | String | The element name we want to query about its version |

### Return Value

Object containing error code and response data. Response data should have version and language fields. Implementation to be specified by the language client.

### Spec

Version queries are implemented using existing command/response mechanism, with a custom `version` command automatically initialized by atom.
This is a reserved name, so users should be unable to add custom command handlers with this string value.
Version responses use the same response mechanism as any other command, with the data field populated by a dictionary containing 'version' and 'language' fields.

## Set Healthcheck

Allows user to optionally set custom healthcheck on an element. By default, any element running its command loop should report as healthy.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `handler` | function | Handler to call when a healthcheck command is received. Handler function takes no args, and should return a response indicating whether the element is healthy or not using the err_code on the response. |

### Return Value

None

### Spec

Healthchecks are implemented using the existing command/response mechanism, with a custom `healthcheck` command automatically initialized by atom.
This is a reserved name, so users should be unable to add custom command handlers with this string value.
Healthcheck responses use the same response mechanism as any other command, a 0 error code means the element is healthy and ready to accept commands,
anything else indicates a failure. If the element is unhealthy, the err_str field should be used to indicate the failure reason.

## Wait for Elements Healthy

Allows user to do a blocking wait until a given list of elements are all reporting healthy.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `elements` | list[string] | List of element names we want to repeatedly query and wait until they are all healthy |
| `retry_interval` | float | If one or more elements are unhealthy, how long we should wait until retrying the healthchecks |

### Return Value

None

### Spec

Wait for elements healthy should leverage the existing healthcheck command and block until all given elements are reporting healthy.
This command should be backwards compatible, so you should do a version check on each given element to make sure it has support for healthchecks.
If it does not, you should assume it is healthy, so that this command doesn't block indefinitely.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `handler` | function | Handler to call when a healthcheck command is received. Handler function takes no args, and should return a response indicating whether the element is healthy or not using the err_code on the response. |

### Return Value

None

### Spec

Healthchecks are implemented using the existing command/response mechanism, with a custom `healthcheck` command automatically initialized by atom.
This is a reserved name, so users should be unable to add custom command handlers with this string value.
Healthcheck responses use the same response mechanism as any other command, a 0 error code means the element is healthy and ready to accept commands,
anything else indicates a failure. If the element is unhealthy, the err_str field should be used to indicate the failure reason.

## Error Codes

The atom spec defines a set of error codes to standardize errors throughout the system.

| Error Code | Description |
|------------|-------------|
0           | No Error
1           | Internal Error, something that happened in the language client |
2           | Redis Error |
3           | Didn't get an ACK to a command |
4           | Didn't get a response to a command |
5           | Invalid command packet, i.e. not all required key/value pairs were present |
6           | Unsupported command |
7           | User callback for command failed |
100-999     | Reserved for language-client specific errors |
1000+       | Reserved for user-callback errors |

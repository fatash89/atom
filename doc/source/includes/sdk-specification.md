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


# If you would like to publish non-string data types (int, list, dict, etc.), you can serialize the data using the serialization argument.
# A "ser" key will be added to the entry with the serialization method used to serialize ("none" if not serialized).
field_data_map = {"hello": 0, "atom": ["a", "t", "o", "m"]}
my_element.entry_write("my_stream", field_data_map, maxlen=512, serialization="msgpack")
```

Publish a piece of data to a stream.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Stream name |
| `data` | map | key:value pairs of data to publish |
| `maxlen` | int | Maximum length of stream. Optional. Default 1024 |
| `serialization` | string | Type of serialization to use when publishing the entry |

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

# If the element is publishing serialized entries, they can be deserialized.
# The entry will be checked for a "ser" flag to determine the deserialization method.
# If not present, the serialization option will be used for deserialization, defaulting to "none".
entries = my_element.entry_read_n("your_element", "your_stream", 5, serialization="msgpack")
```

Reads N entries from a stream in a nonblocking fashion. Returns the N most recent entries.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `element` | string | Element whose stream we want to read |
| `name` | string | Stream name |
| `n` | int | How many entries to read |
| `serialization` | str | The deserialization method to use (defaults to None). If the entry contains a serialization key, that method will be used for deserialization before using this parameter. |
| `force_serialization` | bool | If True, explicitly override the auto-serialization and use the user-specified form of serialization |


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

# If the element is publishing serialized entries, they can be deserialized.
# The entry will be checked for a "ser" flag to determine the deserialization method.
# If not present, the serialization option will be used for deserialization, defaulting to "none".
entries = my_element.entry_read_since("your_element", "your_stream", last_id="0", n=10, serialization="msgpack")
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
| `serialization` | str | The deserialization method to use (defaults to None). If the entry contains a serialization key, that method will be used for deserialization before using this parameter. |
| `force_serialization` | bool | If True, explicitly override the auto-serialization and use the user-specified form of serialization |


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

# If the element is publishing serialized entries, they can be deserialized.
# The entry will be checked for a "ser" flag to determine the deserialization method.
# If not present, the serialization option will be used for deserialization, defaulting to "none".
my_element.entry_read_loop([your_stream_0_handler, your_stream_1_handler], serialization="msgpack")
```

This API is used to monitor multiple streams with a single thread. The user registers all streams that they're interested in along with the desired callback to use.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `handlers` | map | Map of (element, stream) keys to handler values. Could also be a list of (element, stream, handler) tuples |
| `n_loops` | int | Optional. Maximum number of loops. If passed, function will return after `n_loops` XREADS. Note that this doesn't necessarily guarantee that `n_loops` pieces of data have been read on a given stream, since each `XREAD` can yield multiple pieces of data on a given stream. |
| `timeout` | int | Optional. Max timeout between calls to `XREAD`. If 0, will never time out. Otherwise, max number of milliseconds to wait for any data after which we'll return an error. Default 0, i.e. no timeout |
| `serialization` | str | The deserialization method to use (defaults to None). If the entry contains a serialization key, that method will be used for deserialization before using this parameter. |
| `force_serialization` | bool | If True, explicitly override the auto-serialization and use the user-specified form of serialization |


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
//      3. Class-based with serialization/deserialization
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
# The serialization method to use can be specified using the serialization option.
def add_2(data):
    return Response(data + 2, serialization="msgpack")

# The serialization option will allow the data to be deserialized before it is sent to the add_2 function.
my_element.command_add("add_2", add_2, timeout=50, serialization="msgpack")
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

# If serialized data is expected by the command, pass the serialization option to the function.
# If the response of the command is serialized, it will be automatically deserialized.
# The serialization option allows the user to specify which method of serialization to use, defaulting to "none".
# Apache Arrow serialization, specified with "arrow", is preferred for array-like data such as images.
response = my_element.command_send("your_element", "your_command", data, block=True, serialization="arrow")
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

1. `XADD command:$element * ...` where `...` is the "Command Packet Data" from the "Handle Commands" spec. This sends the command to the element. This XADD will return an entry ID that uniquely identifies it and is based on a global millisecond-level redis timestamp. This ID will be used in a few places and will be referred to as `cmd_id`. Primary data will go on a "data" key in the stream. Raw data will be added on additional keys in the stream where the key name will be key from the raw data dict and the value will be the value from the raw data dict.
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

```python
streams = my_element.get_element_version("your_element")
```

Allows user to query any given element for its atom version and language.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `element` | String | The element name we want to query about its version |

### Return Value

Object containing error code and response data. Response data should have version and language fields. Implementation to be specified by the language client.

### Spec

Version queries are implemented using existing command/response mechanism, with a custom `version` command automatically initialized by atom. This is a reserved name, so users should be unable to add custom command handlers with this string value. Version responses use the same response mechanism as any other command, with the data field populated by a dictionary containing 'version' and 'language' fields.

## Set Healthcheck

```python
def is_healthy(self):
    # This is an example health-check, which can be used to tell other elements that depend on you
    # whether you are ready to receive commands or not. Any non-zero error code means you are unhealthy.
    return Response(err_code=0, err_str="Everything is good")

my_element.healthcheck_set(is_healthy)
```

Allows user to optionally set custom healthcheck on an element. By default, any element running its command loop should report as healthy.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `handler` | function | Handler to call when a healthcheck command is received. Handler function takes no args, and should return a response indicating whether the element is healthy or not using the err_code on the response. |

### Return Value

None

### Spec

Healthchecks are implemented using the existing command/response mechanism, with a custom `healthcheck` command automatically initialized by atom. This is a reserved name, so users should be unable to add custom command handlers with this string value. Healthcheck responses use the same response mechanism as any other command, a 0 error code means the element is healthy and ready to accept commands, anything else indicates a failure. If the element is unhealthy, the err_str field should be used to indicate the failure reason.

## Wait for Elements Healthy

```python
my_element.wait_for_elements_healthy(['your_element'])
```

Allows user to do a blocking wait until a given list of elements are all reporting healthy.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `elements` | list[string] | List of element names we want to repeatedly query and wait until they are all healthy |
| `retry_interval` | float | If one or more elements are unhealthy, how long we should wait until retrying the healthchecks |

### Return Value

None

### Spec

Wait for elements healthy should leverage the existing healthcheck command and block until all given elements are reporting healthy. This command should be backwards compatible, so you should do a version check on each given element to make sure it has support for healthchecks. If it does not, you should assume it is healthy, so that this command doesn't block indefinitely.

## Create Reference

```python

# Basic reference, default seralization="none" and timeout_ms=10000
data = b'hello, world!'
ref_ids = my_element.reference_create(data)
my_element.reference_delete(*ref_ids)

# Reference with user specified key
data = b"hello, world!"
key = "my_ref"
ref_ids = my_element.reference_create(data, key=key)
my_element.reference_delete(*ref_ids)

# Serialized reference
data = {"hello" : "world"}
ref_ids = my_element.reference_create(data, serialization="msgpack")
my_element.reference_delete(*ref_ids)

# Explicit timeout
data = {"hello" : "world"}
ref_ids = my_element.reference_create(data, serialization="msgpack", timeout_ms=1000)
my_element.reference_delete(*ref_ids)

# No timeout
data = {"hello" : "world"}
ref_ids = my_element.reference_create(data, serialization="msgpack", timeout_ms=0)
my_element.reference_delete(*ref_ids)

# Creating multiple references
data = ["a", "b", "c"]
ref_ids = my_element.reference_create(*data, serialization="msgpack")
my_element.reference_delete(*ref_ids)

# Creating multiple references with user-specified keys
data = ["a", "b", "c"]
keys = ["ref1", "ref2", "ref3"]
ref_ids = my_element.reference_create(*data, keys=keys, serialization="msgpack")
my_element.reference_delete(*ref_ids)
```

Turn a user-specified data blob into an Atom reference. The data
will be stored in Redis and will be able to be retrieved using
the `reference_get` API.

The `timeout_ms` argument is powerful -- it allows you to set a time at which the reference will auto-expire and the memory will be cleaned up. *This feature is not to be depended on as the primary clean-up mechanism for references*. Calls to `reference_create` should *always* be followed by calls to `reference_delete` once the reference is no longer needed with the timeout acting as a fallback for errors/exceptions/bugs s.t. we don't slowly accumulate memory and die. Do not rely on the timeout to free your memory, this is poor form.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `*data` | Binary/Object | One or more objects to be used for the reference |
| `keys` | strs | Single string or list of strings to be used in reference IDs; defaults to None in which case UUIDs will
be generated |
| `serialization` | str | The method of serialization to use; defaults to None. |
| `timeout_ms` | int | How long the references should exist in Atom. This sets the expiry timeout in redis. Units in milliseconds. Set to 0 for no timeout, i.e. references exist until explicitly deleted. |

### Return Value

List of string IDs for the newly created references.

### Spec

1. Check that if keys is not None, same number of keys as data were provided; raise Exception if not.
2. Make reference IDs using the following string format where `$id` is either user specified or a generated UUID:
```
key = reference:$element_name:$id
```
2. Serialize the data if specified to in the args
3. Depending on the value of `timeout_ms`, run a SET command as below with `PX $timeout` of `timeout_ms>0`, else without the `PX` portion. The NX portion ensures that the reference key doesn't already exist which is pretty unlikely with the UUID scheme but should be checked regardless.
```
SET $key NX [PX $timeout]
```
4. Return `[$key]`

## Get Reference

```python

# Basic reference, default and timeout_ms=10000
data = b'hello, world!'
ref_id = my_element.reference_create(data)[0]
ref_data = my_element.reference_get(ref_id)[0]
# ref_data == data
my_element.reference_delete(ref_id)

# Serialized reference
data = {"hello" : "world"}
ref_id = my_element.reference_create(data, serialization="msgpack")[0]
ref_data = my_element.reference_get(ref_id, serialization="msgpack")[0]
# ref_data == data
my_element.reference_delete(ref_id)

# Get multiple references
data = ["a", "b", "c"]
ref_ids = my_element.reference_create(*data, serialization="msgpack")
ref_data = my_element.reference_get(*ref_ids, serialization="msgpack")
# ref_data[0] == "a"
# ref_data[1] == "b"
# ref_data[2] == "c"
my_element.reference_delete(*ref_ids)
```

Receive the data from Atom for the given references

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `*keys` | String | One or more Reference IDs |
| `serialization` | str | The deserialization method to use (defaults to None). If the reference key contains a serialization method, that method will be used for deserialization before using this parameter. |
| `force_serialization` | bool | If True, explicitly override the auto-serialization and use the user-specified form of serialization |

### Return Value

List of data items corresponding with the reference IDs passed as arguments.

### Spec

1. Call redis `GET` on the reference
```
GET $key
```
2. If no data, return None/NULL/error/etc.
3. If there's data, checks reference key for deserialization method to deserialize.
4. If no serialization method in reference key, use `serialization` parameter to determine deserialization.
4. Return {$key : data}

## Delete Reference

```python

# Basic reference, no expiry -- exists until deleted
data = b'hello, world!'
ref_id = my_element.reference_create(data, timeout_ms=0)[0]

# Delete the reference
my_element.reference_delete(ref_id)

ref_data = my_element.reference_get(ref_id)[0]
# ref_data is None

# Multiple references can be deleted in the same fashion that they are created
data = ["a", "b", "c"]
ref_ids = my_element.reference_create(*data, timeout_ms=0)

# Delete the references
my_element.reference_delete(*ref_ids)
```

Explicitly delete references from Atom. If a reference was created with `timeout_ms=0` then this *always* needs to be called after, otherwise the memory will just sit in redis. In general, it's ill-advised to use `timeout_ms=0` and recommended you choose a safe timeout as a fallback in case we ever forget to call this function. Normal dev flows should *always* plan to call this function and should use the timeout as a fallback, not a primary mechanism, for cleaning up memory.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | String | One or more reference IDs to delete |

### Return Value

Nothing. If reference is already gone, no issues.

### Spec

1. Call redis `UNLINK` or `DEL` on the reference -- `UNLINK` is preferred.
```
UNLINK $key
```

## Create Reference From Stream

```python

#
# Using the most recent piece of data from a stream
#

# Publish some data on a stream -- shown only for example,
#   can use any stream from any element
stream_name = "example_stream"
stream_data = {"key1": b"value1!", "key2" : b"value2!"}
my_element.entry_write(stream_name, stream_data)

# Make a reference to the data that's currently in the above
# stream. Will make a reference to the most recent piece of data
# in the stream. references is a dictionary of reference strings,
# with a key for each key in the stream entry
references = caller.reference_create_from_stream(my_element.name, stream_name, timeout_ms=0)
key1_data = caller.reference_get(references["key1"])[0]
# key1_data == b"value1!"
key2_data = caller.reference_get(references["key2"])[0]
# key2_data == b"value2!"

# Need to delete *each* key when done
for key in references:
    caller.reference_delete(references[key])

#
# Using an exact stream ID
#

# Publish some data on a stream -- shown only for example,
#   can use any stream from any element
stream_name = "example_stream"
stream_data_1 = {"key1": b"value1!", "key2" : b"value2!"}
stream_data_2 = {"key1": b"value3!", "key2" : b"value4!"}
stream_data_3 = {"key1": b"value5!", "key2" : b"value6!"}
id_1 = my_element.entry_write(stream_name, stream_data_1)
id_2 = my_element.entry_write(stream_name, stream_data_2)
id_3 = my_element.entry_write(stream_name, stream_data_3)

# Make a reference to the data that's currently in the above
# stream. Will make a reference to the most recent piece of data
# in the stream. references is a dictionary of reference strings,
# with a key for each key in the stream entry
references = caller.reference_create_from_stream(my_element.name, stream_name, stream_id=id_2, timeout_ms=0)
key1_data = caller.reference_get(references["key1"])[0]
# key1_data == b"value3!"
key2_data = caller.reference_get(references["key2"])[0]
# key2_data == b"value4!"

# Need to delete *each* key when done
for key in references:
    caller.reference_delete(references[key])
```

This allows us to specify an element, stream and (optional) stream ID and create a set of references from it. An independent reference will be created for each key in the stream, where the reference will end with :key.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `element` | String | Name of element whose stream you want to create a reference from |
| `stream` | String | Name of stream from above element you want to create a reference from |
| `stream_id` | String | Explicit redis stream ID (returned from `entry_write` or `entry_read`s to create the reference from. If blank/None/etc. then create a reference to the most recent piece of data on the stream |
| `timeout_ms` | int | How long the reference should exist in Atom. This sets the expiry timeout in redis. Units in milliseconds. Set to 0 for no timeout, i.e. reference exists until explicitly deleted. |

### Return Value

Dict/object mapping keys on the stream to references. We need one reference per key s.t. we can keep the optional serialization/deserialization of the data types and redis SET only supports binary blobs and not hashtables like streams. Caller must call `reference_delete` on each stream in the dictionary!

### Spec

This is our first command that requires us to use lua scripting in Redis and is decently nontrivial to set up and incorporate into the client. We have shared lua scripts in the `lua-scripts` folder at the top level of the repo and your client must be sure to ship the lua script with the package s.t. regardless of how it's installed (container vs not), the script is accessible by the installed client.

Then, on initialization of the element, we need to use the `SCROPT LOAD` command in redis to load the lua script. This will return a `sha1` for the script that we can use to call the script. A script is necessary in order to read from a stream and write to a key without the data ever leaving redis.

#### Language client and element init

1. Add the `stream_reference.lua` lua script to your package installation
2. Add `stream_reference.lua` to the set of lua scripts that your client loads on init. Scripts should be loaded with `SCRIPT LOAD`. Store the `sha1` reference to the loaded script in a private variable in your element.

#### Command

1. Call the `stream_reference.lua` script by using the `EVALSHA` command on the `sha1` returned in (2) above. You will need to pass four arguments to the script:
(a) Name of the stream to read. This should be the full redis key for the stream, i.e. `stream:$element:$stream_name`
(b) `stream_id`. Either valid stream ID or empty string, same as the argument
(c) Full reference key, following the spec in step 1 of `reference_create`, i.e. `reference:$this_element:uuid4`
(d) `timeout_ms`. 0 for no timeout, else positive number of milliseconds. Same as the argument.
```
EVALSHA `sha1` 0 $a $b $c $d
```
2. The `EVALSHA` command will return a list of reference keys, one for each key in the stream entry. Return those to the user.

## Get Reference Time Remaining

```python

# Basic reference, no expiry -- exists until deleted
data = b'hello, world!'
ref_id = my_element.reference_create(data, timeout_ms=0)[0]
time_remaining = my_element.reference_get_timeout_ms(ref_id)
# time_remaining == -1 i.e. no timeout
my_element.reference_delete(ref_id)

# Basic reference, with timeout
data = b'hello, world!'
ref_id = my_element.reference_create(data, timeout_ms=1000)[0]
time_remaining = my_element.reference_get_timeout_ms(ref_id)
# time_remaining ~= 1000
my_element.reference_delete(ref_id)
```

Gets the amount of time until a reference expires and its memory is cleaned up.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | String | Reference ID to get timeout for |

### Return Value

Integer number of milliseconds until the key expires. `-1` for no expiry, i.e. persists until deleted.

### Spec

1. Call `PTTL` on the key
```
PTTL $key
```

## Update reference timeout

```python

# Basic reference, no expiry -- exists until deleted
data = b'hello, world!'
ref_id = my_element.reference_create(data, timeout_ms=0)[0]
time_remaining = my_element.reference_get_timeout_ms(ref_id)
# time_remaining == -1 i.e. no timeout

# Update the timeout for the reference
my_element.reference_update_timeout_ms(ref_id, 10000)

time_remaining = my_element.reference_get_timeout_ms(ref_id)
# time_remaining ~= 10000
my_element.reference_delete(ref_id)
```

Update the timeout for a reference so that it expires in `timeout_ms` milliseconds from now, with the edge case of `timeout_ms==0` yielding no timeout, i.e. it persists until deleted.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | String | Reference ID to update timeout of |
| `timeout_ms` | Int | How many milliseconds until the timeout should expire |

### Return Value

None

### Spec

1. If `timeout_ms == 0` call `PERSIST` on the key
```
PERSIST $key
```
2. Else, call `PEXPIRE` on the key
```
PEXPIRE $key $timeout_ms
```

## Write Parameter

```python

# Basic parameter, override=True, default seralization="none", timeout_ms=0 (no timeout)
data = {b"my_str": b"hello, world!"}
key = "my_param"
param_fields = caller.parameter_write(key, data)
my_element.parameter_delete(key)

# Serialized parameter
data = {b"my_str": b"hello, world!"}
key = "my_param"
param_fields = caller.parameter_write(key, data, serialization="msgpack")
my_element.parameter_delete(key)

# Explicit timeout
data = {b"my_str": b"hello, world!"}
key = "my_param"
param_fields = caller.parameter_write(key, data, serialization="msgpack", timeout_ms=1000)
my_element.parameter_delete(key)

# Overrides not allowed
data = {b"my_str": b"hello, world!"}
key = "my_param"
param_fields = caller.parameter_write(key, data, override=False)
my_element.parameter_delete(key)
```

Turn a user-specified data dictionary into an Atom parameter. The data
will be stored in Redis and will be able to be retrieved using
the `parameter_read` API.

The `timeout_ms` argument is powerful -- it allows you to set a time at which the parameter will auto-expire and the memory will be cleaned up. By default, the `timeout_ms` is set to 0 so the parameter will not expire and will exist until explicitly deleted. Elements that create parameters should explicitly delete them when they are no longer needed.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | str | Key at which to store the parameter |
| `data` | dict | Dictionary containing key-val pairs to store in Redis hash at specified key |
| `override` | bool | Boolean for whether parameter values may be overriden by future calls to `parameter_write` |
| `serialization` | str | The method of serialization to use on the parameter fields; defaults to None. |
| `timeout_ms` | int | How long the parameter should exist in Atom. This sets the expiry timeout in redis. Units in milliseconds. Defaults to 0 for no timeout, i.e. parameter exists until explicitly deleted. |

### Return Value

List of parameter fields written to.

### Spec

1. Make a parameter ID using the following string format:
```
key = parameter:$key
```
2. Check if the parameter already exists in atom; if so, check that the requested serialization is the same as the
existing serialization, and if not raise an Exception.
3. If the parameter exists and the requested serialization matches the existing serialization, check the existing override
setting. If the existing override is set to false, and the user is trying to update existing param fields,
raise an Exception. Otherwise, continue writing or updating the parameter fields.
3. Serialize the data as requested.
4. Run an HSET command to set each field of the parameter in Redis, where the `($field, $value)` pairs come from the
data dictionary.
```
HSET $key $field $value
```
5. If the data is serialized, use HSET to set the reserved "ser" field.
6. Use HSET to set the reserved "override" field to either "true" or "false". Note that if the parameter already existed
with an override value of "false", it cannot be updated. If the override value was set to "true", however, it can be updated
to "false".
4. If a postive, nonzero `timeout_ms` is requested, run a PEXPIRE command to set the timeout.
4. Return list of fields written to.

## Read Parameter

```python

# Basic parameter, default serialization/override/timeout
data = {b"my_str": b"hello, world!"}
key = "my_param"
param_fields = caller.parameter_write(key, data)
param_data = caller.parameter_read(key)
# param_data == data
my_element.parameter_delete(key)

# Serialized parameter
data = {b"my_str": b"hello, world!"}
key = "my_param"
param_fields = caller.parameter_write(key, data, serialization="msgpack")
param_data = my_element.parameter_read(key)
# param_data == data
my_element.parameter_delete(key)

# Read specific parameter field(s)
data = {b"str1": b"hello, world!",
        b"str2": b"goodbye"}
key = "my_param"
param_fields = caller.parameter_write(key, data, serialization="msgpack")
param_data = my_element.parameter_read(key, fields=["str2"])
my_element.parameter_delete(key)
```

Receive the data from Atom for the given parameter

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | String | Parameter key to read |
| `fields` | str(s) | Optional str field name or list of str field names to read from parameter
| `serialization` | str | The deserialization method to use (defaults to None). If the parameter contains a serialization method, that method will be used for deserialization before using this parameter. |
| `force_serialization` | bool | If True, explicitly override the auto-serialization and use the user-specified form of serialization |

### Return Value

Dictionary of data read from the parameter store.

### Spec

1. Call redis `HGETALL` on the parameter store
```
HGETALL $key
```
2. If no data, return None/NULL/error/etc.
3. If there's data, checks "ser" field for deserialization method to deserialize.
4. If no serialization method in parameter, use `serialization` parameter to determine deserialization.
4. Return {$field : data} for every field requested; return all fields if no fields specified.

## Delete Parameter

```python

# Basic parameter, no expiry -- exists until deleted
data = {b"my_str": b"hello, world!"}
key = "my_param"
param_fields = caller.parameter_write(key, data)

# Delete the parameter
my_element.parameter_delete(key)

param_data = my_element.parameter_read(key)
# param_data is None
```

Explicitly delete parameters from Atom. If a parameter was created with the default `timeout_ms=0` then this should *always* be called on element shutdown or when the parameter is no longer necessary, otherwise the memory will just sit in Redis.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | String | Parameter key to delete |

### Return Value

Nothing. If parameter does not exist, raises a KeyError.

### Spec

1. Call redis `DEL` on the parameter key
```
DEL $key
```

## Get Parameter Time Remaining

```python

# Basic parameter, no expiry -- exists until deleted
data = {b"my_str": b"hello, world!"}
key = "my_param"
param_fields = caller.parameter_write(key, data)
time_remaining = my_element.parameter_get_timeout_ms(key)
# time_remaining == -1 i.e. no timeout
my_element.parameter_delete(key)

# Basic parameter, with timeout
data = {b"my_str": b"hello, world!"}
key = "my_param"
param_fields = caller.parameter_write(key, data, timeout_ms=1000)
time_remaining = my_element.parameter_get_timeout_ms(key)
# time_remaining ~= 1000
my_element.parameter_delete(key)
```

Gets the amount of time until a parameter expires and its memory is cleaned up.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | String | Parameter key to get timeout for |

### Return Value

Integer number of milliseconds until the key expires. `-1` for no expiry, i.e. persists until deleted.

### Spec

1. Call `PTTL` on the key
```
PTTL $key
```

## Update parameter timeout

```python

# Basic parameter, no expiry -- exists until deleted
data = {b"my_str": b"hello, world!"}
key = "my_param"
param_fields = caller.parameter_write(key, data)[0]
time_remaining = my_element.parameter_get_timeout_ms(key)
# time_remaining == -1 i.e. no timeout

# Update the timeout for the parameter
my_element.parameter_update_timeout_ms(key, 10000)

time_remaining = my_element.parameter_get_timeout_ms(key)
# time_remaining ~= 10000
my_element.parameter_delete(key)
```

Update the timeout for a parameter so that it expires in `timeout_ms` milliseconds from now, with the edge case of `timeout_ms==0` yielding no timeout, i.e. it persists until deleted.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | String | Parameter key to update timeout of |
| `timeout_ms` | Int | How many milliseconds until the timeout should expire |

### Return Value

None

### Spec

1. If `timeout_ms == 0` call `PERSIST` on the key
```
PERSIST $key
```
2. Else, call `PEXPIRE` on the key
```
PEXPIRE $key $timeout_ms
```

## Set Counter

```python

curr_value = caller.counter_set(key, value)
```

Set a counter to a value. Will return the current value of the counter

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | String | Key of the counter, i.e. the golbal name |
| `value` | Int | Value to set the counter to |

### Return Value

Integer current value of the counter. Should match value.

### Spec

Call `SET` on `counter:<key>`

## Get Counter

```python

curr_value = caller.counter_get(key)
```

Get the current value of a counter

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | String | Key of the counter, i.e. the golbal name |

### Return Value

Integer current value of the counter.

### Spec

Call `GET` on `counter:<key>`

## Update Counter

```python

#
# Update a counter after it's created with an initial counter_set
#

curr_value = caller.counter_set(key, 10)
# curr_value == 10
curr_value = caller.counter_update(key, 2)
# curr_value == 12
curr_value = caller.counter_update(key, -5)
# curr_value == 7

#
# Use counter_update to create a counter
#
curr_value = caller.counter_update(new_key, 3)
# curr_value == 3
```

Update a counter's value by the integer passed in an atomic fasion. If the
counter doesn't previously exist, set the counter's value to the integer
passed. Integer passed can be positive or negative to increment or decrement
the counter.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | String | Key of the counter, i.e. the golbal name |
| `value` | Int | Value to set the counter to |

### Return Value

Integer current value of the counter after applying the update

### Spec

Call `INCRBY` on `counter:<key>`. `INCRBY`'s default behavior is to create
if the key does not already exist.

## Delete Counter

```python

curr_value = caller.counter_delete(key)
```

Delete the counter from redis.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | String | Key of the counter, i.e. the golbal name |

### Return Value

None

### Spec

Call `DEL` on `counter:<key>`

## Add to / Create sorted set

```python

caller.sorted_set_add(key, member, value)
```

Add a < member : value > pair to a sorted set

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | String | Key of the sorted set, i.e. the golbal name |
| `member` | String | Member name within the sorted set |
| `value` | Float | Value of the member within the sorted set. Members will be sorted according to this value |

### Return Value

None

### Spec

Call `ZADD` with the key, member and value

## Pop from a sorted set

```python

item = caller.sorted_set_pop(key)
item = caller.sorted_set_pop(key, least=False)
```

Remove and return either the smallest or largest member of a sorted set. The item is removed from the set.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | String | Key of the sorted set, i.e. the golbal name |
| `least` | Boolean | Optional (default true) argument. If true, will return the smallest member of the set, if false will return the largest member of the set. |

### Return Value

(member, value) tuple of the item removed from the set

### Spec

If least is true, cal `ZPOPMIN`, else `ZPOPMAX`

## Read a member of sorted set

```python

item = caller.sorted_set_read(key, member)
```

Read the value of a member in a sorted set without removing it. The item is not removed.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | String | Key of the sorted set, i.e. the golbal name |
| `member` | String | Member name within the sorted set |

### Return Value

value of the member, float.

### Spec

Call `ZSCORE` on the key and member

## Remove a member of sorted set

```python

caller.sorted_set_remove(key, member)
```

Remove a member of a sorted set. The item is removed.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | String | Key of the sorted set, i.e. the golbal name |
| `member` | String | Member name within the sorted set |

### Return Value

None

### Spec

Call `ZREM` on the key and member

## Read a range of a sorted set

```python

items = caller.sorted_set_range(key, start, stop)
items = caller.sorted_set_range(key, start, stop, least=False)
items = caller.sorted_set_range(key, start, stop, withvalues=False)
```

Reads a range of values over the sorted set, either from least to greatest
or greatest to least. Either returns only member strings or member strings with
values.

### API

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | String | Key of the sorted set, i.e. the golbal name |
| `start` | int | Starting index into the range. Should be >= 0 |
| `end` | int | Starting index into the range. Should be >= -1, where -1 signifies the full range, i.e. the end of it |
| `least` | Boolean | Optional (default true) argument. If true, will consider the set sorted from least to greatest, i.e. the start index is the least and the end index the greatest. If false, the opposite, i.e. the start index is the greatest and the end index the least. |
| `withvalues` | Boolean | Optional (default true) argument. If true, return will be sorted list of (member, value) tuples. If false, return will be sorted list of member strings only. |

### Return Value

Sorted list of items in the range specified. If `withvalues` is True, will be list of (member, value) tuples, else will be list of member strings only.

### Spec

If `least` is true use `ZRANGE`, else ise `ZREVRANGE`

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

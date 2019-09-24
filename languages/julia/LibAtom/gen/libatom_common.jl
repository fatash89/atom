# Automatically generated using Clang.jl


const ATOM_RESPONSE_STREAM_PREFIX = "response:"
const ATOM_COMMAND_STREAM_PREFIX = "command:"
const ATOM_DATA_STREAM_PREFIX = "stream:"
const ATOM_LOG_STREAM_NAME = "log"
const ATOM_VERSION_KEY = "version"
const ATOM_LANGUAGE_KEY = "language"
const ATOM_VERSION = "v0.1.0"
const ATOM_LANGUAGE = "c"
const ATOM_DEFAULT_MAXLEN = 1024
const ATOM_DEFAULT_APPROX_MAXLEN = true
const ATOM_NAME_MAXLEN = 128
const ATOM_LOG_MAXLEN = 1024
const COMMAND_KEY_ELEMENT_STR = "element"
const COMMAND_KEY_COMMAND_STR = "cmd"
const COMMAND_KEY_DATA_STR = "data"
const STREAM_KEY_ELEMENT_STR = "element"
const STREAM_KEY_ID_STR = "cmd_id"
const ACK_KEY_TIMEOUT_STR = "timeout"
const RESPONSE_KEY_CMD_STR = "cmd"
const RESPONSE_KEY_ERR_CODE_STR = "err_code"
const RESPONSE_KEY_ERR_STR_STR = "err_str"
const RESPONSE_KEY_DATA_STR = "data"
const LOG_KEY_LEVEL_STR = "level"
const LOG_KEY_ELEMENT_STR = "element"
const LOG_KEY_MESSAGE_STR = "msg"
const LOG_KEY_HOST_STR = "host"
const DATA_KEY_TIMESTAMP_STR = "timestamp"

struct _element_name
    str::Cstring
    len::Csize_t
end

struct _element_response_info
    stream::Cstring
    last_id::NTuple{32, UInt8}
end

struct redisReadTask
    type::Cint
    elements::Cint
    idx::Cint
    obj::Ptr{Cvoid}
    parent::Ptr{redisReadTask}
    privdata::Ptr{Cvoid}
end

struct redisReplyObjectFunctions
    createString::Ptr{Cvoid}
    createArray::Ptr{Cvoid}
    createInteger::Ptr{Cvoid}
    createNil::Ptr{Cvoid}
    freeObject::Ptr{Cvoid}
end

struct redisReader
    err::Cint
    errstr::NTuple{128, UInt8}
    buf::Cstring
    pos::Csize_t
    len::Csize_t
    maxbuf::Csize_t
    rstack::NTuple{9, redisReadTask}
    ridx::Cint
    reply::Ptr{Cvoid}
    fn::Ptr{redisReplyObjectFunctions}
    privdata::Ptr{Cvoid}
end

@cenum redisConnectionType::UInt32 begin
    REDIS_CONN_TCP = 0
    REDIS_CONN_UNIX = 1
end


struct ANONYMOUS5_tcp
    host::Cstring
    source_addr::Cstring
    port::Cint
end

struct ANONYMOUS6_unix_sock
    path::Cstring
end

struct redisContext
    err::Cint
    errstr::NTuple{128, UInt8}
    fd::Cint
    flags::Cint
    obuf::Cstring
    reader::Ptr{redisReader}
    connection_type::redisConnectionType
    timeout::Ptr{timeval}
    tcp::ANONYMOUS5_tcp
    unix_sock::ANONYMOUS6_unix_sock
end

struct element_command
    name::Cstring
    cb::Ptr{Cvoid}
    cleanup::Ptr{Cvoid}
    timeout::Cint
    user_data::Ptr{Cvoid}
    next::Ptr{element_command}
end

struct _element_command_info
    stream::Cstring
    last_id::NTuple{32, UInt8}
    ctx::Ptr{redisContext}
    hash::NTuple{256, Ptr{element_command}}
end

struct Element
    name::_element_name
    response::_element_response_info
    command::_element_command_info
end

@cenum atom_error_t::UInt32 begin
    ATOM_NO_ERROR = 0
    ATOM_INTERNAL_ERROR = 1
    ATOM_REDIS_ERROR = 2
    ATOM_COMMAND_NO_ACK = 3
    ATOM_COMMAND_NO_RESPONSE = 4
    ATOM_COMMAND_INVALID_DATA = 5
    ATOM_COMMAND_UNSUPPORTED = 6
    ATOM_CALLBACK_FAILED = 7
    ATOM_SERIALIZATION_ERROR = 8
    ATOM_DESERIALIZATION_ERROR = 9
    ATOM_LANGUAGE_ERRORS_BEGIN = 100
    ATOM_USER_ERRORS_BEGIN = 1000
end

@cenum cmd_keys_t::UInt32 begin
    CMD_KEY_ELEMENT = 0
    CMD_KEY_CMD = 1
    CMD_KEY_DATA = 2
    CMD_N_KEYS = 3
end

@cenum stream_keys_t::UInt32 begin
    STREAM_KEY_ELEMENT = 0
    STREAM_KEY_ID = 1
    STREAM_N_KEYS = 2
end

@cenum ack_keys_t::UInt32 begin
    ACK_KEY_TIMEOUT = 2
    ACK_N_KEYS = 3
end

@cenum command_keys_t::UInt32 begin
    RESPONSE_KEY_CMD = 2
    RESPONSE_KEY_ERR_CODE = 3
    RESPONSE_KEY_ERR_STR = 4
    RESPONSE_KEY_DATA = 5
    RESPONSE_N_KEYS = 6
end

@cenum atom_log_keys_t::UInt32 begin
    LOG_KEY_LEVEL = 0
    LOG_KEY_ELEMENT = 1
    LOG_KEY_MESSAGE = 2
    LOG_KEY_HOST = 3
    LOG_N_KEYS = 4
end

@cenum data_keys_t::UInt32 begin
    DATA_KEY_TIMESTAMP = 0
    DATA_N_ADDITIONAL_KEYS = 1
end


struct atom_list_node
    name::Cstring
    next::Ptr{atom_list_node}
end

const ELEMENT_COMMAND_HASH_N_BINS = 256
const ELEMENT_COMMAND_LOOP_NO_TIMEOUT = 0
const ELEMENT_ENTRY_READ_LOOP_FOREVER = 0
const ENTRY_READ_SINCE_BEGIN_BLOCKING_WITH_NEWEST_ID = "\$"
const ENTRY_READ_SINCE_BEGIN_WITH_OLDEST_ID = "0"

struct redisReply
    type::Cint
    integer::Clonglong
    len::Csize_t
    str::Cstring
    elements::Csize_t
    element::Ptr{Ptr{redisReply}}
end

struct redis_xread_kv_item
    key::Cstring
    key_len::Csize_t
    found::Bool
    reply::Ptr{redisReply}
end

struct element_entry_read_info
    element::Cstring
    stream::Cstring
    kv_items::Ptr{redis_xread_kv_item}
    n_kv_items::Csize_t
    user_data::Ptr{Cvoid}
    response_cb::Ptr{Cvoid}
    items_to_read::Csize_t
    items_read::Csize_t
    xreads::Csize_t
end

const ELEMENT_DATA_WRITE_DEFAULT_TIMESTAMP = 0
const ELEMENT_DATA_WRITE_DEFAULT_MAXLEN = 1024

struct redis_xadd_info
    key::Cstring
    key_len::Csize_t
    data::Ptr{UInt8}
    data_len::Csize_t
end

struct element_entry_write_info
    items::Ptr{redis_xadd_info}
    n_items::Csize_t
    stream::NTuple{32, UInt8}
end

const REDIS_DEFAULT_LOCAL_SOCKET = "/shared/redis.sock"
const REDIS_DEFAULT_REMOTE_ADDR = "127.0.0.1"
const REDIS_DEFAULT_REMOTE_PORT = 6379
const STREAM_ID_BUFFLEN = 32

# Skipping MacroDefinition: CONST_STRLEN ( x ) ( sizeof ( x ) - 1 )

const REDIS_XREAD_BLOCK_INDEFINITE = 0
const REDIS_XREAD_DONTBLOCK = -1
const REDIS_XREAD_NOMAXCOUNT = 0
const REDIS_XADD_NO_MAXLEN = -1

struct redis_stream_info
    name::Cstring
    data_cb::Ptr{Cvoid}
    last_id::NTuple{32, UInt8}
    user_data::Ptr{Cvoid}
    items_read::Csize_t
end

struct ANONYMOUS1_ev
    data::Ptr{Cvoid}
    addRead::Ptr{Cvoid}
    delRead::Ptr{Cvoid}
    addWrite::Ptr{Cvoid}
    delWrite::Ptr{Cvoid}
    cleanup::Ptr{Cvoid}
end

const redisCallbackFn = Cvoid

struct redisCallback
    next::Ptr{redisCallback}
    fn::Ptr{redisCallbackFn}
    pending_subs::Cint
    privdata::Ptr{Cvoid}
end

struct redisCallbackList
    head::Ptr{redisCallback}
    tail::Ptr{redisCallback}
end

struct dictEntry
    key::Ptr{Cvoid}
    val::Ptr{Cvoid}
    next::Ptr{dictEntry}
end

struct dictType
    hashFunction::Ptr{Cvoid}
    keyDup::Ptr{Cvoid}
    valDup::Ptr{Cvoid}
    keyCompare::Ptr{Cvoid}
    keyDestructor::Ptr{Cvoid}
    valDestructor::Ptr{Cvoid}
end

struct dict
    table::Ptr{Ptr{dictEntry}}
    type::Ptr{dictType}
    size::Culong
    sizemask::Culong
    used::Culong
    privdata::Ptr{Cvoid}
end

struct ANONYMOUS2_sub
    invalid::redisCallbackList
    channels::Ptr{dict}
    patterns::Ptr{dict}
end

const redisDisconnectCallback = Cvoid
const redisConnectCallback = Cvoid

struct redisAsyncContext
    c::redisContext
    err::Cint
    errstr::Cstring
    data::Ptr{Cvoid}
    ev::ANONYMOUS1_ev
    onDisconnect::Ptr{redisDisconnectCallback}
    onConnect::Ptr{redisConnectCallback}
    replies::redisCallbackList
    sub::ANONYMOUS2_sub
end

struct ANONYMOUS3_ev
    data::Ptr{Cvoid}
    addRead::Ptr{Cvoid}
    delRead::Ptr{Cvoid}
    addWrite::Ptr{Cvoid}
    delWrite::Ptr{Cvoid}
    cleanup::Ptr{Cvoid}
end

struct ANONYMOUS4_sub
    invalid::redisCallbackList
    channels::Ptr{dict}
    patterns::Ptr{dict}
end

const DICT_OK = 0
const DICT_ERR = 1

# Skipping MacroDefinition: DICT_NOTUSED ( V ) ( ( void ) V )

const DICT_HT_INITIAL_SIZE = 4

# Skipping MacroDefinition: dictFreeEntryVal ( ht , entry ) if ( ( ht ) -> type -> valDestructor ) ( ht ) -> type -> valDestructor ( ( ht ) -> privdata , ( entry ) -> val )
# Skipping MacroDefinition: dictSetHashVal ( ht , entry , _val_ ) do { if ( ( ht ) -> type -> valDup ) entry -> val = ( ht ) -> type -> valDup ( ( ht ) -> privdata , _val_ ) ; else entry -> val = ( _val_ ) ; \
#} while ( 0 )
# Skipping MacroDefinition: dictFreeEntryKey ( ht , entry ) if ( ( ht ) -> type -> keyDestructor ) ( ht ) -> type -> keyDestructor ( ( ht ) -> privdata , ( entry ) -> key )
# Skipping MacroDefinition: dictSetHashKey ( ht , entry , _key_ ) do { if ( ( ht ) -> type -> keyDup ) entry -> key = ( ht ) -> type -> keyDup ( ( ht ) -> privdata , _key_ ) ; else entry -> key = ( _key_ ) ; \
#} while ( 0 )
# Skipping MacroDefinition: dictCompareHashKeys ( ht , key1 , key2 ) ( ( ( ht ) -> type -> keyCompare ) ? ( ht ) -> type -> keyCompare ( ( ht ) -> privdata , key1 , key2 ) : ( key1 ) == ( key2 ) )
# Skipping MacroDefinition: dictHashKey ( ht , key ) ( ht ) -> type -> hashFunction ( key )
# Skipping MacroDefinition: dictGetEntryKey ( he ) ( ( he ) -> key )
# Skipping MacroDefinition: dictGetEntryVal ( he ) ( ( he ) -> val )
# Skipping MacroDefinition: dictSlots ( ht ) ( ( ht ) -> size )
# Skipping MacroDefinition: dictSize ( ht ) ( ( ht ) -> used )

struct dictIterator
    ht::Ptr{dict}
    index::Cint
    entry::Ptr{dictEntry}
    nextEntry::Ptr{dictEntry}
end

const HIREDIS_MAJOR = 0
const HIREDIS_MINOR = 13
const HIREDIS_PATCH = 3
const HIREDIS_SONAME = 0.13
const REDIS_BLOCK = 0x01
const REDIS_CONNECTED = 0x02
const REDIS_DISCONNECTING = 0x04
const REDIS_FREEING = 0x08
const REDIS_IN_CALLBACK = 0x10
const REDIS_SUBSCRIBED = 0x20
const REDIS_MONITORING = 0x40
const REDIS_REUSEADDR = 0x80
const REDIS_KEEPALIVE_INTERVAL = 15
const REDIS_CONNECT_RETRIES = 10
const REDIS_ERR = -1
const REDIS_OK = 0
const REDIS_ERR_IO = 1
const REDIS_ERR_EOF = 3
const REDIS_ERR_PROTOCOL = 4
const REDIS_ERR_OOM = 5
const REDIS_ERR_OTHER = 2
const REDIS_REPLY_STRING = 1
const REDIS_REPLY_ARRAY = 2
const REDIS_REPLY_INTEGER = 3
const REDIS_REPLY_NIL = 4
const REDIS_REPLY_STATUS = 5
const REDIS_REPLY_ERROR = 6
const REDIS_READER_MAX_BUF = 1024 * 16

# Skipping MacroDefinition: redisReaderSetPrivdata ( _r , _p ) ( int ) ( ( ( redisReader * ) ( _r ) ) -> privdata = ( _p ) )
# Skipping MacroDefinition: redisReaderGetObject ( _r ) ( ( ( redisReader * ) ( _r ) ) -> reply )
# Skipping MacroDefinition: redisReaderGetError ( _r ) ( ( ( redisReader * ) ( _r ) ) -> errstr )

const SDS_MAX_PREALLOC = 1024 * 1024
const SDS_TYPE_5 = 0
const SDS_TYPE_8 = 1
const SDS_TYPE_16 = 2
const SDS_TYPE_32 = 3
const SDS_TYPE_64 = 4
const SDS_TYPE_MASK = 7
const SDS_TYPE_BITS = 3

# Skipping MacroDefinition: SDS_HDR_VAR ( T , s ) struct sdshdr ## T * sh = ( struct sdshdr ## T * ) ( ( s ) - ( sizeof ( struct sdshdr ## T ) ) ) ;
# Skipping MacroDefinition: SDS_HDR ( T , s ) ( ( struct sdshdr ## T * ) ( ( s ) - ( sizeof ( struct sdshdr ## T ) ) ) )
# Skipping MacroDefinition: SDS_TYPE_5_LEN ( f ) ( ( f ) >> SDS_TYPE_BITS )

const sds = Cstring
const s_malloc = malloc
const s_realloc = realloc
const s_free = free

LANG = "Python"
ACK_TIMEOUT = 1000
RESPONSE_TIMEOUT = 1000
STREAM_LEN = 1024
MAX_BLOCK = 999999999999999999
DEFAULT_REDIS_PORT = 6379
DEFAULT_METRICS_PORT = 6380
HEALTHCHECK_RETRY_INTERVAL = 5
REDIS_PIPELINE_POOL_SIZE = 20
DEFAULT_REDIS_SOCKET = "/shared/redis.sock"
DEFAULT_METRICS_SOCKET = "/shared/metrics.sock"
HEALTHCHECK_COMMAND = "healthcheck"
VERSION_COMMAND = "version"
COMMAND_LIST_COMMAND = "command_list"
VERSION = "1.7.0"

# Error codes
ATOM_NO_ERROR = 0
ATOM_INTERNAL_ERROR = 1
ATOM_REDIS_ERROR = 2
ATOM_COMMAND_NO_ACK = 3
ATOM_COMMAND_NO_RESPONSE = 4
ATOM_COMMAND_INVALID_DATA = 5
ATOM_COMMAND_UNSUPPORTED = 6
ATOM_CALLBACK_FAILED = 7
ATOM_LANGUAGE_ERRORS_BEGIN = 100
ATOM_USER_ERRORS_BEGIN = 1000

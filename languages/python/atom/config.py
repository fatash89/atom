from enum import Enum

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

# Reserved Commands
HEALTHCHECK_COMMAND = "healthcheck"
VERSION_COMMAND = "version"
COMMAND_LIST_COMMAND = "command_list"
RESERVED_COMMANDS = [COMMAND_LIST_COMMAND, VERSION_COMMAND, HEALTHCHECK_COMMAND]

# Parameters
OVERRIDE_PARAM_FIELD = "override"
SERIALIZATION_PARAM_FIELD = "ser"
RESERVED_PARAM_FIELDS = [OVERRIDE_PARAM_FIELD, SERIALIZATION_PARAM_FIELD]

# Metrics
METRICS_ELEMENT_LABEL = "element"
METRICS_TYPE_LABEL = "type"
METRICS_HOST_LABEL = "container"
METRICS_ATOM_VERSION_LABEL = "version"
METRICS_SUBTYPE_LABEL = "subtype"
METRICS_DEVICE_LABEL = "device"
METRICS_LANGUAGE_LABEL = "language"
METRICS_LEVEL_LABEL = "level"
METRICS_AGGREGATION_LABEL = "agg"
METRICS_AGGREGATION_TYPE_LABEL = "agg_type"
# Metrics default retention -- 1 hour of raw data
METRICS_DEFAULT_RETENTION = 3600000
# Metrics default aggregation rules
METRICS_DEFAULT_AGG_TIMING = [
    # Keep data in 10m buckets for 3 days
    (600000, 259200000),
    # Then keep data in 1h buckets for 30 days
    (3600000, 2592000000),
]

# Queue metrics
METRICS_QUEUE_TYPE = "queue"
METRICS_FIFO_QUEUE_TYPE = "fifo"
METRICS_PRIO_QUEUE_TYPE = "prio"

# Shared queue metrics strings
METRICS_QUEUE_SIZE = "size"
METRICS_QUEUE_PUT = "put"
METRICS_QUEUE_GET = "get"
METRICS_QUEUE_PRUNED = "pruned"
METRICS_QUEUE_GET_DATA = "get_data"
METRICS_QUEUE_GET_EMPTY = "get_empty"

# Prio queue only metrics strings
METRICS_PRIO_QUEUE_GET_N = "get_n"
METRICS_PRIO_QUEUE_GET_PRIO = "get_prio"
METRICS_PRIO_QUEUE_PUT_PRIO = "put_prio"
METRICS_PRIO_QUEUE_PRUNE_PRIO = "prune_prio"

# All queue shared keys
METRICS_QUEUE_SHARED_KEYS = [
    METRICS_QUEUE_SIZE,
    METRICS_QUEUE_PUT,
    METRICS_QUEUE_GET,
    METRICS_QUEUE_PRUNED,
    METRICS_QUEUE_GET_DATA,
    METRICS_QUEUE_GET_EMPTY,
    METRICS_PRIO_QUEUE_GET_N,
    METRICS_PRIO_QUEUE_GET_PRIO,
    METRICS_PRIO_QUEUE_PUT_PRIO,
    METRICS_PRIO_QUEUE_PRUNE_PRIO,
]

# Queue config
FIFO_QUEUE_DEFAULT_MAX_LEN = 1000
PRIO_QUEUE_DEFAULT_MAX_LEN = 1000


# Metrics logging levels
class MetricsLevel(Enum):
    EMERG = 0
    ALERT = 1
    CRIT = 2
    ERR = 3
    WARNING = 4
    NOTICE = 5
    INFO = 6
    TIMING = 7
    DEBUG = 8


# Logging constants
LOG_DEFAULT_FILE_SIZE = 2000
LOG_DEFAULT_LEVEL = "INFO"

VERSION = "2.0.0"

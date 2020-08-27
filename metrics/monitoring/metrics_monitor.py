# Simple Python job that will monitor system-level
#   metrics in Atom and then write them to our metrics
#   instance. This is how we will convert system stats
#   into redis time series datapoints.

from atom import Element, MetricsLevel
from atom.config import (
    METRICS_ELEMENT_LABEL, METRICS_TYPE_LABEL, METRICS_HOST_LABEL,
    METRICS_DEVICE_LABEL, METRICS_LANGUAGE_LABEL, METRICS_ATOM_VERSION_LABEL,
    METRICS_LEVEL_LABEL, METRICS_SUBTYPE_LABEL
)
from atom.config import LANG, VERSION
from collections import defaultdict
import psutil
import time
import os

# Which /proc/ to read to get stats. Will default to the /proc/ but this
#   will only give process-level stats for the container. Mount in the
#   host procfs (BE SURE TO DO THIS READ-ONLY) and switch the location
psutil.PROCFS_PATH = os.getenv('METRICS_MONITOR_PROCFS', '/proc')

# How often to poll for monitoring -- every 10s by default
METRICS_MONITOR_INTERVAL = int(os.getenv('METRICS_MONITOR_INTERVAL', '10'))

# How often to retain performance metrics monitoring
METRICS_MONITOR_RETENTION = 86400000

#
# Key Dictionaries
#

# CPU dictionaries
cpu_times_metrics_keys = {}
cpu_pct_metrics_keys = {}
cpu_stats_metrics_keys = {}
cpu_freq_metrics_keys = {}

# Memory dictionaries
memory_virtual_metrics_keys = {}
memory_swap_metrics_keys = {}

# Disk dictaionaries
disk_metrics_usage_keys = defaultdict(lambda: {})
disk_metrics_io_keys = defaultdict(lambda: {})

# Network dictionaries
network_metrics_io_keys = defaultdict(lambda : {})
network_metrics_status_keys = defaultdict(lambda: {})

# Sensor dictionaries
sensors_metrics_status_keys = defaultdict(lambda : {})

#
# Label/Key Strings
#

# CPU strings
CPU_PREFIX = "cpu"
CPU_TIMES_PREFIX = "times"
CPU_PCT_PREFIX = "pct"
CPU_STATS_PREFIX = "stats"
CPU_FREQ_PREFIX = "freq"

# Memory strings
MEMORY_PREFIX = "memory"
MEMORY_VIRTUAL_PREFIX = "virt"
MEMORY_SWAP_PREFIX = "swap"

# Disk strings
DISK_PREFIX = "disk"
DISK_USAGE_PREFIX = "usage"
DISK_IO_PREFIX = "io"

# Network strings
NETWORK_PREFIX = "net"
NETWORK_IO_PREFIX = "io"
NETWORK_KIND_PREFIX = "kind"
NETWORK_METRICS_KINDS = ("tcp", "udp", "unix",)
NETWORK_PROCESS_PREFIX = "process"
NETWORK_REMOTE_PREFIX = "remote"

# Sensor strings
SENSOR_PREFIX = "sensor"
SENSOR_TEMP_PREFIX = "temp"

# Process strings
PROCESS_PREFIX = "process"
PROCESS_THREAD_PREFIX = "thread"

# Timing strings
TIMING_PREFIX = "timing"

def metrics_add_no_create(element, value, m_type, *m_subtypes, pipeline=None):
    """
    Call add on a metric without having created it. This is useful
    for transient-type metrics which you can't initialize beforehand. One
    downside of this, though, is that we can't do effective aggregation
    """

    # Make the key and labels. We have to use internal functions within
    #   the element to do this as we're not encouraged to use this API
    #   to mimic similar results to the encouraged metrics API
    key_str = element._make_metric_id(element.name, m_type, *m_subtypes)
    labels = element._metrics_add_default_labels({}, MetricsLevel.INFO, m_type, *m_subtypes)

    # Write out the metric
    element.metrics_add(key_str, value, labels=labels, enforce_exists=False, pipeline=pipeline)

def metrics_get_process_name(process):
    """
    Gets the name for a passed psutil Process object. This is surprisingly
    tricky -- there are a bunch of edge cases to consider in terms of delivering
    something useful
    """
    def sanitize_process_name(name):
        return name.replace(' ', '').replace('(', '').replace(')', '').replace(',', '')

    name = f"{process.pid}"

    cmdline = process.cmdline()
    if cmdline:
        for val in cmdline[:2]:
            name += f":{sanitize_process_name(val)}"
    else:
        procname = process.name()
        if procname:
            name += f":{procname}"
        if name is None:
            name += ":none"

    return name


def cpu_metrics_init(element):
    """
    Initialize all of the CPU metrics we'll be tracking
    """

    def cpu_metrics_create_cpu_times(*keys):
        for key in keys:
            cpu_times_metrics_keys[key] = element.metrics_create(
                MetricsLevel.INFO,
                CPU_PREFIX, CPU_TIMES_PREFIX, key,
                agg_types=["SUM"]
            )

    def cpu_metrics_create_cpu_pct(key):
        cpu_pct_metrics_keys[key] = element.metrics_create(
            MetricsLevel.INFO,
            CPU_PREFIX, CPU_PCT_PREFIX, key,
            agg_types=["MIN", "MAX", "AVG"]
        )

    def cpu_metrics_create_cpu_stats(*keys):
        for key in keys:
            cpu_stats_metrics_keys[key] = element.metrics_create(
                MetricsLevel.INFO,
                CPU_PREFIX, CPU_STATS_PREFIX, key,
                agg_types=["SUM"]
            )

    def cpu_metrics_create_cpu_freq(key):
        cpu_freq_metrics_keys[key] = element.metrics_create(
            MetricsLevel.INFO,
            CPU_PREFIX, CPU_FREQ_PREFIX, key,
            agg_types=["MIN", "MAX", "AVG"]
        )

    #
    # Metrics from psutil.cpu_times()
    #
    cpu_metrics_create_cpu_times(
        "user", "nice", "system", "idle", "iowait", "irq",
        "softirq", "steal", "guest", "guest_nice"
    )

    #
    # Metrics from psutil.cpu_percent and psutil.cpu_freq
    #
    cpu_count = psutil.cpu_count()
    for cpu in range(cpu_count):
        cpu_metrics_create_cpu_pct(str(cpu))
        cpu_metrics_create_cpu_freq(str(cpu))

    #
    # Metrics from psutil.cpu_stats
    #
    cpu_metrics_create_cpu_stats(
        "ctx_switches", "interrupts", "soft_interrupts"
    )


def cpu_metrics_update(element, pipeline):
    """
    Update the CPU metrics on the pipeline
    """

    def cpu_metrics_update_cpu_times(*keys):
        for key in keys:
            element.metrics_add(
                cpu_times_metrics_keys[key],
                getattr(cpu_times, key),
                pipeline=pipeline
            )

    def cpu_metrics_update_cpu_stats(*keys):
        for key in keys:
            element.metrics_add(
                cpu_stats_metrics_keys[key],
                getattr(cpu_stats, key),
                pipeline=pipeline
            )

    #
    # CPU time metrics
    #
    cpu_times = psutil.cpu_times()
    cpu_metrics_update_cpu_times(
        "user", "nice", "system", "idle", "iowait", "irq",
        "softirq", "steal", "guest", "guest_nice"
    )

    #
    # CPU utilization metrics
    #
    cpu_percent = psutil.cpu_percent(percpu=True)
    for i, pct in enumerate(cpu_percent):
        element.metrics_add(cpu_pct_metrics_keys[str(i)], pct, pipeline=pipeline)

    #
    # CPU stats metrics
    #
    cpu_stats = psutil.cpu_stats()
    cpu_metrics_update_cpu_stats(
        "ctx_switches", "interrupts", "soft_interrupts"
    )

    #
    # CPU frequency metrics
    #
    cpu_freq = psutil.cpu_freq(percpu=True)
    for i, freq in enumerate(cpu_freq):
        element.metrics_add(cpu_freq_metrics_keys[str(i)], freq.current, pipeline=pipeline)

def memory_metrics_init(element):
    """
    Initialize all of the memory metrics we'll be tracking
    """

    def memory_metrics_create_virtual(*keys):
        for key in keys:
            memory_virtual_metrics_keys[key] = element.metrics_create(
                MetricsLevel.INFO,
                MEMORY_PREFIX, MEMORY_VIRTUAL_PREFIX, key,
                agg_types=["MIN", "MAX", "AVG"]
            )

    def memory_metrics_create_swap(*keys):
        for key in keys:
            memory_swap_metrics_keys[key] = element.metrics_create(
                MetricsLevel.INFO,
                MEMORY_PREFIX, MEMORY_SWAP_PREFIX, key,
                agg_types=["MIN", "MAX", "AVG"]
            )

    memory_metrics_create_virtual(
        "total", "available", "percent", "used", "free", "active",
        "inactive", "buffers", "cached", "shared", "slab"
    )

    memory_metrics_create_swap(
        "total", "used", "free", "percent", "sin", "sout"
    )

def memory_metrics_update(element, pipeline):
    """
    Update all of the memory metrics we're tracking
    """

    def memory_metrics_update_virtual(*keys):
        for key in keys:
            element.metrics_add(
                memory_virtual_metrics_keys[key],
                getattr(virt_memory, key),
                pipeline=pipeline
            )

    def memory_metrics_update_swap(*keys):
        for key in keys:
            element.metrics_add(
                memory_swap_metrics_keys[key],
                getattr(swap_memory, key),
                pipeline=pipeline
            )

    virt_memory = psutil.virtual_memory()
    memory_metrics_update_virtual(
        "total", "available", "percent", "used", "free", "active",
        "inactive", "buffers", "cached", "shared", "slab"
    )

    swap_memory = psutil.swap_memory()
    memory_metrics_update_swap(
        "total", "used", "free", "percent", "sin", "sout"
    )

def disk_metrics_init(element):
    """
    Initialize all of the disk metrics we'll be tracking
    """

    def disk_metrics_create_usage(disk, device, *keys):
        for key in keys:
            disk_metrics_usage_keys[disk][key] = element.metrics_create(
                MetricsLevel.INFO,
                DISK_PREFIX, DISK_USAGE_PREFIX, disk, key, device,
                agg_types=["MIN", "MAX", "AVG"]
            )

    def disk_metrics_create_io(device, *keys):
        for key in keys:
            disk_metrics_io_keys[device][key] = element.metrics_create(
                MetricsLevel.INFO,
                DISK_PREFIX, DISK_IO_PREFIX, device, key,
                agg_types=["MIN", "MAX", "AVG"]
            )

    for disk in psutil.disk_partitions(all=True):
        disk_metrics_create_usage(
            disk.mountpoint.replace(',', '/'),
            disk.device if disk.device != '' else "default",
            "total", "used", "free", "percent"
        )

    for device in psutil.disk_io_counters(perdisk=True):
        disk_metrics_create_io(
            device,
            "read_count", "write_count", "read_bytes",
                "write_bytes", "read_time", "write_time"
        )

def disk_metrics_update(element, pipeline):
    """
    Update all of the disk metrics we'll be tracking
    """

    def disk_metrics_update_usage(disk, *keys):
        for key in keys:
            element.metrics_add(
                disk_metrics_usage_keys[disk][key],
                getattr(disk_usage, key),
                pipeline=pipeline
            )

    def disk_metrics_update_io(device, *keys):
        for key in keys:
            element.metrics_add(
                disk_metrics_io_keys[device][key],
                getattr(disk_io[device], key),
                pipeline=pipeline
            )

    for disk in psutil.disk_partitions(all=True):
        disk_usage = psutil.disk_usage(disk.mountpoint)
        disk_metrics_update_usage(
            disk.mountpoint.replace(',', '/'),
            "total", "used", "free", "percent"
        )

    disk_io = psutil.disk_io_counters(perdisk=True)
    for disk in disk_io:
        disk_metrics_update_io(
            disk,
            "read_count", "write_count", "read_bytes",
                "write_bytes", "read_time", "write_time"
        )

def network_metrics_init_nic(element, nic):
    """
    Create all of the network metrics for a given nic
    """

    def network_metrics_create_io(*keys):
        for key in keys:
            network_metrics_io_keys[nic][key] = element.metrics_create(
                MetricsLevel.INFO,
                NETWORK_PREFIX, NETWORK_IO_PREFIX, nic, key,
                agg_types=["SUM"]
            )

    network_metrics_create_io(
        nic,
        "bytes_sent", "bytes_recv", "packets_sent", "packets_recv",
            "errin", "errout", "dropin", "dropout"
    )

def network_metrics_init(element):
    """
    Initialize the network metrics
    """

    def network_metrics_create_kind(kind, *keys):
        for key in keys:
            key_str = str(key)
            network_metrics_status_keys[kind][key_str] = element.metrics_create(
                MetricsLevel.INFO,
                NETWORK_PREFIX, NETWORK_KIND_PREFIX, kind, key_str,
                agg_types=["AVG"]
            )

    # Initialize the NICs
    for nic in psutil.net_io_counters(pernic=True):
        network_metrics_init_nic(element, nic)

    # Now, we want to initialize all of the connection status metrics
    for kind in NETWORK_METRICS_KINDS:
        network_metrics_create_kind(
            kind,
            psutil.CONN_ESTABLISHED,
            psutil.CONN_SYN_SENT,
            psutil.CONN_SYN_RECV,
            psutil.CONN_FIN_WAIT1,
            psutil.CONN_FIN_WAIT2,
            psutil.CONN_TIME_WAIT,
            psutil.CONN_CLOSE,
            psutil.CONN_CLOSE_WAIT,
            psutil.CONN_LAST_ACK,
            psutil.CONN_LISTEN,
            psutil.CONN_CLOSING,
            psutil.CONN_NONE,
        )

#
# We want to log deltas on the network data, not the sum
#
network_data_last = None

def network_metrics_update(element, pipeline):
    """
    Update network metrics
    """
    global network_data_last

    def network_metrics_update_io(nic, *keys):
        if network_data_last is not None and nic in network_data_last:
            for key in keys:
                element.metrics_add(
                    network_metrics_io_keys[nic][key],
                    getattr(data[nic], key) - getattr(network_data_last[nic], key),
                    pipeline=pipeline
                )

    def network_metrics_update_kind(kind, counts, *keys):
        for key in keys:
            element.metrics_add(
                network_metrics_status_keys[kind][key],
                counts[key],
                pipeline=pipeline
            )

    # Get the data
    data = psutil.net_io_counters(pernic=True)

    # Noop over the NICs
    for nic in data:

        # If we haven't seen it before we need to initialize it.
        #   This can happen, they come and go
        if nic not in network_metrics_io_keys:
            network_metrics_init_nic(element, nic)

        network_metrics_update_io(
            nic,
            "bytes_sent", "bytes_recv", "packets_sent", "packets_recv",
                "errin", "errout", "dropin", "dropout"
        )

    # Update the network data
    network_data_last = data

    # Loop over the network kinds
    for kind in NETWORK_METRICS_KINDS:

        # Get the connection data
        data = psutil.net_connections(kind=kind)

        # Loop over the data and update by status count
        status_counts = defaultdict(int)
        pid_counts = defaultdict(int)
        remote_counts = defaultdict(int)
        for conn in data:
            status_counts[conn.status] += 1
            pid_counts[conn.pid] += 1
            if conn.raddr:
                remote_counts[f"{conn.raddr.ip}:{conn.raddr.port}"] += 1

        # Update the status counts
        network_metrics_update_kind(
            kind,
            status_counts,
            psutil.CONN_ESTABLISHED,
            psutil.CONN_SYN_SENT,
            psutil.CONN_SYN_RECV,
            psutil.CONN_FIN_WAIT1,
            psutil.CONN_FIN_WAIT2,
            psutil.CONN_TIME_WAIT,
            psutil.CONN_CLOSE,
            psutil.CONN_CLOSE_WAIT,
            psutil.CONN_LAST_ACK,
            psutil.CONN_LISTEN,
            psutil.CONN_CLOSING,
            psutil.CONN_NONE,
        )

        # Log network connections by PID
        for pid in pid_counts:
            if pid is not None:
                process = psutil.Process(pid)
                name = metrics_get_process_name(process)
            else:
                name = "__system__"
            metrics_add_no_create(
                element,
                pid_counts[pid],
                NETWORK_PREFIX,
                NETWORK_PROCESS_PREFIX,
                kind,
                name,
                pipeline=pipeline
            )

        # Log network connections by remote
        for remote in remote_counts:
            metrics_add_no_create(
                element,
                remote_counts[remote],
                NETWORK_PREFIX,
                NETWORK_REMOTE_PREFIX,
                kind,
                remote,
                pipeline=pipeline
            )

def sensors_metrics_init(element):
    """
    Initialize all of the metrics for sensors in the system
    """

    def sensors_metrics_create_item(item, sensors):
        for sensor in sensors:
            sensors_metrics_status_keys[item][sensor] = element.metrics_create(
                MetricsLevel.INFO,
                SENSOR_PREFIX, SENSOR_TEMP_PREFIX, item, sensor,
                agg_types=["MIN", "MAX", "AVG"]
            )

    data = psutil.sensors_temperatures()
    for item in data:
        sensors_metrics_create_item(item, [x.label if x.label else 'default' for x in data[item]])

def sensors_metrics_update(element, pipeline):
    """
    Update the temperature sensor readings
    """

    def sensors_metrics_update_item(item, sensor, val):
        element.metrics_add(
            sensors_metrics_status_keys[item][sensor],
            val,
            pipeline=pipeline
        )

    data = psutil.sensors_temperatures()
    for item in data:

        # Need to filter out duplicates -- apparently they're in there
        seen = []
        for sensor in data[item]:
            if sensor not in seen:
                sensors_metrics_update_item(item, sensor.label if sensor.label else 'default', sensor.current)
                seen.append(sensor)

def processes_metrics_init(element):
    """
    Initialization for per-process metrics -- noting to do for now
    """
    pass

#
# Static/global variables needed for call-to-call process monitoring
#
cpu_times_time_last = None
cpu_times_system_last = None
cpu_times_user_last = None
cpu_times_iowait_last = None
thread_times_user_last = None
thread_times_system_last = None

def process_metrics_update(element, pipeline):
    """
    Update metrics on a per-process basis
    """

    # Globals we'll be using
    global cpu_times_time_last
    global cpu_times_system_last
    global cpu_times_user_last
    global cpu_times_iowait_last
    global thread_times_user_last
    global thread_times_system_last

    def process_metrics_update_item(item_dict, info):
        for proc in item_dict:
            metrics_add_no_create(
                element, item_dict[proc], PROCESS_PREFIX, proc, info, pipeline=pipeline
            )

    def process_metrics_cpu_time_to_pct(curr, prev):
        output = {}

        # Loop over current processes
        for proc in curr:
            # If we've seen this process before
            if cpu_times_time_last and proc in cpu_times_time_last:
                # Calculate its metrics across the current runtime
                timedelta = (cpu_times_time[proc] - cpu_times_time_last[proc]) / 100.0
                output[proc] = (curr[proc] - prev[proc]) / timedelta

        return output

    def process_metrics_update_item_threaded(item_dict, info):
        for proc in item_dict:
            for thread in item_dict[proc]:
                metrics_add_no_create(
                    element, item_dict[proc][thread], PROCESS_PREFIX, proc, PROCESS_THREAD_PREFIX, thread, info, pipeline=pipeline
                )

    def process_metrics_cpu_time_to_pct_threaded(curr, prev):
        output = {}

        # Loop over processes
        for proc in curr:
            # If we've seen this process before
            if cpu_times_time_last and proc in cpu_times_time_last:
                # Make the new output dictionary
                output[proc] = {}
                # Loop over the process's threads
                for thread in curr[proc]:
                    # If we've seen this thread before
                    if thread in prev[proc]:
                        timedelta = (cpu_times_time[proc] - cpu_times_time_last[proc]) / 100.0
                        output[proc][thread] = (curr[proc][thread] - prev[proc][thread]) / timedelta

        return output

    # All of the metrics we're tracking on a per-process basis
    read_count = {}
    write_count = {}
    read_bytes = {}
    write_bytes = {}
    ctx_switches_voluntary = {}
    ctx_switches_involuntary = {}
    fds = {}
    cpu_times_time = {}
    cpu_times_system = {}
    cpu_times_user = {}
    cpu_times_iowait = {}
    thread_times_user = defaultdict(lambda: {})
    thread_times_system = defaultdict(lambda: {})
    mem_rss = {}
    mem_vms = {}

    # Loop over the processes
    for proc in psutil.process_iter():

        # Do the one-shot process optimization to get as much
        #   data as possible
        with proc.oneshot():
            name = metrics_get_process_name(proc)

            # IO counter data for the process
            io = proc.io_counters()
            read_count[name] = io.read_count
            write_count[name] = io.write_count
            read_bytes[name] = io.read_bytes
            write_bytes[name] = io.write_bytes

            # Context switches
            switches = proc.num_ctx_switches()
            ctx_switches_voluntary[name] = switches.voluntary
            ctx_switches_involuntary[name] = switches.involuntary

            # File descriptors
            fds[name] = proc.num_fds()

            # CPU
            cpu = proc.cpu_times()
            cpu_times_time[name] = time.time()
            cpu_times_system[name] = cpu.system
            cpu_times_user[name] = cpu.user
            cpu_times_iowait[name] = cpu.iowait

            # Thread CPU
            for thread in proc.threads():
                thread_times_user[name][thread.id] = thread.user_time
                thread_times_system[name][thread.id] = thread.system_time

            # Memory info
            mem = proc.memory_info()
            mem_rss[name] = mem.rss
            mem_vms[name] = mem.vms

    # Now, we want to make all of the metrics
    process_metrics_update_item(read_count, "read_count")
    process_metrics_update_item(write_count, "write_count")
    process_metrics_update_item(read_bytes, "read_bytes")
    process_metrics_update_item(write_bytes, "write_bytes")
    process_metrics_update_item(ctx_switches_voluntary, "ctx_switches_voluntary")
    process_metrics_update_item(ctx_switches_involuntary, "ctx_switches_involuntary")
    process_metrics_update_item(fds, "fds")
    process_metrics_update_item(
        process_metrics_cpu_time_to_pct(
            cpu_times_system,
            cpu_times_system_last
        ),
        "cpu_system"
    )
    process_metrics_update_item(
        process_metrics_cpu_time_to_pct(
            cpu_times_user,
            cpu_times_user_last
        ),
        "cpu_user"
    )
    process_metrics_update_item(
        process_metrics_cpu_time_to_pct(
            cpu_times_iowait,
            cpu_times_iowait_last
        ),
        "cpu_iowait"
    )
    process_metrics_update_item_threaded(
        process_metrics_cpu_time_to_pct_threaded(
            thread_times_user,
            thread_times_user_last
        ),
        "thread_user"
    )
    process_metrics_update_item_threaded(
        process_metrics_cpu_time_to_pct_threaded(
            thread_times_system,
            thread_times_system_last
        ),
        "thread_system"
    )
    process_metrics_update_item(mem_rss, "mem_rss")
    process_metrics_update_item(mem_vms, "mem_vms")

    # And update the last seen dictionaries
    cpu_times_time_last = cpu_times_time
    cpu_times_system_last = cpu_times_system
    cpu_times_user_last = cpu_times_user
    cpu_times_iowait_last = cpu_times_iowait
    thread_times_user_last = thread_times_user
    thread_times_system_last = thread_times_system

# Mainloop
if __name__ == '__main__':

    def initialize_timing_metric(metric):
        timing_metrics[metric] = element.metrics_create(
            MetricsLevel.TIMING,
            TIMING_PREFIX, metric,
            agg_types=["AVG", "MIN", "MAX"]
        )

    # Make the element
    element = None
    while True:
        element = Element('monitor')
        if element is not None:
            break

        print("Failed to create element! Waiting 10s")
        time.sleep(10)

    # Initialize all of the timing metrics
    timing_metrics = {}
    initialize_timing_metric("cpu")
    initialize_timing_metric("memory")
    initialize_timing_metric("disk")
    initialize_timing_metric("network")
    initialize_timing_metric("sensors")
    initialize_timing_metric("processes")
    initialize_timing_metric("redis")

    # Call all of the init functions
    print("Initializing...")
    cpu_metrics_init(element)
    memory_metrics_init(element)
    disk_metrics_init(element)
    network_metrics_init(element)
    sensors_metrics_init(element)
    processes_metrics_init(element)
    print("Initialized!")

    # Loop forever
    while True:
        # Sleep until the next time we should be monitoring
        time.sleep(METRICS_MONITOR_INTERVAL)

        pipeline = element.metrics_get_pipeline()
        if pipeline is None:
            print("Failed to get pipeline!")
            continue

        # Add in the stats
        print("Starting update...")
        element.metrics_timing_start(timing_metrics["cpu"])
        cpu_metrics_update(element, pipeline)
        element.metrics_timing_end(timing_metrics["cpu"], pipeline=pipeline)
        element.metrics_timing_start(timing_metrics["memory"])
        memory_metrics_update(element, pipeline)
        element.metrics_timing_end(timing_metrics["memory"], pipeline=pipeline)
        element.metrics_timing_start(timing_metrics["disk"])
        disk_metrics_update(element, pipeline)
        element.metrics_timing_end(timing_metrics["disk"], pipeline=pipeline)
        element.metrics_timing_start(timing_metrics["network"])
        network_metrics_update(element, pipeline)
        element.metrics_timing_end(timing_metrics["network"], pipeline=pipeline)
        element.metrics_timing_start(timing_metrics["sensors"])
        sensors_metrics_update(element, pipeline)
        element.metrics_timing_end(timing_metrics["sensors"], pipeline=pipeline)
        element.metrics_timing_start(timing_metrics["processes"])
        process_metrics_update(element, pipeline)
        element.metrics_timing_end(timing_metrics["processes"], pipeline=pipeline)
        print("Finished update!")

        # Execute the pipeline
        print("Writing metrics...")
        element.metrics_timing_start(timing_metrics["redis"])
        element.metrics_write_pipeline(pipeline)
        element.metrics_timing_end(timing_metrics["redis"])
        print("Metrics written!")

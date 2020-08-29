#
# create_dashboards.py
#   Uses jinja2 + json to read from a template file on disk
#   and create a set of dashboards for grafana. This is surprisingly
#   the best/recommended way to configure this -- there are a few YAML
#   options but they seem to be less fully featured.
#
# If wanting to add/change something in this, the recommended workflow is:
#   1. Change it in the grafana UI
#   2. Use grafana HTTP API: https://grafana.com/docs/grafana/latest/http_api/
#       to read out a JSON blob corresponding to what you did
#   3. Save the JSON blob as a jinja2 template in the templates folder in
#       this directory + jinja-fy it with variables you need
#   4. Add a section to this script that reads in the template and writes
#       out the settings.
#

import json
import requests
import os
import redis
import time
from jinja2 import FileSystemLoader, Environment, select_autoescape

GRAFANA_USER = os.getenv("GRAFANA_USER", "admin")
GRAFANA_PASSWORD = os.getenv("GRAFANA_PASSWORD", "admin")
GRAFANA_URL = f"http://{GRAFANA_USER}:{GRAFANA_PASSWORD}@{os.getenv('GRAFANA_URL', 'localhost:3001')}"

# Info to make all of the dashboards
METRICS_TIMING = [
    # Data bucketed by 10m, default show last hour
    (600000, "1h"),
    # Data bucketed by 1h, default show last 24 hours
    (3600000, "24h"),
    # Data bucketed by 24h, default show last 7 days
    (86400000, "7d"),
]

ATOM_SERVER_IP = os.getenv("ATOM_SERVER_IP", "localhost")
ATOM_SERVER_PORT = int(os.getenv("ATOM_SERVER_PORT", "6379"))
METRICS_SERVER_IP = os.getenv("METRICS_SERVER_IP", "localhost")
METRICS_SERVER_PORT = int(os.getenv("METRICS_SERVER_PORT", "6380"))
DATASOURCES = [
    ("Atom Nucleus", "redis-atom", f"{ATOM_SERVER_IP}:{ATOM_SERVER_PORT}"),
    ("Atom Metrics", "redis-metrics", f"{METRICS_SERVER_IP}:{METRICS_SERVER_PORT}"),
]

# List of system-level dashboards we want to make at boot
SYS_DASHBOARDS = ["cpu", "disk", "memory", "network"]

# Wait for grafana to come up
print("Waiting for Grafana to come up...")
while True:
    try:
        data = requests.get(GRAFANA_URL + "/api/health")
        if data.ok:
            break
    except:  # noqa: E722
        print("Grafana server not yet up, waiting")
        time.sleep(1)
print("Grafana up!")

# Get the template
templateLoader = FileSystemLoader(searchpath="./templates")
env = Environment(loader=templateLoader, autoescape=select_autoescape(["html", "xml"]))

# Create the datasources
print("Creating datasources...")
datasource_template = env.get_template("datasource.json.j2")
for source in DATASOURCES:
    data = requests.post(
        GRAFANA_URL + "/api/datasources",
        json=json.loads(
            datasource_template.render(
                name=source[1],
                redis_ip=source[2],
            )
        ),
    )
    if not data.ok:
        print(
            f"Failed to create datasource {source}: status: {data.status_code} response: {data.json()}"
        )

# Create the dashboards for the redises themselves
print("Creating Redis Overview Dashboards...")
overview_template = env.get_template("redis_overview.json.j2")
for source in DATASOURCES:
    data = requests.post(
        GRAFANA_URL + "/api/dashboards/db",
        json=json.loads(overview_template.render(name=source[0], datasource=source[1])),
    )
    if not data.ok:
        print(
            f"Failed to create overview dashboard for source {source}: "
            f"status: {data.status_code} response: {data.json()}"
        )

# Create system overview dashboards
print("Creating System Overview Dashboards...")
for sys_dash in SYS_DASHBOARDS:
    template = env.get_template(f"{sys_dash}.json.j2")

    for timing in [
        (None, None),
    ] + METRICS_TIMING:
        if timing[0] is not None:
            bucket = timing[0]
            agg_label = f"{timing[0] // (1000 * 60)}m"
            name = agg_label
            start_time = timing[1]
        else:
            bucket = 1000
            agg_label = "none"
            name = "live"
            start_time = "5m"

        data = requests.post(
            GRAFANA_URL + "/api/dashboards/db",
            json=json.loads(
                template.render(
                    name=f"System-{sys_dash}-{name}",
                    bucket=bucket,
                    agg_label=agg_label,
                    datasource="redis-metrics",
                    start_time=start_time,
                )
            ),
        )
        if not data.ok:
            print(
                f"Failed to create overview dashboard for source {source}: "
                f"status: {data.status_code} response: {data.json()}"
            )


# Figure out how many elements we have that support metrics
print("Searching for metrics elements...")
redis_client = redis.StrictRedis(host=METRICS_SERVER_IP, port=METRICS_SERVER_PORT)
metrics_keys = redis_client.keys()
metrics_elements = set()
for key in metrics_keys:
    element = key.decode("utf-8").split(":")[0]
    if element not in metrics_elements:
        metrics_elements.add(element)

# Create the dashboards for the elements
print(f"Setting up dashboards for elements: {metrics_elements}")
element_template = env.get_template("default_element.json.j2")
for element in metrics_elements:
    for timing in [
        (None, None),
    ] + METRICS_TIMING:
        if timing[0] is not None:
            bucket = timing[0]
            agg_label = f"{timing[0] // (1000 * 60)}m"
            name = agg_label
            start_time = timing[1]
        else:
            bucket = 1000
            agg_label = "none"
            name = "live"
            start_time = "5m"

        data = requests.post(
            GRAFANA_URL + "/api/dashboards/db",
            json=json.loads(
                element_template.render(
                    element=element,
                    bucket=bucket,
                    agg_label=agg_label,
                    name=name,
                    datasource="redis-metrics",
                    start_time=start_time,
                )
            ),
        )
        if not data.ok:
            print(
                f"Failed to create dashboard: status: {data.status_code} response: {data.json()}"
            )

# Create the home dashboard
print("Creating/Updating Home Dashboard...")
home_template = env.get_template("home.json.j2")
data = requests.post(
    GRAFANA_URL + "/api/dashboards/db",
    json=json.loads(home_template.render(datasource="redis-metrics")),
)
if not data.ok:
    print(
        f"Failed to create home dashboard: status: {data.status_code} response: {data.json()}"
    )

# Now we want to set the home dashboard as the default
data = requests.put(
    GRAFANA_URL + "/api/org/preferences", json={"homeDashboardId": data.json()["id"]}
)
if not data.ok:
    print(
        f"Failed to update home dashboard: status: {data.status_code} response: {data.json()}"
    )

print("Dashboard setup complete!")

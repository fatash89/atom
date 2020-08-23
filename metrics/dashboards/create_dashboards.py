#
# create_element_dashboards.py
#   Uses jinja2 + json to read from a template file on disk
#   and create a set of dashboards
#

import json
import requests
import os
import redis
from jinja2 import FileSystemLoader, Environment, PackageLoader, select_autoescape

GRAFANA_USER = "admin"
GRAFANA_PASSWORD = "admin"
GRAFANA_URL = f"http://{GRAFANA_USER}:{GRAFANA_PASSWORD}@{os.getenv('GRAFANA_URL', 'localhost:3000')}"

METRICS_DEFAULT_AGG_TIMING = [
    # Keep data in 10m buckets for 3 days
    (600000,  259200000),
    # Then keep data in 1h buckets for 30 days
    (3600000, 2592000000),
    # Then keep data in 1d buckets for 365 days
    (86400000, 31536000000),
]

ATOM_SERVER_IP = os.getenv("ATOM_SERVER_IP", "localhost")
ATOM_SERVER_PORT = int(os.getenv("ATOM_SERVER_PORT", "6379"))
METRICS_SERVER_IP = os.getenv("METRICS_SERVER_IP", "localhost")
METRICS_SERVER_PORT = int(os.getenv("METRICS_SERVER_PORT", "6380"))
DATASOURCES = [
    ("redis-atom",      f"{ATOM_SERVER_IP}:{ATOM_SERVER_PORT}"),
    ("redis-metrics",   f"{METRICS_SERVER_IP}:{METRICS_SERVER_PORT}")
]

# Get the template
templateLoader = FileSystemLoader(searchpath="./templates")
env = Environment(
    loader=templateLoader,
    autoescape=select_autoescape(['html', 'xml'])
)
template = env.get_template('default_element.json.j2')

# Create the datasources
print("Creating datasources...")
datasource_template = env.get_template('datasource.json.j2')
for source in DATASOURCES:
    data = requests.post(
        GRAFANA_URL + "/api/datasources",
        json=json.loads(
            datasource_template.render(
                name=source[0],
                redis_ip=source[1],
            )
        )
    )
    if not data.ok:
        print(f"Failed to create datasource: status: {data.status_code} response: {data.json()}")

# Figure out how many elements we have that support metrics
print("Searching for metrics elements...")
redis_client = redis.StrictRedis(host=METRICS_SERVER_IP, port=METRICS_SERVER_PORT)
metrics_keys = redis_client.keys()
metrics_elements = set()
for key in metrics_keys:
    element = key.decode('utf-8').split(":")[0]
    if element not in metrics_elements:
        metrics_elements.add(element)

# Create the dashboards for the elements
print(f"Setting up dashboards for elements: {metrics_elements}")
element_template = env.get_template('default_element.json.j2')
for element in metrics_elements:
    for timing in [(None, None),] + METRICS_DEFAULT_AGG_TIMING:
        if timing[0] is not None:
            bucket = timing[0]
            agg_label = f"{timing[0] // (1000 * 60)}m"
            name = agg_label
        else:
            bucket = 1000
            agg_label = "none"
            name = "live"

        data = requests.post(
            GRAFANA_URL + "/api/dashboards/db",
            json=json.loads(
                element_template.render(
                    element=element,
                    bucket=bucket,
                    agg_label=agg_label,
                    name=name
                )
            )
        )
        if not data.ok:
            print(f"Failed to create dashboard: status: {data.status_code} response: {data.json()}")

print("Dashboard setup complete!")

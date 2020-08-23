#
# create_element_dashboards.py
#   Uses jinja2 + json to read from a template file on disk
#   and create a set of dashboards
#

import json
import requests
import os
from jinja2 import FileSystemLoader, Environment, PackageLoader, select_autoescape

GRAFANA_USER = "admin"
GRAFANA_PASSWORD = "elementary"
GRAFANA_URL = f"http://{GRAFANA_USER}:{GRAFANA_PASSWORD}@{os.getenv('GRAFANA_SERVER', 'localhost:3000')}"

ELEMENTS = [
    "spec_robot",
    "defect-detection"
]

METRICS_DEFAULT_AGG_TIMING = [
    # Keep data in 10m buckets for 3 days
    (600000,  259200000),
    # Then keep data in 1h buckets for 30 days
    (3600000, 2592000000),
    # Then keep data in 1d buckets for 365 days
    (86400000, 31536000000),
]

DATASOURCES = [
    ("redis-atom",      os.getenv("ATOM_SERVER", "localhost:6379")),
    ("redis-metrics",   os.getenv("METRICS_SERVER", "localhost:6380"))
]

# Get the template
templateLoader = FileSystemLoader(searchpath="./templates")
env = Environment(
    loader=templateLoader,
    autoescape=select_autoescape(['html', 'xml'])
)
template = env.get_template('default_element.json.j2')

# Create the datasources
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

# Create the dashboards for the elements
element_template = env.get_template('default_element.json.j2')
for element in ELEMENTS:
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

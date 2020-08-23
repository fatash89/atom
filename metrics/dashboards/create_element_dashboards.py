#
# create_element_dashboards.py
#   Uses jinja2 + json to read from a template file on disk
#   and create a set of dashboards
#

import json
import requests
from jinja2 import FileSystemLoader, Environment, PackageLoader, select_autoescape
from atom import METRICS_DEFAULT_AGG_TIMING

GRAFANA_USER = "admin"
GRAFANA_PASSWORD = "elementary"
GRAFANA_URL = f"http://{GRAFANA_USER}:{GRAFANA_PASSWORD}@localhost:3001"

ELEMENTS = [
    "spec-robot",
    "defect-detection"
]

# Get the template
templateLoader = FileSystemLoader(searchpath="./templates")
env = Environment(
    loader=templateLoader,
    autoescape=select_autoescape(['html', 'xml'])
)
template = env.get_template('default_element.json.j2')

for element in ELEMENTS:
    for timing in METRICS_DEFAULT_AGG_TIMING:
        if timing[0] is not None:
            bucket = timing[0]
            agg_label = f"{timing[0] // (1000 * 60)}m"
        else:
            bucket = 1000
            agg_label = "none"

        requests.post(
            GRAFANA_URL + "/api/dadhboards/db",
            json=json.loads(
                template.render(
                    element='defect-detection',
                    bucket=bucket,
                    agg_label=agg_label
                )
            )
        )

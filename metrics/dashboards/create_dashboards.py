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
import time
import redis
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

# How long to wait between polls for checking elements
ELEMENT_POLL_S = 10


class DashboardAgent(object):
    """
    Class that implements creation and monitoring of dashboards
    """

    def __init__(self):
        """
        Create the class and initialize the template renderer
        """

        self.template_loader = FileSystemLoader(searchpath="./templates")
        self.env = Environment(
            loader=self.template_loader, autoescape=select_autoescape(["html", "xml"])
        )
        self.metrics_elements = set()

        # Make an element we'll use for monitoring other elements
        self.redis_client = redis.StrictRedis(
            host=METRICS_SERVER_IP, port=METRICS_SERVER_PORT
        )

    def run(self):
        """
        Run the agent. Go through creating all of the startup dashboards
        and settings, and then enter into a loop monitoring for new
        elements, and when seen, add their dashboards.
        """

        # Wait for grafana to come up s.t. we can connect
        self.wait_for_grafana()

        # Make all of the startup dashboards and settings
        self.create_datasources()
        self.create_redis_dashboards()
        self.create_system_dashboards()
        self.create_home_dashboard()

        # Loop indefinitely, checking for new elements we haven't seen, and when
        #   we do see them, making a dashboard for them
        while True:

            # Get the new elements
            new_elements = self.update_metrics_elements()

            # For each element in the list, make a dashboard
            for element in new_elements:
                self.create_element_dashboard(element)

            # And then sleep until the next polling time
            time.sleep(ELEMENT_POLL_S)

    def update_metrics_elements(self):
        """
        Query the metrics redis for the current elements. If we find a new
        one, add it to our list of known elements and then also add it to a list
        of new elements which we will return
        """

        new_elements = []
        cursor = 0

        while True:

            cursor, keys = self.redis_client.scan(cursor, match="*")

            # Take the keys we got back and see if they're new elements
            for key in keys:
                element = key.decode("utf-8").split(":")[0]
                if element not in self.metrics_elements:
                    new_elements.append(element)
                    self.metrics_elements.add(element)

            # When we get a cursor back of 0 then we are done
            if cursor == 0:
                break

        return new_elements

    def wait_for_grafana(self):
        """
        Block until grafana is up
        """

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

    def create_datasources(self):
        """
        Create the datasources to be used for the dashboards
        """

        # Create the datasources
        print("Creating datasources...")
        datasource_template = self.env.get_template("datasource.json.j2")
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

    def create_redis_dashboards(self):
        """
        Create the redis overview dashboards for both redises
        """

        # Create the dashboards for the redises themselves
        print("Creating Redis Overview Dashboards...")
        overview_template = self.env.get_template("redis_overview.json.j2")
        for source in DATASOURCES:
            data = requests.post(
                GRAFANA_URL + "/api/dashboards/db",
                json=json.loads(
                    overview_template.render(name=source[0], datasource=source[1])
                ),
            )
            if not data.ok:
                print(
                    f"Failed to create overview dashboard for source {source}: "
                    f"status: {data.status_code} response: {data.json()}"
                )

    def create_system_dashboards(self):
        """
        Create the system dashboards
        """

        # Create system overview dashboards
        print("Creating System Overview Dashboards...")
        for sys_dash in SYS_DASHBOARDS:
            template = self.env.get_template(f"{sys_dash}.json.j2")

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
                        f"Failed to create overview dashboard for {sys_dash}: "
                        f"status: {data.status_code} response: {data.json()}"
                    )

    def create_home_dashboard(self):
        """
        Create the home dashboard and set it as the default
        """

        # Create the home dashboard
        print("Creating/Updating Home Dashboard...")
        home_template = self.env.get_template("home.json.j2")
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
            GRAFANA_URL + "/api/org/preferences",
            json={"homeDashboardId": data.json()["id"]},
        )
        if not data.ok:
            print(
                f"Failed to update home dashboard: status: {data.status_code} response: {data.json()}"
            )

    def create_user_dashboards(self):
        """
        Create the user-specified dashboards
        """

        # Finally, we want to create all of the user-specified dashboards
        user_templateLoader = FileSystemLoader(searchpath="./user")
        user_env = Environment(
            loader=user_templateLoader, autoescape=select_autoescape(["html", "xml"])
        )
        user_dashboards = [x for x in os.listdir("./user") if x.endswith(".json.j2")]
        if len(user_dashboards) > 0:
            print(f"Found user-specified dashboards {user_dashboards}...")

            for dashboard in user_dashboards:
                print(f"Loading user-specified dashboard {dashboard}...")
                user_template = user_env.get_template(dashboard)
                data = requests.post(
                    GRAFANA_URL + "/api/dashboards/db",
                    json=json.loads(user_template.render(datasource="redis-metrics")),
                )
                if not data.ok:
                    print(
                        f"Failed to create user dashboard: {dashboard} status: {data.status_code} "
                        f"response: {data.json()}"
                    )
                else:
                    print(f"Loaded user-specified dashboard {dashboard}")
        else:
            print("No user-specified dashboards found!")

    def create_element_dashboard(self, element):
        """
        Create a dashboard for a new element we've seen
        """

        # Create the dashboards for the elements
        print(f"Setting up dashboard for element: {element}")
        element_template = self.env.get_template("default_element.json.j2")
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


if __name__ == "__main__":
    agent = DashboardAgent()
    agent.run()

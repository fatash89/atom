#
# save_dashboard.py
#   Program to be run that can query grafana for a dashboard
#   and then save it in a way s.t. it can be re-loaded on sunsequent
#   runs of the system
#

import argparse
import json
import os

import requests


def save_dashboard(dashboard, filename, directory, url, user, password):
    """
    Query grafana for a dashboard, remove the unnecessary JSON, abstract
    out anyything that will be templated (datasource name), and then save
    the dashboard to the specified folder.

    Args:
        dashboard (str): Grafana UID of the dashboard
        filename (str): Filename of the output dashboard. Will be saved with
                        extension '.json.j2'
        directory (str): Directory in which to put the output filename
        url (str): URL of the grafana server
        user (str): User to use for interacting with the grafana server
        password (str): Password to use for interacting with the grafana server
    """

    # Get the data
    data = requests.get(
        f"http://{user}:{password}@{url}/api/dashboards/uid/{dashboard}"
    )
    if not data.ok:
        print(
            f"Failed to get dashboard: status: {data.status_code}, response: {data.json()}"
        )
        return

    # Now we need to parse the data
    json_data = data.json()

    # Strip out the instance-specific fields
    del json_data["dashboard"]["id"]
    del json_data["dashboard"]["uid"]
    del json_data["meta"]

    # Abstract out the datasource
    for panel in json_data["dashboard"]["panels"]:
        if panel["datasource"] is not None:
            panel["datasource"] = "{{ datasource }}"

    # Now, we want to open the output file
    output_path = os.path.join(directory, f"{filename}.json.j2")
    with open(output_path, "w") as f:
        f.write(json.dumps(json_data, indent=4, sort_keys=True))

    # Note we saved the dashboard
    print(f"Saved dashboard uid {dashboard} to file {output_path}")


# Mainloop
if __name__ == "__main__":

    #
    # Make the argument parser
    #

    parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument(
        "--user",
        "-u",
        type=str,
        default=os.getenv("GRAFANA_USER", "admin"),
        help="User to log into grafana with",
    )
    parser.add_argument(
        "--password",
        "-p",
        type=str,
        default=os.getenv("GRAFANA_PASSWORD", "admin"),
        help="Password to log into grafana with",
    )
    parser.add_argument(
        "--serverurl",
        "-s",
        type=str,
        default=os.getenv("GRAFANA_URL", "localhost:3001"),
        help="Grafana server URL",
    )
    parser.add_argument(
        "--dashboard", "-d", type=str, required=True, help="ID of the dashboard to save"
    )
    parser.add_argument(
        "--name",
        "-n",
        type=str,
        required=True,
        help="Name of the file under which to save the dashboard",
    )
    parser.add_argument(
        "--folder",
        "-f",
        type=str,
        default="/metrics/dashboards/user",
        help="Folder in which to save the dashboard",
    )

    #
    # Parse the arguments
    #

    args = parser.parse_args()

    #
    # And save the dashboard
    #
    save_dashboard(
        args.dashboard, args.name, args.folder, args.serverurl, args.user, args.password
    )

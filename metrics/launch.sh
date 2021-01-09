#!/bin/bash

# Launch the grafana server
/run.sh &

# Create the dashboards and data sources. This will run indefinitely,
#   scanning for elements and adding their dashboards when created
cd dashboards && python3 create_dashboards.py

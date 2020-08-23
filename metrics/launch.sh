#!/bin/bash

# Launch the grafana server
/run.sh &

# Sleep for a few seconds to let it come up
sleep 5

# Create the dashboards and data sources
cd dashboards && python3 create_dashboards.py

# Hang infinitely
tail -f /dev/null

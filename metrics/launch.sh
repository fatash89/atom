#!/bin/bash

# Launch the grafana server
/run.sh &

# Create the dashboards and data sources
cd dashboards && python3 create_dashboards.py

# Hang infinitely
tail -f /dev/null

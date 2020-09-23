# User-supplied Dashboards

It's easy to create and save your own dashboards so that they're always present in the system. To do this, we use the `save_dashboard.py` utility present in this directory in order to query your currently running grafana for a dashboard by UID and save it to JSON in a folder of your choice.

## Saving your dashboards to your host machine

By default, dashboards will be saved to `/metrics/dashboards/user` within the docker container. You have a few options for then getting the dashboard out of the container and onto your host machine:

1. Map a folder from your host into `/metrics/dashboards/user` in your `docker-compose`. This can be done with a line similar to below in the `volumes` folder of your service that defines the metrics/grafana container:
```
    - "<host_path>:/metrics/dashboards/user"
```
2. Use `docker cp` to copy the saved dashboard out
```
docker cp <container_name>:/metrics/dashboards/user/<dashboard_name>.json.j2 .
```

## Loading dashboards at boot

Any dashboard created using the `save_dashboard.py` script can be auto-loaded at boot of the metrics container. At boot, the metrics container will search `/metrics/dashboards/user` for all `.json.j2` files and will import them into the newly launched grafana. The best way to handle this is to follow path (1) from above and have a directory on your host machine mapped into `/metrics/dashboards/user` in your metrics container via docker-compose. This way the output of the save is automatically loaded next time at boot!

Add a section similar to the below to the `volumes` section of your metrics/grafana container:

```
    - "<host_path>:/metrics/dashboards/user"
```

## Using `save_dashboard.py`

Dashboards can be saved in a fairly straightforward fashion:

```
docker exec -w /metrics/dashboards <metrics_contaner_name> python3 save_dashboard.py -d <dashboard_uid> -n <output_name>
```

The UID of the dashboard can be pulled directly from the URL you see in your browser when editing the dashboard (the `dashboard_uid` field in the example below):
```
http://localhost:3001/d/<dashboard_uid>/<dashboard_name>?orgId=<user_org>
```

The utility is fairly simple at the moment, and can get a good amount of its defaults from the environment variables already set for the `create_dashboards.py` script. Arguments are below:

```
usage: save_dashboard.py [-h] [--user USER] [--password PASSWORD] [--serverurl SERVERURL]
                         --dashboard DASHBOARD --name NAME [--folder FOLDER]

optional arguments:
  -h, --help            show this help message and exit
  --user USER, -u USER  User to log into grafana with
  --password PASSWORD, -p PASSWORD
                        Password to log into grafana with
  --serverurl SERVERURL, -s SERVERURL
                        Grafana server URL
  --dashboard DASHBOARD, -d DASHBOARD
                        ID of the dashboard to save
  --name NAME, -n NAME  Name of the file under which to save the dashboard
  --folder FOLDER, -f FOLDER
                        Folder in which to save the dashboard
```

Defaults are:

| Argument | Default |
|----------|---------|
| `--user` | `GRAFANA_USER` env var |
| `--password` | `GRAFANA_PASSWORD` env var |
| `--serverurl` | `GRAFANA_URL` env var |
| `--dashboard` | None, required |
| `--name` | None, required |
| `--folder` | `/metrics/dashboards/user` |

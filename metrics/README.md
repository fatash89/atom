# Metrics

This README covers the built-in metrics for Atom and overall metrics system architecture For information on how to use metrics or add your own custom metrics, please see the general documentation.

## Overview

The metrics system in Atom is built on Redis Time Series. With Redis Time Series we get efficient writes, auto-compaction and aggregation and quickand easy integration into grafana to visualize how your system is doing.

## Viewing Metrics

Viewing metrics can be done with the `metrics` container built from the dockerfile in this folder. It is available at `elementaryrobotics/metrics` and/or can be built with:
```
docker-compose build
```

This metrics container contains the following:
1. Grafana (it is based off of `grafana/grafana`)
2. The redis datasource for grafana, compiled from source. We're compiling from source as this is fairly bleeding-edge at this point and the official release process through grafana can take a few weeks.
3. Default dashboards for monitoring the nucleus and metrics redis servers
4. Default dashboards for monitoring elements that support the metrics instrumentaion (running atom v1.7.3+)
5. A small python script, [`create_dashboards.py`](dashboards/create_dashboards.py) which will set up all of the grafana dashboards for us.

After launching the container, you can see the metrics by logging into `localhost:3001` (or whichever port you have mapped the grafana server to). The default username is `admin` and password is `admin`. You'll be prompted to change the password after logging in for the first time.

### Grafana

Grafana is an open-source graphing tool that integrates nicely with redis thanks to the [Grafana Redis Datasource](https://github.com/RedisTimeSeries/grafana-redis-datasource). We can use Grafana to create dashboards that will show us our metrics from Redis Time Series along with other perhaps interesting system stats.

### `create_dashboards.py`

This Python script is launched at the boot of the metrics container and does the following:

1. Sets up all of the off-the-shelf always-on dashboards
2. Performs service discovery for all elements running the metrics APIs.
3. Sets up dashboards for all elements found in (2)
4. Sets up the default grafana dashboard

#### Adding/tweaking dashboards

The general process for adding/tweaking a dashboard in `create_dashboards.py` is:

1. Change it in the grafana UI
2. Use the grafana HTTP API: https://grafana.com/docs/grafana/latest/http_api/ to read out a JSON blob corresponding to what you did
3. Save the JSON blob as a jinja2 template in the templates folder in the `templates` directory + jinja-fy it with variables you need
4. Add a section to the script that reads in the template and writes out the settings.

This is a fairly annoying process, but seems to be the most fully-featured way to do things in Grafana. Grafana uses a SQLite DB backend and exposes some settings via YAML configs but seems to only give first-class support to their RESTful API. For example, the default dashboard can only be set via the RESTful API.

## Atom Automatic Metrics

### Overview

Just by using Atom, you get the following metrics (grouped by category). All metrics, by default are configured to store 100% of values written for the first 24 hours. They then will compact and downsample into the buckets below using rules described in the tables:

| Time Bucket | Retention |
|-------------|-----------|
| all | 1 day |
| 10 minutes | 3 days |
| 1 hour | 30 days |
| 24 hours | 365 days |

Metric keys will always begin with the element name, followed by the type and any additional (optional) subtypes.

### Labels

The labels below are applied on all metrics and can be used on `TS.MRANGE` queries using redis time series.

#### `level`

Default atom metrics follow a labeling system by severity so that you can quickly surface errors. This follows the standard severity

| Label | Description |
|-------|-------------|
| `EMERG` | Catastrophic failure |
| `ALERT` | Action must be taken immediately |
| `CRIT` | Hard errors |
| `ERROR` | General-purpose error |
| `WARN` | Not an error, but not good |
| `NOTICE` | Not a routine log, but nothing to worry about |
| `INFO` | Routine log |
| `TIMING` | Timing metrics -- useful to differentiate out s.t. all timing metrics for an element can be queried to see where it is spending its time |
| `DEBUG` | Useful for debug |

Severity is applied as a label to metrics under the `severity` key.

The default severity is set with the `ATOM_METRICS_LEVEL` environment variable. It should be set to the entry from the table. All metrics equal to and above (as seen in the table) in severity will then be logged. Default level is `TIMING`.

#### `type` and `subtype<n>`

The type of the metric will be equal to the first part of the metric key, `atom:<string>`. This allows us to query groups of similar but not identical metrics by atom function (command sending, handling, etc.). Types are added under the label `type`

Subtypes are any additional `<string>` values added onto the key. They are separated by `:` and appended onto the key. Subtypes are added under the label `subtype<x>`, where X is the index of the subtype.

The type is the first argument passed to `metrics_create`, subtypes `0` through `n` are automatically created from the remaining variadic arguments coming after the type that are passed to `metrics_create`.

#### `element`

Each metric also has a label under the `element` key.

#### `container`

This is equal to the `uname` returned from the OS. Should either be the container or computer name.

#### `device`

Set `ATOM_DEVICE_ID` to have all metrics populated with a device ID for a given device. This is useful if monitoring fleets of devices.

#### `language`

The language of the client logging the metric. This is useful for monitoring performance language-to-language.

#### `version`

The version of the client logging the metric. This is useful for monitoring performance version-to-version.

#### `agg`

The level of aggregation for the metric. Will be one of:

- `none`
- `10m`
- `60m`
- `1440m`

Depending on which of the three downsampled streams (or the original stream) that the metric belongs to.

### Metrics

This section contains all of the metrics that have been instrumented within Atom itself. It is not entirely complete, for now please see [`element.py`](../languages/python/atom/element.py) and refer to the source.

#### Command

| Type | Subtype(s) | Description | Severity | Additional Labels | Aggregation |
|------|------------|-------------|----------|-------------------|-------------|
| `atom:command` | `count:<command>` | How many times a particular element's particular command has been called | Info | None | sum |

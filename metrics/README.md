# Metrics

This README covers the built-in metrics for Atom and overall metrics system architecture For information on how to use metrics or add your own custom metrics, please see the general documentation.

## Overview

The metrics system in Atom is built on Redis Time Series. With Redis Time Series we get efficient writes, auto-compaction and aggregation and quickand easy integration into grafana to visualize how your system is doing.

## Grafana

Grafana is an open-source graphing tool that integrates nicely with redis thanks to the [Grafana Redis Datasource](https://github.com/RedisTimeSeries/grafana-redis-datasource). We can use Grafana to create dashboards that will show us our metrics from Redis Time Series along with other perhaps interesting system stats.

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

#### Severity

Default atom metrics follow a labeling system by severity so that you can quickly surface errors. This follows the standard severity

| Label | Description |
|-------|-------------|
| `emerg` | Catastrophic failure |
| `alert` | Action must be taken immediately |
| `crit` | Hard errors |
| `error` | General-purpose error |
| `warn` | Not an error, but not good |
| `notice` | Not a routine log, but nothing to worry about |
| `info` | Routine log |
| `debug` | Useful for debug |
| `timing` | Timing metrics -- useful to differentiate out s.t. all timing metrics for an element can be queried to see where it is spending its time |

Severity is applied as a label to metrics under the `severity` key.

#### Type and Subtype

The type of the metric will be equal to the first part of the metric key, `atom:<string>`. This allows us to query groups of similar but not identical metrics by atom function (command sending, handling, etc.). Types are added under the label `type`

Subtypes are any additional `<string>` values added onto the key. They are separated by `:` and appended onto the key. Subtypes are added under the label `subtype<x>`, where X is the index of the subtype.

#### Element

Each metric also has a label under the `element` key.

### Metrics

#### Command

| Type | Subtype(s) | Description | Severity | Additional Labels | Aggregation |
|------|------------|-------------|----------|-------------------|-------------|
| `atom:command` | `count:<command>` | How many times a particular element's particular command has been called | Info | None | sum |

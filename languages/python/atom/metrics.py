from __future__ import annotations

import time
from typing import Optional, cast

from redis.client import Pipeline
from redistimeseries.client import Pipeline as RedisTimeSeriesPipeline

from atom.config import (
    METRICS_LEVEL_LABEL,
    METRICS_SUBTYPE_LABEL,
    METRICS_TYPE_LABEL,
    MetricsLevel,
)
from atom.element import Element


class MetricsTimingCall(object):
    """
    Wrapper for making metrics timing calls
    """

    def __init__(
        self,
        helper_instance,
        element: Element,
        metric_key: str,
        pipeline: Pipeline = None,
    ):
        self.helper_instance = helper_instance
        self.element = element
        self.metric_key = metric_key
        self.time_start = time.monotonic()
        self.pipeline = pipeline

    def __enter__(self):
        return self.time_start

    def __exit__(self, type, value, traceback):
        self.helper_instance._log_metric_timing(
            self.element, self.metric_key, self.time_start, pipeline=self.pipeline
        )


class MetricsHelper(object):
    """
    Helper class for making metrics
    """

    def _set_metric_info(self, m_type: str, *m_subtypes: str) -> None:
        """
        Set the metric info for this class. Takes a type and a variadic list of
        subtypes and strings them into a key we'll use as a high-level
        identifier for this class's metrics.

        Args:
            queue_type: Metrics type for this queue
        """
        self._metrics_type = m_type
        self._metrics_subtypes = m_subtypes

        # Make the key string
        self._metrics_key_str = m_type
        for subtype in m_subtypes:
            self._metrics_key_str += f":{subtype}"

        # Make the labels
        self._metrics_labels = {METRICS_TYPE_LABEL: self._metrics_type}
        for i, subtype in enumerate(m_subtypes):
            self._metrics_labels[METRICS_SUBTYPE_LABEL + str(i)] = subtype

        # Make the metrics keys
        self._metrics_keys = {}

    def _make_metric_key(self, descriptor: str) -> str:
        """
        Return a fully specified metrics key

        Args:
            descriptor: Descriptor for the key
        """
        return f"{self._metrics_key_str}:{descriptor}"

    def _create_metric(
        self,
        element: Element,
        descriptor: str,
        metric_level: MetricsLevel = MetricsLevel.INFO,
    ) -> None:
        """
        Create a metric and return the key for it

        Args:
            element: Element used to create the metric
            descriptor: Subtype/Descriptor for the metric
            metric_level: Level of the metric

        Returns:
            Key string for the metric
        """

        # Make the metric key
        metric_key = self._make_metric_key(descriptor)

        # Make the metric
        element.metrics_create_custom(
            metric_level,
            metric_key,
            labels={
                METRICS_LEVEL_LABEL: metric_level.name,
                "desc": descriptor,
                **self._metrics_labels,
            },
        )

        # Add the key into our metrics keys
        self._metrics_keys[descriptor] = metric_key

    def _log_metric(
        self, element: Element, descriptor: str, value: float, pipeline: Pipeline = None
    ) -> None:
        """
        Log a metric for a descriptor

        Args:
            element: Element used to create the metric
            descriptor: Subtype/Descriptor for the metric
            value: Value for the metric
            pipeline: Pipeline for the metric
        """

        # Issue in Atom -- if we're not the element that made the metric
        #   we're not going to be able to log to it.
        if self._metrics_keys[descriptor] not in element._metrics:
            element._metrics.add(self._metrics_keys[descriptor])

        # Known bug in RTS when logging 0, ignore for now
        if value != 0:
            element.metrics_add(
                self._metrics_keys[descriptor],
                value,
                pipeline=cast(Optional[RedisTimeSeriesPipeline], pipeline),
            )

    def _log_metric_timing(
        self,
        element: Element,
        descriptor: str,
        start_time: float,
        pipeline: Pipeline = None,
    ) -> None:
        """
        Log a timing metric for a descriptor. Should be given a start time
        calculated with time.monotonic()

        Args:
            element: Element used to create the metric
            descriptor: Subtype/Descriptor for the metric
            start_time: Time the timing metric was started
            pipeline: Pipeline for the metric
        """
        self._log_metric(
            element, descriptor, time.monotonic() - start_time, pipeline=pipeline
        )

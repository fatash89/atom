import time

from atom.config import (
    METRICS_LEVEL_LABEL,
    METRICS_SUBTYPE_LABEL,
    METRICS_TYPE_LABEL,
    MetricsLevel,
)


class MetricsTimingCall(object):
    """
    Wrapper for making metrics timing calls
    """

    def __init__(self, helper_instance, element, metric_key, pipeline=None):
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

    def _set_metric_info(self, m_type, *m_subtypes):
        """
        Set the metric info for this class. Takes a type and a variadic list
        of subtypes and strings them into a key we'll use as a high-level
        identifier for this class's metrics.

        Args:
            queue_type (string): Metrics type for this queue
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

    def _make_metric_key(self, descriptor):
        """
        Return a fully specified metrics key

        Args:
            descriptor (string): Descriptor for the key
        """
        return f"{self._metrics_key_str}:{descriptor}"

    def _create_metric(self, element, descriptor, metric_level=MetricsLevel.INFO):
        """
        Create a metric and return the key for it

        Args:
            element (Atom Element): Element used to create the metric
            descriptor (string): Subtype/Descriptor for the metric
            metric_level (MetricsLevel): Level of the metric

        Return:
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

    def _log_metric(self, element, descriptor, value, pipeline=None):
        """
        Log a metric for a descriptor

        Args:
            element (Atom Element): Element used to create the metric
            descriptor (string): Subtype/Descriptor for the metric
            value (float): Value for the metric
            pipeline (redis pipeline): Pipeline for the metric
        """

        # Issue in Atom -- if we're not the element that made the metric
        #   we're not going to be able to log to it.
        if self._metrics_keys[descriptor] not in element._metrics:
            element._metrics.add(self._metrics_keys[descriptor])

        # Known bug in RTS when logging 0, ignore for now
        if value != 0:
            element.metrics_add(
                self._metrics_keys[descriptor], value, pipeline=pipeline
            )

    def _log_metric_timing(self, element, descriptor, start_time, pipeline=None):
        """
        Log a timing metric for a descriptor. Should be given a start time
        calculated with time.monotonic()

        Args:
            element (Atom Element): Element used to create the metric
            descriptor (string): Subtype/Descriptor for the metric
            start_time (time.monotonic() return): Time the timing metric
                was started
            pipeline (redis pipeline): Pipeline for the metric
        """
        self._log_metric(
            element, descriptor, time.monotonic() - start_time, pipeline=pipeline
        )

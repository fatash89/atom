import pickle
import time
from enum import Enum, auto
from multiprocessing import Queue
from queue import Empty as QueueEmpty

from atom import AtomError, LogLevel
from atom.config import (
    FIFO_QUEUE_DEFAULT_MAX_LEN,
    METRICS_FIFO_QUEUE_TYPE,
    METRICS_PRIO_QUEUE_GET_N,
    METRICS_PRIO_QUEUE_GET_PRIO,
    METRICS_PRIO_QUEUE_PRUNE_PRIO,
    METRICS_PRIO_QUEUE_PUT_PRIO,
    METRICS_PRIO_QUEUE_TYPE,
    METRICS_QUEUE_GET,
    METRICS_QUEUE_GET_DATA,
    METRICS_QUEUE_GET_EMPTY,
    METRICS_QUEUE_PRUNED,
    METRICS_QUEUE_PUT,
    METRICS_QUEUE_SIZE,
    METRICS_QUEUE_TYPE,
    PRIO_QUEUE_DEFAULT_MAX_LEN,
)
from atom.element import MetricsPipeline, SetEmptyError
from atom.metrics import MetricsHelper, MetricsTimingCall


class AtomQueueTypes(Enum):
    FIFO = auto()
    PRIO = auto()


class AtomQueue(MetricsHelper):
    """
    Shared functions between the various queues. No need to reinvent
    the wheel on most things, including metrics
    """

    def _init_shared_metrics(self, element, metric_type, *metric_subtypes):
        """
        Initialize metrics for this queue. We will do this using the custom
        API from Atom s.t. we don't have the metrics namespaced on the element
        itself. This will enable multiple processes to be logging to the same
        metrics s.t. it shows up in one place in the dashboards

        Args:
            metric_type (string): Metric type to use for the queue
            element (Atom Element): Element to use to communicate with the
                metrics redis. Can be any valid element.
            metric_subtypes (list of str): List of subtypes for the queue
        """

        # Set the metrics info
        self._set_metric_info(metric_type, *metric_subtypes)

        # Make all of the shared metrics
        self._create_metric(element, METRICS_QUEUE_SIZE)
        self._create_metric(element, METRICS_QUEUE_PUT)
        self._create_metric(element, METRICS_QUEUE_GET)
        self._create_metric(element, METRICS_QUEUE_PRUNED)
        self._create_metric(element, METRICS_QUEUE_GET_DATA)
        self._create_metric(element, METRICS_QUEUE_GET_EMPTY)


class AtomPrioQueue(AtomQueue):
    """
    Multi-process priority queue with auto-self-pruning and metrics integrations

    Takes floating-point priority numbers and can be configured to treat either
    the min or max numbers as the min/max priority.

    Built around Atom/Redis sorted set since it is multi-process safe and
        will allow us to collaborate on a sorted list easily and effectively
        in a multi-process fashion.

    Pruning occurs on PUT if we are over our max size as this is likely the
    best place to put it to resolve the problem (putter takes more time to
    clean, slowing down puts temporarily to perhaps allow gets to catch up).
    """

    def __init__(
        self,
        name,
        element,
        max_highest_prio=False,
        max_len=PRIO_QUEUE_DEFAULT_MAX_LEN,
        metrics_type=METRICS_PRIO_QUEUE_TYPE,
    ):
        """
        Constructor.

        Args:
            name (str): The name of the queue
            element (Atom Element): Element to use to initialize metrics
                for the queue. Can be any valid element, won't be remembered
                or used again outside of this call.
            max_highest_prio (boolean, optional). Default False. If False,
                the minimum value in the queue is considered to be the highest
                priority. If False, the maximum is considered to be the highest
                priority. We can support either.
            max_len (int, optional): Maximum length of the queue. If this number
                is exceeded in the qsize() call immediately after a put the
                queue will be pruned to max length.
        """

        # Create the name for the sorted sed
        self.sorted_set_key = f"atom-prio-queue-{name}"

        # Delete the sorted set in case it already exists
        try:
            element.sorted_set_delete(self.sorted_set_key)
        except AtomError:
            pass

        # Note variables
        self.name = name
        self.max_highest_prio = max_highest_prio
        self.max_len = max_len

        # Initialize the metrics we'll use to track the queue
        self._init_metrics(element, METRICS_QUEUE_TYPE, metrics_type, self.name)

    def _init_metrics(self, element, metric_type, *metric_subtypes):
        """
        Initialize metrics for this queue. We will do this using the custom
        API from Atom s.t. we don't have the metrics namespaced on the element
        itself. This will enable multiple processes to be logging to the same
        metrics s.t. it shows up in one place in the dashboards

        Args:
            metric_type (string): Metric type to use for the queue
            element (Atom Element): Element to use to communicate with the
                metrics redis. Can be any valid element.
            metric_subtypes (list of str): List of subtypes for the queue
        """

        # Initialize the shared metrics
        self._init_shared_metrics(element, metric_type, *metric_subtypes)

        # Make our additional metrics
        self._create_metric(element, METRICS_PRIO_QUEUE_GET_N)
        self._create_metric(element, METRICS_PRIO_QUEUE_GET_PRIO)
        self._create_metric(element, METRICS_PRIO_QUEUE_PUT_PRIO)
        self._create_metric(element, METRICS_PRIO_QUEUE_PRUNE_PRIO)

    def prune(self, element, q_size=None, pipeline=None, invert=False):
        """
        Prune to max length

        Args:
            q_size (int): Current size of the queue.
            element (Atom Element): Element to use to communicate with
                metrics.
            pipeline (redis pipeline): Pipeline to use for metrics,
                else will just put it on the element
            invert (bool): Whether we should invert the pruning logic

        Return:
            List of items pruned
        """

        if q_size is None:
            q_size = element.sorted_set_size(self.sorted_set_key)

        pruned = []

        while q_size > self.max_len:

            # Get the lowest prio item from the set by inverting the user's
            #   maximum preference.
            prune_maximum = (
                not self.max_highest_prio if not invert else self.max_highest_prio
            )
            (data, prune_prio), q_size = element.sorted_set_pop(
                self.sorted_set_key, maximum=prune_maximum
            )

            # Add the pruned item to the list of pruned items
            pruned.append(pickle.loads(data))

            # Note the prio for the object pruned
            self._log_metric(
                element,
                METRICS_PRIO_QUEUE_PRUNE_PRIO,
                prune_prio,
                pipeline=pipeline,
            )

        return pruned, q_size

    def put(self, item, prio, element, prune=True, invert=False):
        """
        Put an item onto the queue

        Args:
            item (N/A): Thing to be put onto the queue. MUST be pickleable
                as we will attempt to pickle it.
            prio (float): Floating-point priority to put the item into the queue
                with.
            element (Atom Element): Element to use to communicate with
                metrics.
            prune (bool): If True, do pruning on this put action. If false,
                will skip the pruning. Not recommended to do this unless
                there's a really heavy cleanup action for the pruned
                items which cannot be done from the put() side such as in
                StreamHandler
            invert (bool): Whether we should invert the pruning logic

        Return:
            (Current queue size, list of pruned elements)
        """

        # Note the pruned items
        pruned = []

        # Get a metrics pipeline to use for queue interactions
        with MetricsPipeline(element) as metrics_pipeline:

            # Start timing how long the put will take
            with MetricsTimingCall(
                self, element, METRICS_QUEUE_PUT, pipeline=metrics_pipeline
            ):

                # Do the put
                q_size = element.sorted_set_add(
                    self.sorted_set_key, pickle.dumps(item), prio
                )

            # Note the queue size and priority of the item added
            self._log_metric(
                element, METRICS_QUEUE_SIZE, q_size, pipeline=metrics_pipeline
            )
            self._log_metric(
                element, METRICS_PRIO_QUEUE_PUT_PRIO, prio, pipeline=metrics_pipeline
            )

            if prune:
                pruned, q_size = self.prune(
                    element, q_size=q_size, pipeline=metrics_pipeline, invert=invert
                )

            # Note how many were pruned
            self._log_metric(
                element, METRICS_QUEUE_PRUNED, len(pruned), pipeline=metrics_pipeline
            )

        return q_size, pruned

    def get(self, element, block=True, timeout=0):
        """
        Get a piece of data from a queue. Default will block until data
        is available. Pass timeout (in seconds) to have it return early
        if no data i available.

        Args:
            element (Atom Element): Element used to communicate with metrics
            block (bool, optional): Default true. If true will block for timeout
                seconds until returning. Otherwise will attempt to get data
                and then return immediately
            timeout (int): If block is true, the amount of seconds to wait
                for data. Set to 0 for infinite timeout.

        Return:
            Item from queue else None
        """

        with MetricsPipeline(element) as metrics_pipeline:

            with MetricsTimingCall(
                self, element, METRICS_QUEUE_GET, pipeline=metrics_pipeline
            ):

                # Do the get
                try:
                    item, _ = element.sorted_set_pop(
                        self.sorted_set_key,
                        maximum=self.max_highest_prio,
                        block=block,
                        timeout=timeout,
                    )
                except SetEmptyError:
                    item = None

            # If we got valid data from the queue
            if item is not None:

                # Unpack the item and unpickle the data
                data, prio = item
                item = pickle.loads(data)

                # Note that we have data and the prio of the data
                self._log_metric(
                    element, METRICS_QUEUE_GET_DATA, 1, pipeline=metrics_pipeline
                )
                self._log_metric(
                    element,
                    METRICS_PRIO_QUEUE_GET_PRIO,
                    prio,
                    pipeline=metrics_pipeline,
                )

            # Otherwise
            else:
                self._log_metric(
                    element, METRICS_QUEUE_GET_EMPTY, 1, pipeline=metrics_pipeline
                )

        return item

    def get_n(self, element, n, max_n=False):
        """
        Return up to N items from the priority queue, in priority order. No
        ability to block, if you need blocking you should use the get() API.

        Args:
            element (Atom Element): Element used to communicate with metrics
            n (integer): Maximum number of items to return from the priority
                queue.
            max_n (boolean): If true will return up to the queue's max amount
                of items

        Return:
            List of items from queue, returned in prio order
        """

        with MetricsPipeline(element) as metrics_pipeline:

            with MetricsTimingCall(
                self, element, METRICS_PRIO_QUEUE_GET_N, pipeline=metrics_pipeline
            ):

                # Do the get
                try:
                    items, _ = element.sorted_set_pop_n(
                        self.sorted_set_key,
                        n if not max_n else self.max_len,
                        maximum=self.max_highest_prio,
                    )
                except SetEmptyError:
                    items = []

            # If we got valid data from the queue, we want to
            #   unpack it
            ret_items = []
            if items:

                for item in items:

                    # Unpack the item and unpickle the data
                    data, prio = item
                    ret_items.append(pickle.loads(data))

                    # Note the priority of the item we got
                    self._log_metric(
                        element,
                        METRICS_PRIO_QUEUE_GET_PRIO,
                        prio,
                        pipeline=metrics_pipeline,
                    )

                # Note how many data we got
                self._log_metric(
                    element,
                    METRICS_QUEUE_GET_DATA,
                    len(items),
                    pipeline=metrics_pipeline,
                )

            # Otherwise
            else:
                self._log_metric(
                    element, METRICS_QUEUE_GET_EMPTY, 1, pipeline=metrics_pipeline
                )

        return ret_items

    def finish(self, element):
        """
        Call when done using the queue. This will ensure that your process/
        thread can shut down properly. Nothing to do for the prio queue type

        Args:
            element (Atom Element): Element to be used to close out the queue
        """
        try:
            element.sorted_set_delete(self.sorted_set_key)
        except AtomError:
            pass


class AtomFIFOQueue(AtomPrioQueue):
    """
    FIFO queue buit atop the prio queue using time as priority. Might be more
    reliable in terms of in-time ordering when being fed by multiple
    handling processes. We can use frame timestamp to prioritize frames
    when feeding from something like StreamHandler
    """

    def __init__(
        self,
        name,
        element,
        max_highest_prio=False,
        max_len=PRIO_QUEUE_DEFAULT_MAX_LEN,
        metrics_type=METRICS_FIFO_QUEUE_TYPE,
    ):
        """
        Constructor.

        Args:
            name (str): The name of the queue
            element (Atom Element): Element to use to initialize metrics
                for the queue. Can be any valid element, won't be remembered
                or used again outside of this call.
            max_highest_prio (boolean, optional). Default False. If False,
                the minimum value in the queue is considered to be the highest
                priority. If False, the maximum is considered to be the highest
                priority. We can support either.
            max_len (int, optional): Maximum length of the queue. If this number
                is exceeded in the qsize() call immediately after a put the
                queue will be pruned to max length.
        """
        super(AtomFIFOQueue, self).__init__(
            name,
            element,
            max_highest_prio=max_highest_prio,
            max_len=max_len,
            metrics_type=metrics_type,
        )

    def prune(self, element, q_size=None, pipeline=None, invert=False):
        """
        Prune to max length. We want to invert the pruning logic
        of the typical prio queue, since typically the prio will prune
        the least important value, which in our case will be the newest
        since it will have the greatest timestamp. We want to prune from
        the front

        Args:
            q_size (int): Current size of the queue.
            element (Atom Element): Element to use to communicate with
                metrics.
            pipeline (redis pipeline): Pipeline to use for metrics,
                else will just put it on the element
            invert (bool): Whether we should invert the pruning logic

        Return:
            List of items pruned
        """
        return super(AtomFIFOQueue, self).prune(
            element, q_size=q_size, pipeline=pipeline, invert=not invert
        )

    def put(self, item, element, timestamp=None, prune=True, invert=False):
        """
        Put an item onto the queue

        Args:
            item (N/A): Thing to be put onto the queue. MUST be pickleable
                as we will attempt to pickle it.
            prio (float): Floating-point priority to put the item into the queue
                with.
            element (Atom Element): Element to use to communicate with
                metrics.
            prune (bool): If True, do pruning on this put action. If false,
                will skip the pruning. Not recommended to do this unless
                there's a really heavy cleanup action for the pruned
                items which cannot be done from the put() side such as in
                StreamHandler
            timestamp (float): Timestamp to use for the FIFO ordering. If
                None will use time.monotonic(), else will use the passed value.
                This allows us to add slightly-out-of order based on scheduling
                and still get FIFO behavior.

        Return:
            (Current queue size, list of pruned elements)
        """
        return super(AtomFIFOQueue, self).put(
            item,
            time.monotonic() if not timestamp else timestamp,
            element,
            prune=prune,
            invert=invert,
        )


class AtomFIFOMultiprocessingQueue(AtomQueue):
    """
    Multi-process FIFO queue with auto-self-pruning and metrics integrations.

    Built around Multiprocessing Queue() since it's simple, effective and
    native to Python.

    NOTE: THIS QUEUE IS MORE OR LESS DEPRECATED BY AtomFIFOQueue AS IT
    PERFORMS SIGNIFICANTLY WORSE. IT'S LEFT HERE SINCE IT CONFORMS TO THE
    SAME API AND COULD BE USEFUL EVENTUALLY BUT IT SHOULD NOT BE USED/FAVORED
    IN NEW DESIGNS.

    Pruning occurs on PUT if we are over our max size, as this is likely the
    best place to put it to resolve the problem (putter takes more time to
    clean, slowing down puts temporarily to perhaps allow gets to catch up)
    """

    def __init__(self, name, element, max_len=FIFO_QUEUE_DEFAULT_MAX_LEN):
        """
        Constructor.

        Args:
            name (str): The name of the queue
            element (Atom Element): Element to use to initialize metrics
                for the queue. Can be any valid element, won't be remembered
                or used again outside of this call.
            max_len (int, optional): Maximum length of the queue. If this number
                is exceeded in the qsize() call immediately after a put the
                queue will be pruned to max length.
        """

        # Make the queue
        self.q = Queue()

        # Note variables
        self.name = name
        self.max_len = max_len

        # Initialize the metrics we'll use to track the queue
        self._init_metrics(
            element, METRICS_QUEUE_TYPE, METRICS_FIFO_QUEUE_TYPE, self.name
        )

    def _init_metrics(self, element, metric_type):
        """
        Initialize metrics for this queue. We will do this using the custom
        API from Atom s.t. we don't have the metrics namespaced on the element
        itself. This will enable multiple processes to be logging to the same
        metrics s.t. it shows up in one place in the dashboards

        Args:
            metric_type (string): Metric type to use for the queue
            element (Atom Element): Element to use to communicate with the
                metrics redis. Can be any valid element.
        """

        # Just use the standard shared metrics from AtomQueue. Nothing
        #   fancy here
        self._init_shared_metrics(element, metric_type)

    def prune(self, element, q_size=None):
        """
        Prune to max length

        Args:
            q_size (int): Current size of the queue
            element (Atom Element): Element to use to communicate with
                metrics.

        Return:
            List of items pruned
        """

        if q_size is None:
            q_size = self.q.qsize()

        pruned = []

        # If our queue size is greater than the max size, we want to
        #   prune
        while q_size > self.max_len:

            # Try to get an item. This should not return empty since we're
            #   over the queue size
            try:
                item = self.q.get(block=False)
            except QueueEmpty:
                element.log(
                    LogLevel.ERR,
                    f"Queue {self.name} returned empty when over-size!",
                )
                break

            # Add the pruned item to the list of pruned items
            pruned.append(item)

            # Update the queue size
            q_size = self.q.qsize()

        return pruned, q_size

    def put(self, item, element, prune=True):
        """
        Put an item onto the queue

        Args:
            item (N/A): Thing to be put onto the queue
            element (Atom Element): Element to use to communicate with
                metrics.
            prune (bool): If True, do pruning on this put action. If false,
                will skip the pruning. Not recommended to do this unless
                there's a really heavy cleanup action for the pruned
                items which cannot be done from the put() side such as in
                StreamHandler

        Return:
            (Current queue size, list of pruned elements)
        """

        # Note the pruned items
        pruned = []

        # Get a metrics pipeline to use for queue interactions
        with MetricsPipeline(element) as metrics_pipeline:

            # Do the put and wrap it in a timing call
            with MetricsTimingCall(
                self, element, METRICS_QUEUE_PUT, pipeline=metrics_pipeline
            ):
                self.q.put(item)

            # Get the queue size
            q_size = self.q.qsize()
            self._log_metric(
                element, METRICS_QUEUE_SIZE, q_size, pipeline=metrics_pipeline
            )

            if prune:
                pruned, q_size = self.prune(element, q_size=q_size)

            # If we pruned data, we should note it
            self._log_metric(
                element, METRICS_QUEUE_PRUNED, len(pruned), pipeline=metrics_pipeline
            )

        return q_size, pruned

    def get(self, element, block=True, timeout=None):
        """
        Get a piece of data from a queue. Default will block until data
        is available. Pass timeout (in seconds) to have it return early
        if no data i available.

        Args:
            element (Atom Element): Element used to communicate with metrics
            block (bool, optional): Default true. If true will block for timeout
                seconds until returning. Otherwise will attempt to get data
                and then return immediately
            timeout (int): If block is true, the amount of seconds to wait
                for data. Leave as None for infinite timeout

        Return:
            Item from queue else None
        """

        with MetricsPipeline(element) as metrics_pipeline:

            with MetricsTimingCall(
                self, element, METRICS_QUEUE_GET, pipeline=metrics_pipeline
            ):

                # Do the get
                try:
                    item = self.q.get(block=block, timeout=timeout)
                except QueueEmpty:
                    item = None

            # Check to see if we had data or are empty
            if item is not None:
                self._log_metric(
                    element, METRICS_QUEUE_GET_DATA, 1, pipeline=metrics_pipeline
                )
            else:
                self._log_metric(
                    element,
                    METRICS_QUEUE_GET_EMPTY,
                    1,
                    pipeline=metrics_pipeline,
                )

        return item

    def finish(self, element):
        """
        Call when done using the queue. This will ensure that your process/
        thread can shut down properly. We will close the queue and cancel the
        thread that's ensuring data is being written/read from the queue
        so that we may exit

        Args:
            element (Atom Element): Element to be used to close out the queue
        """
        self.q.close()
        self.q.cancel_join_thread()

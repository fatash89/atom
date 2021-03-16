import gc
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
import redis
from atom import Element
from atom.config import (
    DEFAULT_METRICS_SOCKET,
    DEFAULT_REDIS_SOCKET,
    METRICS_QUEUE_SHARED_KEYS,
)
from atom.queue import AtomFIFOQueue, AtomPrioQueue, AtomQueueTypes
from redistimeseries.client import Client as RedisTimeSeries

QUEUE_TYPES = [AtomQueueTypes.FIFO, AtomQueueTypes.PRIO]

# Queue classes for test parametrization
QUEUE_CLASSES = {
    AtomQueueTypes.FIFO: AtomFIFOQueue,
    AtomQueueTypes.PRIO: AtomPrioQueue,
}


class QueueDummyClass(object):
    def __init__(self, value):
        self.value = value

    def __eq__(self, obj):
        return self.value == obj.value


class TestQueue(object):

    element_incrementor = 0

    @pytest.fixture
    def nucleus_redis(self):
        """
        Sets up a redis-py connection to the redis server
        """
        client = redis.StrictRedis(unix_socket_path=DEFAULT_REDIS_SOCKET)
        client.flushall()

        yield client

        del client
        gc.collect()

    @pytest.fixture
    def metrics_redis(self):
        """
        Sets up a redis-py connection to the redis server
        """
        client = RedisTimeSeries(unix_socket_path=DEFAULT_METRICS_SOCKET)

        client.redis.flushall()
        keys = client.redis.keys()
        assert keys == []
        yield client

        del client
        gc.collect()

    @pytest.fixture
    def element(self, nucleus_redis, metrics_redis):
        """
        Sets up the caller before each test function is run.
        Tears down the caller after each test is run.

        NOTE: must depend on metrics_redis, otherwise creating the
            metrics_redis will flush needed keys
        """
        # Want to be at the highest log level for testing
        os.environ["ATOM_LOG_LEVEL"] = "DEBUG"
        os.environ["ATOM_USE_METRICS"] = "TRUE"

        # Make the element and yield it
        element = Element(f"test_atom_queue-{self.element_incrementor}")
        self.element_incrementor += 1
        yield element

        # Delete the element when done
        element._clean_up()
        del element
        gc.collect()

    def _make_metrics_prefix(self, q, q_type):
        """
        Make the metrics prefix
        """
        return f"queue:{q_type.name.lower()}:{q.name}"

    def _make_metrics_key(self, q, q_type, desc):
        """
        Make an expected metrics key
        """
        return f"{self._make_metrics_prefix(q, q_type)}:{desc}".encode("utf-8")

    def _make_metrics_labels(self, q, q_type, desc):
        """
        Make the expected metrics label for the queue metric
        """
        return {
            "agg": "none",
            "agg_type": "none",
            "level": "INFO",
            "desc": desc,
            "type": "queue",
            "subtype0": q_type.name.lower(),
            "subtype1": q.name,
        }

    def _make_prio_q_key(self, q):
        """
        Get the key for a priority queue
        """
        return f"vision-prio-queue-{q.name}"

    def _finish_and_check_q(self, nucleus_redis, element, q, q_type):
        """
        Call finish and check that everything is cleaned up properly
        """
        q.finish(element)

        if q_type == AtomQueueTypes.PRIO:
            q_key = self._make_prio_q_key(q)
            assert nucleus_redis.exists(q_key) == 0

    @pytest.mark.parametrize("queue_type", QUEUE_TYPES)
    def test_queue_create_and_metrics(
        self, nucleus_redis, metrics_redis, element, queue_type
    ):
        """
        Test creating a queue
        """
        test_q = QUEUE_CLASSES[queue_type]("some_queue", element)

        # Make the list of expected descriptors
        keys = set(METRICS_QUEUE_SHARED_KEYS)

        # Make sure all of the metrics keys are created
        metrics_keys = set(metrics_redis.redis.keys(f"queue:*"))
        expected_keys = set(
            [self._make_metrics_key(test_q, queue_type, x) for x in keys]
        )

        # Make sure all of the labels are correct
        assert metrics_keys == expected_keys

        # Now, make sure each has the right info
        for key in keys:
            info = metrics_redis.info(self._make_metrics_key(test_q, queue_type, key))
            assert info.labels == self._make_metrics_labels(test_q, queue_type, key)

        self._finish_and_check_q(nucleus_redis, element, test_q, queue_type)

    @pytest.mark.parametrize("queue_type", QUEUE_TYPES)
    @pytest.mark.parametrize("max_len", [1, 10, 100, 1000])
    def test_queue_create_max_len(self, nucleus_redis, element, queue_type, max_len):
        """
        Test creating a queue
        """
        test_q = QUEUE_CLASSES[queue_type]("some_queue", element, max_len=max_len)
        assert test_q is not None

        self._finish_and_check_q(nucleus_redis, element, test_q, queue_type)

    @pytest.mark.parametrize("queue_type", QUEUE_TYPES)
    @pytest.mark.parametrize("max_len", [1, 10])
    @pytest.mark.parametrize(
        "item", [None, 0, 1, {"hello": "world"}, QueueDummyClass(set(("a", "b", "c")))]
    )
    def test_queue_put_get(self, nucleus_redis, element, queue_type, max_len, item):
        """
        Test creating a queue
        """
        test_q = QUEUE_CLASSES[queue_type]("some_queue", element, max_len=max_len)

        # If a prio queue, need to pass a prio as well.
        if queue_type == AtomQueueTypes.PRIO:
            q_size, pruned = test_q.put(item, 0, element)
        else:
            q_size, pruned = test_q.put(item, element)
        assert q_size == 1
        assert len(pruned) == 0

        start_time = time.monotonic()
        get_item = test_q.get(element)
        end_time = time.monotonic()
        assert get_item == item
        assert end_time - start_time < 0.1

        self._finish_and_check_q(nucleus_redis, element, test_q, queue_type)

    @pytest.mark.parametrize("queue_type", QUEUE_TYPES)
    @pytest.mark.parametrize("max_len", [1, 10])
    @pytest.mark.parametrize(
        "item", [None, 0, 1, {"hello": "world"}, QueueDummyClass(set(("a", "b", "c")))]
    )
    def test_queue_put_get_nonblocking(
        self, nucleus_redis, element, queue_type, max_len, item
    ):
        """
        Test creating a queue
        """
        test_q = QUEUE_CLASSES[queue_type]("some_queue", element, max_len=max_len)

        # If a prio queue, need to pass a prio as well.
        if queue_type == AtomQueueTypes.PRIO:
            q_size, pruned = test_q.put(item, 0, element)
        else:
            q_size, pruned = test_q.put(item, element)
        assert q_size == 1
        assert len(pruned) == 0

        # If it's a FIFO need to give the queue some time to ensure the item
        #   is in there. This is fairly silly/annoying
        if queue_type == AtomQueueTypes.FIFO:
            time.sleep(0.5)

        start_time = time.monotonic()
        get_item = test_q.get(element, block=False)
        end_time = time.monotonic()
        assert get_item == item
        assert end_time - start_time < 0.1

        self._finish_and_check_q(nucleus_redis, element, test_q, queue_type)

    @pytest.mark.parametrize("queue_type", QUEUE_TYPES)
    @pytest.mark.parametrize("max_len", [1, 10])
    def test_queue_get_nonblocking_empty(
        self, nucleus_redis, element, queue_type, max_len
    ):
        """
        Test creating a queue
        """
        test_q = QUEUE_CLASSES[queue_type]("some_queue", element, max_len=max_len)

        start_time = time.monotonic()
        get_item = test_q.get(element, block=False)
        end_time = time.monotonic()
        assert get_item is None
        assert end_time - start_time < 0.1

        self._finish_and_check_q(nucleus_redis, element, test_q, queue_type)

    @pytest.mark.parametrize("queue_type", QUEUE_TYPES)
    @pytest.mark.parametrize("max_len", [1, 10])
    @pytest.mark.parametrize("timeout", [0.1, 0.5])
    def test_queue_get_blocking_empty(
        self, nucleus_redis, element, queue_type, max_len, timeout
    ):
        """
        Test creating a queue
        """
        test_q = QUEUE_CLASSES[queue_type]("some_queue", element, max_len=max_len)

        start_time = time.monotonic()
        get_item = test_q.get(element, block=True, timeout=timeout)
        end_time = time.monotonic()
        assert get_item is None
        assert end_time - start_time > timeout

        self._finish_and_check_q(nucleus_redis, element, test_q, queue_type)

    def _test_queue_put_get_blocking_getter(self, queue):
        """
        Function to be called in the thread pool executor that will put into
        a queue
        """
        element = Element(f"test_queue_put_get_{uuid.uuid4()}")
        item = queue.get(element)
        return item

    @pytest.mark.parametrize("queue_type", QUEUE_TYPES)
    @pytest.mark.parametrize("max_len", [1, 10, 100])
    @pytest.mark.parametrize("sleep_time", [0.1, 0.5])
    def test_queue_put_get_blocking(
        self, nucleus_redis, element, queue_type, max_len, sleep_time
    ):
        """
        Test creating a queue
        """
        test_q = QUEUE_CLASSES[queue_type]("some_queue", element, max_len=max_len)

        # Issue a bunch of blocking gets with 2x the sleep time timeout
        executor = ThreadPoolExecutor(max_workers=max_len)
        futures = []
        for i in range(max_len):
            futures.append(
                executor.submit(self._test_queue_put_get_blocking_getter, test_q)
            )

        # Sleep for the sleep time
        time.sleep(sleep_time)

        # Put all of the items into the queue
        for i in range(max_len):
            if queue_type == AtomQueueTypes.PRIO:
                q_size, pruned = test_q.put(i, 0, element)
            else:
                q_size, pruned = test_q.put(i, element)

        # Get all of the results
        items = set()
        for fut in futures:
            items.add(fut.result())

        # Make sure we got all unique items
        assert items == set(range(max_len))

        self._finish_and_check_q(nucleus_redis, element, test_q, queue_type)

    @pytest.mark.parametrize("queue_type", QUEUE_TYPES)
    @pytest.mark.parametrize("max_len", [1, 10, 100])
    @pytest.mark.parametrize("prune_overage", [0, 1, 10, 100])
    def test_queue_put_get_pruning(
        self, nucleus_redis, element, queue_type, max_len, prune_overage
    ):
        """
        Test creating a queue
        """
        test_q = QUEUE_CLASSES[queue_type]("some_queue", element, max_len=max_len)

        # Loop over all of the values and some overage
        for i in range(max_len + prune_overage):

            # If we're in prio mode, run it like a FIFO with the priority
            #   equal to i.
            if queue_type == AtomQueueTypes.PRIO:
                q_size, pruned = test_q.put(i, i, element)
            else:
                q_size, pruned = test_q.put(i, element)

            # Do some checks based on where we are in the process
            if i < max_len:
                assert len(pruned) == 0
                assert q_size == i + 1
            else:

                # Make sure we pruned something
                assert len(pruned) == 1
                assert q_size == max_len

                # Prio queues always prune
                if queue_type == AtomQueueTypes.PRIO:
                    assert pruned[0] == i
                else:
                    assert pruned[0] == i - max_len

        for i in range(max_len):
            get_item = test_q.get(element)
            if queue_type == AtomQueueTypes.PRIO:
                assert get_item == i
            else:
                assert get_item == i + prune_overage

        self._finish_and_check_q(nucleus_redis, element, test_q, queue_type)

    @pytest.mark.parametrize("queue_type", QUEUE_TYPES)
    @pytest.mark.parametrize("max_len", [1, 10, 100])
    @pytest.mark.parametrize("prune_overage", [0, 1, 10, 100])
    def test_queue_put_get_pruning_manual(
        self, nucleus_redis, element, queue_type, max_len, prune_overage
    ):
        """
        Test creating a queue
        """
        test_q = QUEUE_CLASSES[queue_type]("some_queue", element, max_len=max_len)

        # Loop over all of the values and some overage
        for i in range(max_len + prune_overage):

            # If we're in prio mode, run it like a FIFO with the priority
            #   equal to i.
            if queue_type == AtomQueueTypes.PRIO:
                q_size, pruned = test_q.put(i, i, element, prune=False)
            else:
                q_size, pruned = test_q.put(i, element, prune=False)

            # Do some checks based on where we are in the process
            assert len(pruned) == 0
            assert q_size == i + 1

        # Manually prune
        pruned, q_size = test_q.prune(element)

        # Make sure we pruned to the right size and removed the right number
        #   of entries
        assert q_size == max_len
        assert len(pruned) == prune_overage

        # Make sure the pruned values are correct
        for i, val in enumerate(pruned):
            if queue_type == AtomQueueTypes.PRIO:
                assert val == max_len + prune_overage - i - 1
            else:
                assert val == i

        # Make sure the rest of the queue is correct
        for i in range(max_len):
            get_item = test_q.get(element)
            if queue_type == AtomQueueTypes.PRIO:
                assert get_item == i
            else:
                assert get_item == i + prune_overage

        self._finish_and_check_q(nucleus_redis, element, test_q, queue_type)

    @pytest.mark.parametrize("max_len", [10, 100, 1000])
    def test_queue_fifo(self, nucleus_redis, element, max_len):
        """
        Test creating a queue
        """
        test_q = AtomFIFOQueue("some_queue", element, max_len=max_len)

        for i in range(max_len):
            q_size, pruned = test_q.put(i, element)
            assert q_size == i + 1
            assert len(pruned) == 0

        for i in range(max_len):
            item = test_q.get(element)
            assert item is not None
            assert item == i

        self._finish_and_check_q(nucleus_redis, element, test_q, AtomQueueTypes.FIFO)

    @pytest.mark.parametrize("max_len", [10, 100, 1000])
    def test_queue_prio_least(self, nucleus_redis, element, max_len):
        """
        Test creating a queue
        """
        test_q = AtomPrioQueue("some_queue", element, max_len=max_len)

        for i in range(max_len):
            q_size, pruned = test_q.put(i, i, element)
            assert q_size == i + 1
            assert len(pruned) == 0

        for i in range(max_len):
            item = test_q.get(element)
            assert item is not None
            assert item == i

        self._finish_and_check_q(nucleus_redis, element, test_q, AtomQueueTypes.FIFO)

    @pytest.mark.parametrize("max_len", [10, 100, 1000])
    def test_queue_prio_greatest(self, nucleus_redis, element, max_len):
        """
        Test creating a queue
        """
        test_q = AtomPrioQueue(
            "some_queue", element, max_len=max_len, max_highest_prio=True
        )

        for i in range(max_len):
            q_size, pruned = test_q.put(i, i, element)
            assert q_size == i + 1
            assert len(pruned) == 0

        for i in range(max_len):
            item = test_q.get(element)
            assert item is not None
            assert item == max_len - i - 1

        self._finish_and_check_q(nucleus_redis, element, test_q, AtomQueueTypes.FIFO)

    @pytest.mark.parametrize("n", [-1, 0, 1, 2, 3, 4])
    @pytest.mark.parametrize("num_items", [2, 4])
    @pytest.mark.parametrize("max_len", [3])
    @pytest.mark.parametrize("queue_type", QUEUE_TYPES)
    def test_queue_peek_nonempty(
        self, nucleus_redis, element, queue_type, n, num_items, max_len
    ):
        """
        Test reading items from a non-empty queue does not consume items. Test
        that the returned list contains the following number of items:
            - -1 items       -> 0 (empty list)
            - 0 items        -> 0 (empty list)
            - n < num_items  -> n
            - n == num_items -> n or num_items (they're equal)
            - n > num_items  -> num_items
            - n > max_len    -> num_items
        """
        test_q = QUEUE_CLASSES[queue_type]("some_queue", element, max_len=max_len)
        q_size_expected = min(num_items, max_len)
        peek_expected_min = max(n, 0)
        peek_expected_max = min(num_items, max_len)

        # If a prio queue, need to pass a prio as well.
        for i in range(num_items):
            if queue_type == AtomQueueTypes.PRIO:
                test_q.put(i, i, element)
            else:
                test_q.put(i, element)

        assert test_q.size(element) == q_size_expected

        peek_item = test_q.peek_n(element, n)
        assert len(peek_item) == min(peek_expected_min, peek_expected_max)
        assert test_q.size(element) == q_size_expected

        self._finish_and_check_q(nucleus_redis, element, test_q, queue_type)

    @pytest.mark.parametrize("queue_type", QUEUE_TYPES)
    def test_queue_peek_empty(self, nucleus_redis, element, queue_type):
        """
        Test reading items from a non-empty queue returns an empty list.
        """
        test_q = QUEUE_CLASSES[queue_type]("some_queue", element, max_len=1)
        assert test_q.size(element) == 0

        peek_item = test_q.peek_n(element, 1)
        assert peek_item == []
        assert test_q.size(element) == 0

        self._finish_and_check_q(nucleus_redis, element, test_q, queue_type)

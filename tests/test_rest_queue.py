"""RestQueue: one worker thread, and shutdown drains what is queued.

__new__ returns the shared instance but Python still runs __init__ on every
RestQueue() call. Before this was guarded, each call rebuilt the queue and
started a new worker, orphaning the previous one on a queue nothing would ever
read again - a leaked thread per REST call.
"""
import threading
import time
import unittest

import _support  # noqa: F401  (path + hardware stubs)
import rest


class RestQueueTests(unittest.TestCase):
    def setUp(self):
        # Each test gets a fresh singleton.
        rest.RestQueue._instance = None
        self.calls = []
        self._realCall = rest.RestHelpers.makeRestCall
        rest.RestHelpers.makeRestCall = staticmethod(
            lambda url, *a, **k: self.calls.append(url)
        )

    def tearDown(self):
        rest.RestHelpers.makeRestCall = self._realCall
        queue = rest.RestQueue._instance
        if queue is not None and getattr(queue, "thread", None) is not None:
            if queue.thread.is_alive():
                queue.shutdown(timeout=2)
        rest.RestQueue._instance = None

    def test_repeated_construction_reuses_one_instance_and_one_thread(self):
        before = threading.active_count()
        instances = set()
        for i in range(50):
            queue = rest.RestQueue()
            instances.add(id(queue))
            queue.makeRestCallAsync(f"http://example.invalid/{i}")
        time.sleep(0.5)
        self.assertEqual(len(instances), 1, "RestQueue() returned different objects")
        self.assertEqual(
            threading.active_count() - before, 1,
            "expected exactly one worker thread for 50 calls",
        )
        self.assertEqual(len(self.calls), 50, "not every queued call was dispatched")

    def test_shutdown_drains_queued_calls_before_stopping(self):
        # cleanup() queues the WLED blackout and then shuts the queue down; if
        # the sentinel jumped the queue that preset would never be sent.
        queue = rest.RestQueue()
        for i in range(5):
            queue.makeRestCallAsync(f"http://example.invalid/{i}")
        queue.makeRestCallAsync("http://example.invalid/blackout")
        queue.shutdown(timeout=5)
        self.assertIn("http://example.invalid/blackout", self.calls)
        self.assertEqual(len(self.calls), 6)
        self.assertFalse(queue.thread.is_alive(), "worker still running after shutdown")


if __name__ == "__main__":
    unittest.main()

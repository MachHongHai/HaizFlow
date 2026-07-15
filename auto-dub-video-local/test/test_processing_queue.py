import sys
import threading
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autodub.services.processing_queue import SerialProcessingQueue


class SerialProcessingQueueTests(unittest.TestCase):
    def test_runs_jobs_in_fifo_order_without_parallel_execution(self):
        started = []
        completed = []
        active_count = 0
        maximum_active_count = 0
        done = threading.Event()
        lock = threading.Lock()

        def runner(job_id):
            nonlocal active_count, maximum_active_count
            with lock:
                active_count += 1
                maximum_active_count = max(maximum_active_count, active_count)
            time.sleep(0.02)
            with lock:
                active_count -= 1

        queue = SerialProcessingQueue(
            runner,
            on_started=started.append,
            on_finished=completed.append,
            on_idle=done.set,
        )

        self.assertTrue(queue.enqueue("first"))
        self.assertTrue(queue.enqueue("second"))
        self.assertTrue(queue.enqueue("third"))
        self.assertFalse(queue.enqueue("second"))
        self.assertTrue(done.wait(2))

        self.assertEqual(started, ["first", "second", "third"])
        self.assertEqual(completed, ["first", "second", "third"])
        self.assertEqual(maximum_active_count, 1)
        self.assertIsNone(queue.active_job_id)
        self.assertEqual(queue.pending_ids(), [])

    def test_discard_removes_only_a_waiting_job(self):
        release_first = threading.Event()
        done = threading.Event()
        completed = []

        def runner(job_id):
            if job_id == "first":
                release_first.wait(2)

        queue = SerialProcessingQueue(runner, on_finished=completed.append, on_idle=done.set)
        self.assertTrue(queue.enqueue("first"))
        self.assertTrue(queue.enqueue("second"))
        time.sleep(0.02)
        self.assertTrue(queue.discard("second"))
        self.assertFalse(queue.discard("first"))
        release_first.set()
        self.assertTrue(done.wait(2))
        self.assertEqual(completed, ["first"])


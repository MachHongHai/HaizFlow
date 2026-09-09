import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.services.external_engine import ExternalEngineClient, ExternalEngineError, ExternalEnginePool  # noqa: E402


FAKE_ENGINE = r"""
import json
import os
import sys
import time

for line in sys.stdin:
    request = json.loads(line)
    payload = request.get("payload") or {}
    time.sleep(float(payload.get("delay", 0)))
    if request["operation"] == "file_task":
        task_path = payload["request_path"]
        task = json.load(open(task_path, encoding="utf-8"))
        with open(task["response_path"], "w", encoding="utf-8") as stream:
            json.dump({"protocol_version": 1, "ok": True, "result": {"pid": os.getpid()}}, stream)
    print(json.dumps({
        "protocol_version": 1,
        "request_id": request["request_id"],
        "event": "response",
        "ok": True,
        "result": {"pid": os.getpid(), "operation": request["operation"]},
    }), flush=True)
"""


class _Manager:
    def __init__(self, root: Path):
        self.root = root
        self.definitions = {"engine-test": object()}

    def engine_command(self, _pack_id, command_name):
        if command_name != "rpc_command":
            return []
        return [sys.executable, "-u", "-c", FAKE_ENGINE]

    def _engine_marker(self, _definition):
        return self.root / "complete.json"

    def external_engine_pack(self, _capability, _context=None):
        return "engine-test"


class ExternalEngineTests(unittest.TestCase):
    def test_client_reuses_one_process_for_serial_requests(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = _Manager(Path(temp_dir))
            client = ExternalEngineClient(manager, "engine-test")
            try:
                first = client.request("warm").result
                second = client.request("release").result
            finally:
                client.close()

        self.assertEqual(first["pid"], second["pid"])
        self.assertEqual(second["operation"], "release")

    def test_speculative_warm_can_be_preempted_without_waiting_for_request_lock(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pool = ExternalEnginePool(_Manager(Path(temp_dir)))
            failures = []

            def warm():
                try:
                    pool._client("engine-test").request("warm", {"delay": 5}, timeout_seconds=10)
                except ExternalEngineError as exc:
                    failures.append(exc)

            worker = threading.Thread(target=warm)
            worker.start()
            time.sleep(0.15)
            started = time.monotonic()
            pool._client("engine-test").terminate()
            worker.join(2)
            elapsed = time.monotonic() - started
            pool.close()

        self.assertFalse(worker.is_alive())
        self.assertTrue(failures)
        self.assertLess(elapsed, 2)

    def test_file_task_runs_in_the_already_warmed_process(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pool = ExternalEnginePool(_Manager(root))
            client = pool._client("engine-test")
            warm_pid = client.request("warm").result["pid"]
            response = root / "response.json"
            request = root / "request.json"
            request.write_text(
                json.dumps({"response_path": str(response)}),
                encoding="utf-8",
            )
            try:
                self.assertTrue(pool.run_file_task("recognition", {}, str(request)))
                task_pid = json.loads(response.read_text(encoding="utf-8"))["result"]["pid"]
            finally:
                pool.close()

        self.assertEqual(warm_pid, task_pid)

    @unittest.skipUnless(os.name == "nt", "Windows process semantics are the release target")
    def test_windows_engine_is_started_without_a_console_window(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = _Manager(Path(temp_dir))
            client = ExternalEngineClient(manager, "engine-test")
            try:
                self.assertEqual(client.request("warm").result["operation"], "warm")
            finally:
                client.close()


if __name__ == "__main__":
    unittest.main()

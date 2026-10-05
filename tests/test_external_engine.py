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
    def test_rpc_request_paths_survive_a_legacy_windows_decoder(self):
        # ASCII JSON remains portable even before the child reconfigures stdin.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            unicode_root = root / "Mẫu giọng 日本語"
            unicode_root.mkdir()
            request, response = unicode_root / "request.json", unicode_root / "response.json"
            request.write_text(json.dumps({"response_path": str(response)}), encoding="utf-8")
            manager = _Manager(root)
            manager.engine_command = lambda *_: [sys.executable, "-u", "-c",
                "import sys; sys.stdin.reconfigure(encoding='cp1252'); " + FAKE_ENGINE]
            client = ExternalEngineClient(manager, "engine-test")
            try:
                client.request("file_task", {"request_path": str(request)})
            finally:
                client.close()
            self.assertTrue(json.loads(response.read_text(encoding="utf-8"))["ok"])
    def test_translation_handoff_retires_shared_asr_and_separation_process(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pool = ExternalEnginePool(_Manager(Path(temp_dir)))
            try:
                pool.warm("recognition")
                pool.warm("separation")
                process = pool._client("engine-test")._process
                self.assertEqual(pool.release({"recognition", "separation", "ocr"}), {"recognition", "separation"})
                self.assertIsNotNone(process.poll())
            finally:
                pool.close()

    def test_releasing_last_capability_exits_the_engine_and_can_restart(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pool = ExternalEnginePool(_Manager(Path(temp_dir)))
            try:
                pool.warm("recognition")
                client = pool._client("engine-test")
                first_process = client._process
                self.assertEqual(pool.release({"recognition"}), {"recognition"})
                self.assertIsNotNone(first_process.poll())
                pool.warm("recognition")
                self.assertIsNot(client._process, first_process)
                self.assertIsNone(client._process.poll())
            finally:
                pool.close()

    def test_releasing_one_capability_preserves_a_shared_engine_owner(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pool = ExternalEnginePool(_Manager(Path(temp_dir)))
            try:
                pool.warm("recognition")
                pool.warm("separation")
                process = pool._client("engine-test")._process
                self.assertEqual(pool.release({"recognition"}), {"recognition"})
                self.assertIsNone(process.poll())
                self.assertEqual(pool.release({"separation"}), {"separation"})
                self.assertIsNotNone(process.poll())
            finally:
                pool.close()

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

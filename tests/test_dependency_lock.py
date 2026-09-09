import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


class DependencyLockTests(unittest.TestCase):
    def test_release_lock_and_manifest_are_current(self):
        root = Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [sys.executable, str(root / "scripts" / "verify-dependency-lock.py"), "--no-installed-check"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertGreaterEqual(payload["locked_packages"], 40)
        lock_text = (root / "requirements-lock-py313-win64.txt").read_text(encoding="utf-8").lower()
        self.assertNotIn("download.pytorch.org", lock_text)
        self.assertNotIn("llama-cpp-python", lock_text)
        self.assertEqual(payload["target"], "windows-x86_64-python-3.13")

    def test_engine_locks_include_reviewed_common_runtime_dependencies(self):
        root = Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [sys.executable, str(root / "scripts" / "verify-engine-dependency-locks.py")],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertIn("requirements-engine-common.in", payload["inputs"])
        for profile in ("cpu", "cuda128", "vision"):
            lock_text = (root / payload["locks"][profile]["file"]).read_text(encoding="utf-8").lower()
            self.assertIn("python-dotenv==", lock_text)
            self.assertIn("pydantic==", lock_text)
            self.assertNotIn("pyside6==", lock_text)

    def test_core_controller_import_does_not_load_optional_ai_runtimes(self):
        root = Path(__file__).resolve().parents[1]
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(root / "src")
        script = (
            "import json,sys; import haizflow.desktop.qml_controller; "
            "names=('torch','transformers','onnxruntime','rapidocr','whisperx','demucs'); "
            "print(json.dumps([name for name in names if name in sys.modules]))"
        )
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout), [])


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


class DependencyLockTests(unittest.TestCase):
    def _load_script(self, name):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location(name.replace("-", "_"), root / "scripts" / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_source_client_is_exactly_pinned_and_included_in_license_inventory(self):
        verifier = self._load_script("verify-dependency-lock")
        requirement, version = verifier._locked_requirements()["edge-tts"]
        self.assertEqual(version, "7.3.1")
        self.assertEqual(requirement.url, verifier._source_pins()["edge-tts"]["url"])
        notices = self._load_script("generate-third-party-notices")
        self.assertIn("edge-tts", notices._locked_distributions(verifier.LOCK_PATH))
        runtime = self._load_script("verify-runtime")
        self.assertEqual(runtime.expected_packages()["edge-tts"], "7.3.1")

    def test_source_lock_rejects_changed_hash_commit_branch_and_unreviewed_source(self):
        verifier = self._load_script("verify-dependency-lock")
        pin = verifier._source_pins()["edge-tts"]
        valid = f"edge-tts @ {pin['url']} --hash=sha256:{pin['sha256']}"
        invalid = (
            valid.replace(pin["sha256"], "0" * 64),
            valid.replace(pin["url"].rsplit("/", 1)[1], "0" * 40),
            valid.replace(pin["url"].rsplit("/", 1)[1], "main"),
            valid.replace("edge-tts @", "unreviewed @"),
            valid + " --hash=sha256:" + "0" * 64,
        )
        for entry in invalid:
            with self.subTest(entry=entry), patch.object(verifier, "_logical_requirements", return_value=[entry]):
                with self.assertRaisesRegex(RuntimeError, "not exact"):
                    verifier._locked_requirements()

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
        self.assertGreaterEqual(payload["locked_packages"], 30)
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
            "import json,sys; import hflow.desktop.qml_controller; "
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

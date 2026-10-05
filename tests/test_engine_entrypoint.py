import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.engine import main as engine_main  # noqa: E402


def load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


write_manifest = load_script("write-engine-manifest.py")


class EngineEntrypointTests(unittest.TestCase):
    def test_external_voice_audio_dependency_is_frozen_and_smoke_checked(self):
        for profile in ("cpu", "cuda128"):
            self.assertIn("pydub.silence", engine_main.SMOKE_MODULES[profile])
            self.assertIn("audioop", engine_main.SMOKE_MODULES[profile])
        script = (ROOT / "scripts/build-resource-engine.ps1").read_text(encoding="utf-8")
        for module in ('"pydub"', '"pydub.silence"', '"audioop"'):
            self.assertIn(module, script)

    def test_smoke_exercises_whisperx_lazy_inference_modules(self):
        for profile in ("cpu", "cuda128"):
            self.assertIn("onnxruntime", engine_main.SMOKE_MODULES[profile])
            for module in ("whisperx.asr", "whisperx.alignment", "whisperx.vads"):
                self.assertIn(module, engine_main.SMOKE_MODULES[profile])
        hook = (ROOT / "scripts/hooks/hook-whisperx.py").read_text(encoding="utf-8")
        self.assertIn('copy_metadata(distribution.metadata["Name"])', hook)
        self.assertIn('"pyannote/audio/telemetry"', hook)
        self.assertIn("metrics_enabled: false", (ROOT / "scripts/hooks/pyannote-audio/config.yaml").read_text())
        for module in ("whisperx.asr", "whisperx.alignment", "whisperx.vads"):
            self.assertIn(f'"{module}"', hook)

    def test_build_keeps_vad_runtime_and_model_data_in_ai_profiles(self):
        script = (ROOT / "scripts/build-resource-engine.ps1").read_text(encoding="utf-8")
        self.assertIn('"whisperx", "faster_whisper", "transformers"', script)
        self.assertNotIn('"--exclude-module", "onnxruntime"', script)

    def test_smoke_rejects_missing_lazy_asr_module(self):
        def imported(module):
            if module == "whisperx.asr":
                raise ModuleNotFoundError("No module named 'whisperx.asr'")
            return SimpleNamespace()
        with patch.object(engine_main.importlib, "import_module", side_effect=imported):
            with self.assertRaisesRegex(ModuleNotFoundError, "whisperx.asr"):
                engine_main.smoke_test("cpu")

    def test_atomic_response_retries_transient_windows_reader_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "response.json"
            path.write_text('{"old":true}', encoding="utf-8")
            replace = engine_main.os.replace
            attempts = []

            def locked_once(source, target):
                attempts.append((source, target))
                if len(attempts) == 1:
                    raise PermissionError(13, "File is temporarily in use")
                replace(source, target)

            with patch.object(engine_main.os, "replace", side_effect=locked_once), patch.object(engine_main.time, "sleep"):
                engine_main._write_atomic(path, {"ok": True})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"ok": True})
            self.assertEqual(len(attempts), 2)
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_status_failure_does_not_abort_inference_but_response_failure_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "status.json"
            path.write_text('{"current":0}', encoding="utf-8")
            with patch.object(engine_main.os, "replace", side_effect=PermissionError("locked")), patch.object(engine_main.time, "sleep"):
                engine_main._status(path, current=1)
                self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"current": 0})
                with self.assertRaises(PermissionError):
                    engine_main._write_atomic(Path(directory) / "response.json", {"ok": True})
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_atomic_publish_does_not_retry_unrelated_io_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(engine_main.os, "replace", side_effect=OSError("disk full")) as replace:
                with self.assertRaisesRegex(OSError, "disk full"):
                    engine_main._write_atomic(Path(directory) / "response.json", {})
                self.assertEqual(replace.call_count, 1)

    def test_cpu_smoke_rejects_a_cuda_torch_build(self):
        fake_torch = SimpleNamespace(version=SimpleNamespace(cuda="12.8"))
        with (
            patch.dict(engine_main.SMOKE_MODULES, {"cpu": ("torch",)}, clear=True),
            patch.dict(sys.modules, {"torch": fake_torch}),
            patch.object(engine_main.importlib, "import_module", return_value=fake_torch),
            patch.object(engine_main.importlib.metadata, "version", return_value="2.8.0+cu128"),
        ):
            with self.assertRaisesRegex(RuntimeError, "CPU engine contains a CUDA"):
                engine_main.smoke_test("cpu")

    def test_engine_manifest_binds_smoke_to_the_built_profile(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "engine.json"
            with patch(
                "sys.argv",
                [
                    "write-engine-manifest.py",
                    "--profile",
                    "vision",
                    "--version",
                    "4",
                    "--output",
                    str(output),
                ],
            ):
                self.assertEqual(write_manifest.main(), 0)
            payload = __import__("json").loads(output.read_text(encoding="utf-8"))

        self.assertEqual(payload["profile"], "vision")
        self.assertEqual(payload["smoke_command"], ["HaizFlowEngine.exe", "--smoke", "--profile", "vision"])
        self.assertIn("subtitle_ocr", payload)
        self.assertNotIn("transcribe", payload)


if __name__ == "__main__":
    unittest.main()

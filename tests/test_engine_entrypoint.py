import importlib.util
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

"""Storage containment does not depend on a drive letter or project name."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RuntimeStorageContainmentTests(unittest.TestCase):
    def test_configuration_replaces_an_already_cached_tempfile_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "old-temp"
            old.mkdir()
            selected = root / "selected-home"
            environment = dict(
                os.environ,
                HAIZFLOW_SMOKE_TEST="1",
                HAIZFLOW_HOME=str(selected),
                RUNTIME_DATA_DIR=str(selected / "data"),
                PYTHONPATH=str(ROOT / "src"),
            )
            environment.pop("HAIZFLOW_RESOURCE_ROOT", None)
            script = (
                "import tempfile,json; "
                f"tempfile.tempdir={str(old)!r}; "
                "from haizflow.config import TMP_DIR; "
                "before=tempfile.gettempdir(); "
                "with_file=tempfile.NamedTemporaryFile(); "
                "print(json.dumps([TMP_DIR,before,with_file.name])); with_file.close()"
            )
            result = subprocess.run(
                [sys.executable, "-c", script], cwd=ROOT, env=environment, capture_output=True, text=True, timeout=20
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            target, cached, actual = map(Path, json.loads(result.stdout))
            self.assertEqual(target, cached)
            self.assertTrue(actual.is_relative_to(selected))
            self.assertFalse(list(old.iterdir()))

    def test_model_and_package_cache_overrides_cannot_escape_selected_home(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected = root / "selected"
            escape = root / "not-selected"
            environment = dict(
                os.environ,
                HAIZFLOW_SMOKE_TEST="1",
                HAIZFLOW_HOME=str(selected),
                RUNTIME_DATA_DIR=str(selected / "data"),
                MODELS_DIR=str(escape / "models"),
                PIP_CACHE_DIR=str(escape / "pip"),
                UV_CACHE_DIR=str(escape / "uv"),
                HF_HOME=str(escape / "hf"),
                TORCH_HOME=str(escape / "torch"),
                HAIZFLOW_TMP_DIR=str(escape / "tmp"),
                PYTHONPATH=str(ROOT / "src"),
            )
            environment.pop("HAIZFLOW_RESOURCE_ROOT", None)
            script = (
                "import json; from haizflow import config as c; "
                "from haizflow.core.paths import engines_dir,resource_packages_dir; "
                "print(json.dumps([c.MODELS_DIR,c.HF_HOME,c.TORCH_HOME,c.PIP_CACHE_DIR,c.UV_CACHE_DIR,"
                "c.TMP_DIR,str(engines_dir()),str(resource_packages_dir())]))"
            )
            result = subprocess.run(
                [sys.executable, "-c", script], cwd=ROOT, env=environment, capture_output=True, text=True, timeout=20
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            for value in json.loads(result.stdout):
                with self.subTest(path=value):
                    self.assertTrue(Path(value).is_relative_to(selected))
            self.assertFalse(escape.exists())

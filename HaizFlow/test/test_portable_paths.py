import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


class PortablePathTests(unittest.TestCase):
    def test_runtime_environment_stays_under_the_selected_home(self):
        with tempfile.TemporaryDirectory() as temporary:
            environment = os.environ.copy()
            environment.update(
                {
                    "PYTHONPATH": str(SRC),
                    "HAIZFLOW_SMOKE_TEST": "1",
                    "HAIZFLOW_HOME": temporary,
                    "RUNTIME_DATA_DIR": temporary,
                    "MODELS_DIR": "C:\\HaizFlow-escape-test\\models",
                    "HF_HOME": "C:\\HaizFlow-escape-test\\huggingface",
                    "TORCH_HOME": "C:\\HaizFlow-escape-test\\torch",
                    "HAIZFLOW_TMP_DIR": "C:\\HaizFlow-escape-test\\tmp",
                }
            )
            script = (
                "import json, os; import haizflow.config as c; "
                "values = {name: os.environ[name] for name in "
                "('HF_HOME','TORCH_HOME','XDG_CACHE_HOME','NUMBA_CACHE_DIR','MPLCONFIGDIR',"
                "'CUDA_CACHE_PATH','QML_DISK_CACHE_PATH','LOCALAPPDATA','APPDATA','TMP','TEMP')}; "
                "values['MODELS_DIR'] = c.MODELS_DIR; print(json.dumps(values))"
            )
            completed = subprocess.run(
                [sys.executable, "-c", script],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        values = json.loads(completed.stdout.strip())
        selected_home = os.path.normcase(os.path.abspath(temporary))
        for name, value in values.items():
            with self.subTest(name=name):
                self.assertEqual(os.path.commonpath([selected_home, os.path.abspath(value)]), selected_home)

    def test_frozen_release_ignores_machine_wide_path_overrides(self):
        with tempfile.TemporaryDirectory() as temporary:
            install_root = Path(temporary) / "selected-install"
            bundle_root = install_root / "_internal"
            bundle_root.mkdir(parents=True)
            (install_root / "HaizFlow.exe").touch()
            environment = os.environ.copy()
            for name in (
                "HAIZFLOW_HOME", "HAIZFLOW_INSTALL_ROOT", "HAIZFLOW_SMOKE_TEST",
                "APP_DATA_DIR", "RUNTIME_DATA_DIR", "MODELS_DIR", "BIN_DIR",
                "HF_HOME", "TORCH_HOME", "HAIZFLOW_TMP_DIR",
                "HOME", "USERPROFILE",
            ):
                environment.pop(name, None)
            environment.update(
                {
                    "PYTHONPATH": str(SRC),
                    "APP_DATA_DIR": "C:\\HaizFlow-escape-test\\app-data",
                    "RUNTIME_DATA_DIR": "C:\\HaizFlow-escape-test\\runtime-data",
                    "MODELS_DIR": "C:\\HaizFlow-escape-test\\models",
                    "BIN_DIR": "C:\\HaizFlow-escape-test\\bin",
                    "HF_HOME": "C:\\HaizFlow-escape-test\\huggingface",
                    "TORCH_HOME": "C:\\HaizFlow-escape-test\\torch",
                    "HAIZFLOW_TMP_DIR": "C:\\HaizFlow-escape-test\\tmp",
                    "HAIZFLOW_TEST_INSTALL_ROOT": str(install_root),
                    "HAIZFLOW_TEST_BUNDLE_ROOT": str(bundle_root),
                }
            )
            script = (
                "import json, os, sys; "
                "sys.frozen = True; sys.executable = os.environ['HAIZFLOW_TEST_INSTALL_ROOT'] + '/HaizFlow.exe'; "
                "sys._MEIPASS = os.environ['HAIZFLOW_TEST_BUNDLE_ROOT']; "
                "import haizflow.config as c; "
                "names = ('APP_DATA_DIR','RUNTIME_DATA_DIR','MODELS_DIR','BIN_DIR','HF_HOME','TORCH_HOME',"
                "'XDG_CACHE_HOME','NUMBA_CACHE_DIR','MPLCONFIGDIR','CUDA_CACHE_PATH','QML_DISK_CACHE_PATH',"
                "'LOCALAPPDATA','APPDATA','HOME','USERPROFILE','TMP','TEMP'); "
                "print(json.dumps({name: getattr(c, name, os.environ.get(name)) for name in names}))"
            )
            completed = subprocess.run(
                [sys.executable, "-c", script], cwd=ROOT, env=environment,
                capture_output=True, text=True, timeout=15, check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        values = json.loads(completed.stdout.strip())
        selected_home = os.path.normcase(os.path.abspath(install_root))
        for name, value in values.items():
            with self.subTest(name=name):
                self.assertEqual(os.path.commonpath([selected_home, os.path.abspath(value)]), selected_home)


if __name__ == "__main__":
    unittest.main()

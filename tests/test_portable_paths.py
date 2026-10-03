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
    def test_versioned_core_uses_same_install_runtime_not_version_directory(self):
        from haizflow.update.state import provision
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "installation"
            provision(root)
            for value in ("0.1.0", "0.2.0"):
                core = root / "versions" / value
                core.mkdir(parents=True)
                environment = dict(os.environ, PYTHONPATH=str(SRC), HAIZFLOW_TEST_CORE=str(core),
                                   HAIZFLOW_INSTALL_ROOT="C:/HaizFlow-escape-test", HAIZFLOW_HOME="C:/HaizFlow-escape-test")
                environment.pop("HAIZFLOW_SMOKE_TEST", None)
                script = ("import sys, os, json; sys.frozen=True; "
                          "sys.executable=os.environ['HAIZFLOW_TEST_CORE']+'/HaizFlowCore.exe'; "
                          "from haizflow.core.paths import install_root, core_root, app_data_dir; "
                          "print(json.dumps([str(install_root()),str(core_root()),str(app_data_dir())]))")
                result = subprocess.run([sys.executable, "-c", script], env=environment, capture_output=True,
                                        text=True, check=False, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                paths = list(map(Path, json.loads(result.stdout)))
                self.assertEqual(paths, [root, core, root / "runtime"])

    def test_versioned_core_with_bad_marker_does_not_fall_back_to_nested_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "installation"
            core = root / "versions/0.2.0"
            core.mkdir(parents=True)
            (root / "update-layout.json").write_text("{}")
            environment = dict(os.environ, PYTHONPATH=str(SRC), HAIZFLOW_TEST_CORE=str(core))
            environment.pop("HAIZFLOW_SMOKE_TEST", None)
            script = ("import sys, os; sys.frozen=True; "
                      "sys.executable=os.environ['HAIZFLOW_TEST_CORE']+'/HaizFlowCore.exe'; "
                      "from haizflow.core.paths import app_data_dir; app_data_dir()")
            result = subprocess.run([sys.executable, "-c", script], env=environment, capture_output=True,
                                    text=True, check=False, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((core / "runtime").exists())

    def test_portable_profile_includes_native_dialog_shell_folders(self):
        with tempfile.TemporaryDirectory() as temporary:
            environment = os.environ.copy()
            environment.update(
                {
                    "PYTHONPATH": str(SRC),
                    "HAIZFLOW_SMOKE_TEST": "1",
                    "HAIZFLOW_HOME": temporary,
                }
            )
            script = (
                "import json, os; import haizflow.config; "
                "profile = os.environ['USERPROFILE']; "
                "print(json.dumps({name: os.path.isdir(os.path.join(profile, name)) for name in "
                "('Desktop', 'Documents', 'Downloads', 'Music', 'Pictures', 'Videos')}))"
            )
            completed = subprocess.run(
                [sys.executable, "-c", script], cwd=ROOT, env=environment,
                capture_output=True, text=True, timeout=15, check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(all(json.loads(completed.stdout.strip()).values()))

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
                "('HF_HOME','TORCH_HOME','TORCHINDUCTOR_CACHE_DIR','PYTORCH_KERNEL_CACHE_PATH',"
                "'XDG_CACHE_HOME','XDG_DATA_HOME','XDG_CONFIG_HOME','NUMBA_CACHE_DIR','MPLCONFIGDIR',"
                "'EASYOCR_MODULE_PATH','PADDLE_HOME','PADDLEX_HOME','KAGGLEHUB_CACHE',"
                "'CUDA_CACHE_PATH','QML_DISK_CACHE_PATH','NLTK_DATA','LOCALAPPDATA','APPDATA','TMP','TEMP')}; "
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
                "'TORCHINDUCTOR_CACHE_DIR','PYTORCH_KERNEL_CACHE_PATH','XDG_CACHE_HOME','XDG_DATA_HOME',"
                "'XDG_CONFIG_HOME','NUMBA_CACHE_DIR','MPLCONFIGDIR','EASYOCR_MODULE_PATH','PADDLE_HOME',"
                "'PADDLEX_HOME','KAGGLEHUB_CACHE','CUDA_CACHE_PATH','QML_DISK_CACHE_PATH',"
                "'LOCALAPPDATA','APPDATA','HOME','USERPROFILE','NLTK_DATA','TMP','TEMP'); "
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

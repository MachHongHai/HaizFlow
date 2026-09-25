import hashlib
import importlib.util
import json
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import QObject, Signal

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.services.model_bootstrap import ModelAsset
from haizflow.services.resource_packs import ResourcePackDefinition, ResourcePackError, ResourcePackManager


def load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


verify_manifest = load_script("verify-resource-pack-manifest.py")
finalize_pack = load_script("finalize-resource-pack.py")


class ResourcePackManifestTests(unittest.TestCase):
    def test_source_manifest_is_valid_but_not_public_release_ready(self):
        manifest = ROOT / "runtime" / "resource-pack-manifest.json"
        result = verify_manifest.validate_manifest(manifest, strict=False)
        self.assertEqual(result["engine_packs"], 3)
        with self.assertRaisesRegex(RuntimeError, "immutable release URL"):
            verify_manifest.validate_manifest(manifest, strict=True)

    def test_finalize_engine_archive_pins_exact_sizes_and_digest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = root / "packs.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema": 1,
                        "protocol_version": 1,
                        "packs": {
                            pack_id: {
                                "version": "1",
                                "url": "",
                                "sha256": "",
                                "download_size": 1,
                                "installed_size": 1,
                            }
                            for pack_id in verify_manifest.ENGINE_PACKS
                        },
                    }
                ),
                encoding="utf-8",
            )
            archive = root / "engine.zip"
            engine = {
                "pack_id": "engine-cpu-py313",
                "profile": "cpu",
                "version": "2",
                "protocol_version": 1,
                "smoke_command": ["engine.exe", "--smoke", "--profile", "cpu"],
                "rpc_command": ["engine.exe", "--rpc"],
                "hymt2_server": ["engine.exe", "--hymt2-worker", "--server"],
                "omnivoice_worker": ["engine.exe", "--omnivoice-worker"],
                "omnivoice_server": ["engine.exe", "--omnivoice-server"],
                "demucs": ["engine.exe", "--demucs-separate"],
                "transcribe": ["engine.exe", "--transcribe"],
                "runtime_probe": ["engine.exe", "--runtime-probe"],
            }
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("engine.json", json.dumps(engine))
                bundle.writestr("engine.exe", b"binary")

            with patch(
                "sys.argv",
                [
                    "finalize-resource-pack.py",
                    "--manifest",
                    str(manifest),
                    "--pack-id",
                    "engine-cpu-py313",
                    "--version",
                    "2",
                    "--archive",
                    str(archive),
                    "--url",
                    "https://github.com/MachHongHai/HaizFlow/releases/download/v2/engine.zip",
                ],
            ):
                self.assertEqual(finalize_pack.main(), 0)

            record = json.loads(manifest.read_text(encoding="utf-8"))["packs"]["engine-cpu-py313"]
            self.assertEqual(record["version"], "2")
            self.assertEqual(record["download_size"], archive.stat().st_size)
            self.assertEqual(record["installed_size"], len(json.dumps(engine).encode()) + len(b"binary"))
            self.assertEqual(record["sha256"], hashlib.sha256(archive.read_bytes()).hexdigest())

    def test_finalize_rejects_archive_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("../engine.json", "{}")
            with self.assertRaisesRegex(RuntimeError, "Unsafe archive member"):
                finalize_pack._read_engine_archive(archive, "engine-cpu-py313", "1")


class ResourcePackManagerTests(unittest.TestCase):
    def test_bundled_development_engine_still_runs_out_of_process(self):
        definition = ResourcePackDefinition(
            "engine-test",
            "Test engine",
            "processor",
            "1",
            "engine",
            "cpu",
            engine_modules=("json",),
        )
        manager = ResourcePackManager((definition,))
        manager.required_packs = lambda *_args, **_kwargs: ["engine-test"]

        self.assertEqual(manager.external_engine_pack("recognition"), "")
        self.assertEqual(manager.warm_engine_pack("recognition"), "engine-test")
        command = manager.engine_command("engine-test", "rpc_command")
        self.assertEqual(command[:3], [sys.executable, "-m", "haizflow.engine.main"])
        self.assertEqual(command[-1], "--rpc")

    def test_controller_presents_cpu_and_gpu_profiles_as_real_install_units(self):
        from haizflow.desktop.resource_pack_controller import ResourcePackController

        class Host(QObject):
            appAlertRequested = Signal(str, str, str)

            def __init__(self):
                super().__init__()
                self._settings_processing_device = "cpu"
                self._speech_recognition_model = "small"
                self._target_language = "vi"
                self._processing_queue = SimpleNamespace(has_work=False)
                self._device_switching = False
                self._smart_warmup = None

        manager = ResourcePackManager()
        manager.cleanup_previous_storage = lambda: None
        controller = ResourcePackController(Host(), manager)
        try:
            rows = controller.displayRows
            pack_ids = [row["packId"] for row in rows]
            self.assertEqual(len(pack_ids), len(set(pack_ids)))
            self.assertIn("engine-cpu-py313", pack_ids)
            self.assertIn("model-speech-cpu", pack_ids)
            self.assertIn("engine-cuda128-py313", pack_ids)
            self.assertIn("model-speech-gpu", pack_ids)
            self.assertIn("engine-vision-onnx", pack_ids)
            self.assertIn("model-subtitle-ocr", pack_ids)
            self.assertTrue(all("packIds" not in row for row in rows))
        finally:
            controller.shutdown()

    def test_builtin_pack_inventory_can_be_presented(self):
        rows = ResourcePackManager().snapshot()
        self.assertTrue(rows)
        self.assertEqual({row["packId"] for row in rows}, set(ResourcePackManager().definitions))
        self.assertTrue(all(isinstance(row["installedSize"], int) for row in rows))
        self.assertTrue(all(isinstance(row["totalInstalledBytes"], int) for row in rows))

    def test_storage_summary_counts_shared_files_only_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models"
            engines = root / "engines"
            packages = root / "packages"
            (models / "shared").mkdir(parents=True)
            engines.mkdir()
            packages.mkdir()
            (models / "shared" / "vad.bin").write_bytes(b"1234")
            (packages / "cached.zip").write_bytes(b"12")
            with (
                patch("haizflow.services.resource_packs.models_dir", return_value=models),
                patch("haizflow.services.resource_packs.engines_dir", return_value=engines),
                patch("haizflow.services.resource_packs.resource_packages_dir", return_value=packages),
            ):
                self.assertEqual(ResourcePackManager._resource_storage_bytes(), 6)

    def test_capability_mapping_selects_one_integrated_speech_backend(self):
        manager = ResourcePackManager()
        self.assertEqual(
            manager.required_packs("recognition", {"device": "cpu", "language": "en-US"}),
            ["engine-cpu-py313", "model-speech-cpu"],
        )
        self.assertEqual(
            manager.required_packs(
                "recognition", {"device": "gpu", "model": "large-v3-turbo", "language": "en"}
            ),
            ["engine-cuda128-py313", "model-speech-gpu"],
        )
        self.assertEqual(
            manager.required_packs("recognition", {"device": "gpu", "model": "small"}),
            ["engine-cuda128-py313", "model-speech-gpu"],
        )
        self.assertEqual(manager.required_packs("voice", {"provider": "edge"}), [])

    def test_engine_without_pinned_archive_cannot_be_installed(self):
        definition = ResourcePackDefinition(
            "engine-test",
            "Test engine",
            "processor",
            "engine",
            "cpu",
            engine_modules=("module_that_does_not_exist_haizflow",),
        )
        manager = ResourcePackManager((definition,))
        with self.assertRaisesRegex(ResourcePackError, "manifest"):
            manager.install("engine-test", lambda *_args: None)

    def test_requirement_summary_uses_download_install_rollback_and_reserve(self):
        definition = ResourcePackDefinition(
            pack_id="model-test",
            label="Test model",
            group="recognition",
            version="1",
            capability="recognition",
            assets=(),
            download_size=100,
            installed_size=200,
        )
        manager = ResourcePackManager((definition,))
        with (
            patch.object(manager, "status", return_value="missing"),
            patch("haizflow.services.resource_packs.shutil.disk_usage") as disk_usage,
        ):
            disk_usage.return_value = type("Usage", (), {"free": 10_000})()
            summary = manager.requirement_summary(["model-test"])
        self.assertEqual(summary["downloadBytes"], 100)
        self.assertEqual(summary["installedBytes"], 200)
        self.assertEqual(summary["rollbackBytes"], 0)
        self.assertGreater(summary["requiredBytes"], 300)

    def test_model_pack_download_size_counts_only_missing_and_partial_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = ModelAsset("speech", "First", "https://example.invalid/a", "a.bin", 4, "0" * 64)
            second = ModelAsset("speech", "Second", "https://example.invalid/b", "b.bin", 8, "1" * 64)
            definition = ResourcePackDefinition(
                pack_id="model-speech-test",
                label="Speech",
                group="tools",
                version="1",
                capability="speech",
                assets=(first, second),
                download_size=12,
                installed_size=12,
            )
            (root / "a.bin").write_bytes(b"done")
            (root / "b.bin.part").write_bytes(b"123")
            manager = ResourcePackManager((definition,))
            with patch("haizflow.services.resource_packs.models_dir", return_value=root):
                self.assertEqual(manager.download_bytes("model-speech-test"), 5)
                row = manager.snapshot()[0]
            self.assertEqual(row["downloadSize"], 5)

    def test_paused_pack_is_still_reported_as_missing_for_a_capability(self):
        definition = ResourcePackDefinition(
            pack_id="model-test",
            label="Test model",
            group="recognition",
            version="1",
            capability="recognition",
        )
        manager = ResourcePackManager((definition,))
        manager.required_packs = lambda *_args, **_kwargs: ["model-test"]
        with patch.object(manager, "status", return_value="paused"):
            self.assertEqual(manager.missing_packs("recognition"), ["model-test"])

    def test_installed_model_reports_a_missing_processor_dependency(self):
        engine = ResourcePackDefinition(
            "engine-test",
            "Test processor",
            "processor",
            "1",
            "engine",
            engine_modules=("missing_test_engine",),
        )
        model = ResourcePackDefinition(
            "model-test",
            "Test model",
            "recognition",
            "1",
            "recognition",
            dependencies=("engine-test",),
        )
        manager = ResourcePackManager((engine, model))
        with patch.object(manager, "status", side_effect=lambda pack_id: "installed" if pack_id == "model-test" else "missing"):
            rows = {row["packId"]: row for row in manager.snapshot()}
        self.assertIn("Test processor", rows["model-test"]["blockedReason"])

    def test_controller_exposes_active_package_progress_for_status_strip(self):
        from haizflow.desktop.resource_pack_controller import ResourcePackController

        definition = ResourcePackDefinition(
            pack_id="model-test",
            label="Test model",
            group="recognition",
            version="1",
            capability="recognition",
        )
        manager = ResourcePackManager((definition,))
        manager.cleanup_previous_storage = lambda: None
        host = QObject()
        controller = ResourcePackController(host, manager)
        try:
            controller.model.set_operation(
                "model-test",
                status="downloading",
                progress=37,
                detail="Đang tải",
            )
            self.assertEqual(controller.activityProgress, 37)
            self.assertIn("Test model", controller.activityText)
            self.assertIn("Đang tải", controller.activityText)
        finally:
            controller.shutdown()

    def test_progress_updates_do_not_rescan_installed_engine_directories(self):
        from haizflow.desktop.resource_pack_controller import ResourcePackListModel

        definition = ResourcePackDefinition(
            pack_id="model-test",
            label="Test model",
            group="recognition",
            version="1",
            capability="recognition",
        )
        manager = ResourcePackManager((definition,))
        manager.snapshot = Mock(side_effect=AssertionError("disk inventory ran on the UI thread"))
        model = ResourcePackListModel(manager)

        model.set_operation("model-test", status="downloading", progress=10, detail="10%")
        model.set_operation("model-test", status="downloading", progress=80, detail="80%")

        manager.snapshot.assert_not_called()
        self.assertEqual(model._rows[0]["progress"], 80)

    def test_install_and_remove_are_dispatched_without_blocking_the_ui_thread(self):
        from haizflow.desktop.resource_pack_controller import ResourcePackController

        class Host(QObject):
            appAlertRequested = Signal(str, str, str)

            def __init__(self):
                super().__init__()
                self._processing_queue = SimpleNamespace(has_work=False)
                self._device_switching = False
                self._smart_warmup = None

        definition = ResourcePackDefinition(
            pack_id="model-test",
            label="Test model",
            group="recognition",
            version="1",
            capability="recognition",
        )
        manager = ResourcePackManager((definition,))
        manager.cleanup_previous_storage = lambda: None
        snapshot = [{
            "packId": "model-test", "label": "Test model", "group": "recognition",
            "version": "1", "capability": "recognition", "backend": "",
            "status": "missing", "downloadSize": 0, "installedSize": 0,
            "location": str(manager.storage_root), "dependencies": [],
            "canInstall": True, "canRemove": False, "blockedReason": "", "freeBytes": 1,
        }]
        manager.snapshot = Mock(return_value=snapshot)
        install_started = threading.Event()
        release_install = threading.Event()
        remove_started = threading.Event()
        release_remove = threading.Event()

        def install(_pack_id, _progress):
            install_started.set()
            release_install.wait(2)

        manager.install = install
        host = Host()
        controller = ResourcePackController(host, manager)
        try:
            started_at = time.perf_counter()
            controller.installResourcePacks(["model-test"])
            elapsed = time.perf_counter() - started_at
            self.assertLess(elapsed, 0.2)
            self.assertTrue(install_started.wait(1))
            self.assertTrue(controller.busy)
            release_install.set()
            controller._threads["model-test"].join(2)

            def remove(_pack_id, *, in_use=False):
                self.assertFalse(in_use)
                remove_started.set()
                release_remove.wait(2)
                return 123

            manager.remove = remove
            started_at = time.perf_counter()
            self.assertTrue(controller.removeResourcePack("model-test"))
            elapsed = time.perf_counter() - started_at
            self.assertLess(elapsed, 0.2)
            self.assertTrue(remove_started.wait(1))
            release_remove.set()
            controller._threads["model-test"].join(2)
        finally:
            release_install.set()
            release_remove.set()
            controller.shutdown()

    def test_removing_a_model_pack_deletes_its_complete_and_partial_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            asset = ModelAsset("test", "Test", "https://example.invalid/model", "test/model.bin", 4, "0" * 64)
            definition = ResourcePackDefinition(
                pack_id="model-test",
                label="Test model",
                group="recognition",
                version="1",
                capability="recognition",
                assets=(asset,),
            )
            manager = ResourcePackManager((definition,))
            complete = root / asset.relative_path
            complete.parent.mkdir(parents=True)
            complete.write_bytes(b"data")
            partial = complete.with_name(complete.name + ".part")
            partial.write_bytes(b"partial")
            with patch("haizflow.services.resource_packs.models_dir", return_value=root):
                self.assertEqual(manager.status("model-test"), "installed")
                removed = manager.remove("model-test")
                self.assertEqual(removed, 11)
                self.assertFalse(complete.exists())
                self.assertFalse(partial.exists())
                self.assertEqual(manager.status("model-test"), "missing")


if __name__ == "__main__":
    unittest.main()

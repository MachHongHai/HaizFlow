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
    def test_source_manifest_pins_all_public_engines(self):
        manifest = ROOT / "runtime" / "resource-pack-manifest.json"
        result = verify_manifest.validate_manifest(manifest, strict=True)
        self.assertEqual(result["engine_packs"], 3)
        self.assertEqual(result["release_ready"], 3)

    def test_unpublished_fixture_is_not_public_release_ready(self):
        payload = json.loads((ROOT / "runtime/resource-pack-manifest.json").read_text(encoding="utf-8"))
        for record in payload["packs"].values():
            record.update(url="", sha256="")
            record.pop("parts", None)
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "unpublished.json"
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(verify_manifest.validate_manifest(manifest, strict=False)["release_ready"], 0)
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
                "demucs_task": ["engine.exe", "--demucs-rpc"],
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

    def test_finalize_rejects_mutable_data_even_in_empty_directories(self):
        for member in ("runtime/", "runtime/cache/", "runtime/data/config.json", "update-state/"):
            with self.subTest(member=member), tempfile.TemporaryDirectory() as temp_dir:
                archive = Path(temp_dir) / "mutable.zip"
                with zipfile.ZipFile(archive, "w") as bundle:
                    bundle.writestr(member, b"" if member.endswith("/") else b"{}")
                with self.assertRaisesRegex(RuntimeError, "Mutable runtime"):
                    finalize_pack._read_engine_archive(archive, "engine-cpu-py313", "1")


class ResourcePackManagerTests(unittest.TestCase):
    def test_disk_preflight_survives_a_removed_resource_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing = root / "removed/resources"
            manager = ResourcePackManager(())
            with patch("haizflow.services.resource_packs.resource_storage_dir", return_value=missing):
                summary = manager.requirement_summary(())
            self.assertGreater(summary["freeBytes"], 0)
            self.assertFalse(missing.exists(), "A read-only preflight must not recreate storage")

    def test_engine_repair_reserves_staging_space_even_when_status_is_installed(self):
        from dataclasses import replace
        from haizflow.services.resource_packs import MINIMUM_OPERATIONAL_FREE_BYTES

        manager = ResourcePackManager()
        pack_id = "engine-cpu-py313"
        definition = replace(manager.definitions[pack_id], archive_sha256="a" * 64)
        manager.definitions[pack_id] = definition
        with patch.object(manager, "status", return_value="installed"), \
                patch.object(manager, "archive_available", return_value=True), \
                patch.object(manager, "download_bytes", return_value=0), \
                patch.object(manager, "requirement_summary", return_value={
                    "freeBytes": MINIMUM_OPERATIONAL_FREE_BYTES + 1,
                    "requiredBytes": MINIMUM_OPERATIONAL_FREE_BYTES}), \
                patch.object(manager, "_safe_extract_zip") as extract:
            self.assertGreater(definition.installed_size, 1)
            with self.assertRaisesRegex(ResourcePackError, "Không đủ dung lượng"):
                manager.install(pack_id, lambda *_: None, repair=True)
            extract.assert_not_called()
        self.assertFalse(manager._active)

    def test_healthy_model_install_is_a_noop_without_network_or_disk_preflight(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "model.bin").write_bytes(b"data")
            asset = ModelAsset("test", "Test", "https://example.invalid/model", "model.bin", 4,
                               hashlib.sha256(b"data").hexdigest())
            manager = ResourcePackManager((ResourcePackDefinition(
                "model-test", "Test", "tools", "1", "voice", assets=(asset,)),))
            events = []
            with patch("haizflow.services.resource_packs.models_dir", return_value=root), \
                    patch("haizflow.services.resource_packs.install_model_assets") as install, \
                    patch.object(manager, "requirement_summary") as summary:
                manager.install("model-test", lambda _pack, event: events.append(event))
                manager.install("model-test", lambda _pack, event: events.append(event))
            install.assert_not_called()
            summary.assert_not_called()
            self.assertEqual([event.state for event in events], ["ready", "ready"])
            self.assertEqual((root / "model.bin").read_bytes(), b"data")

    def test_model_dedup_allows_healthy_repair_corrupt_repair_and_remove_reinstall(self):
        import io

        class Response(io.BytesIO):
            status = 200
            headers = {"Content-Length": "4"}

            def getcode(self):
                return 200

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            asset = ModelAsset("test", "Test", "https://example.invalid/model", "model.bin", 4,
                               hashlib.sha256(b"data").hexdigest())
            definition = ResourcePackDefinition("model-test", "Test", "tools", "1", "voice", assets=(asset,))
            manager = ResourcePackManager((definition,))
            target = root / asset.relative_path
            with patch("haizflow.services.resource_packs.models_dir", return_value=root), \
                    patch("haizflow.services.resource_packs.resource_storage_dir", return_value=root), \
                    patch("haizflow.services.model_bootstrap._open_download",
                          side_effect=lambda *_: Response(b"data")) as download:
                manager.install("model-test", lambda *_: None)
                stamp = target.stat().st_mtime_ns
                manager.install("model-test", lambda *_: None)
                manager.install("model-test", lambda *_: None, repair=True)
                self.assertEqual(download.call_count, 1)
                self.assertEqual(target.stat().st_mtime_ns, stamp)
                target.write_bytes(b"bad!")
                self.assertEqual(manager.status("model-test"), "missing")
                manager.install("model-test", lambda *_: None, repair=True)
                self.assertEqual(target.read_bytes(), b"data")
                self.assertEqual(download.call_count, 2)
                manager.remove("model-test")
                self.assertFalse(target.exists())
                manager.install("model-test", lambda *_: None)
                self.assertEqual(manager.status("model-test"), "installed")
                self.assertEqual(download.call_count, 3)
                self.assertFalse(target.with_name("model.bin.part").exists())

    def test_healthy_engine_install_is_noop_but_explicit_repair_remains_available(self):
        manager = ResourcePackManager()
        with patch.object(manager, "status", return_value="installed"), \
                patch.object(manager, "archive_available", return_value=True), \
                patch.object(manager, "_install_engine_archive") as install:
            manager.install("engine-cpu-py313", lambda *_args: None)
            install.assert_not_called()
            manager.install("engine-cpu-py313", lambda *_args: None, repair=True)
            install.assert_called_once()

    def test_speaker_backend_remains_bundled_cpu_for_both_device_preferences(self):
        manager = ResourcePackManager()
        self.assertEqual(manager.required_packs("speaker", {"device": "cpu"}),
                         ["engine-speaker-bundled", "model-speaker-identification"])
        self.assertEqual(manager.required_packs("speaker", {"device": "gpu"}),
                         ["engine-speaker-bundled", "model-speaker-identification"])
        packs = manager.required_packs("voice", {"device": "gpu", "provider": "omnivoice", "speaker_mode": "multiple"})
        self.assertIn("engine-cpu-py313", packs)
        self.assertIn("engine-speaker-bundled", packs)
        self.assertNotIn("engine-cuda128-py313", packs)
        self.assertNotIn("engine-vision-onnx", packs)

    def test_bundled_speaker_worker_has_a_frozen_entrypoint(self):
        manager = ResourcePackManager()
        with patch.object(sys, "frozen", True, create=True):
            command = manager.engine_command("engine-speaker-bundled", "rpc_command")
        self.assertEqual(command, [sys.executable, "--engine-worker", "--rpc"])

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
            self.assertEqual(pack_ids, [
                "model-whisper-small", "model-whisper-turbo",
                "model-hymt2-cpu", "model-hymt2-gpu", "model-omnivoice",
                "model-demucs-cpu", "model-demucs-gpu", "model-subtitle-ocr",
            ])
            self.assertTrue(all("packIds" not in row for row in rows))
        finally:
            controller.shutdown()

    def test_builtin_pack_inventory_can_be_presented(self):
        rows = ResourcePackManager().snapshot()
        self.assertTrue(rows)
        self.assertEqual({row["packId"] for row in rows}, set(ResourcePackManager().definitions))
        self.assertTrue(all(isinstance(row["installedSize"], int) for row in rows))
        self.assertTrue(all(isinstance(row["totalInstalledBytes"], int) for row in rows))

    def test_eight_gib_nvidia_gpu_can_select_full_translation_pack(self):
        from haizflow.core.hardware import HardwareCapabilities
        from haizflow.desktop.resource_pack_controller import ResourcePackController

        capabilities = HardwareCapabilities(
            cuda_available=True, cuda_name="RTX 4060 Laptop GPU",
            total_vram_bytes=8 * 1024**3, free_vram_bytes=7 * 1024**3,
            total_ram_bytes=16 * 1024**3, logical_cpu_count=16,
            ac_powered=True, battery_percent=80,
        )
        controller = SimpleNamespace(_host=SimpleNamespace(
            _hardware_capabilities=capabilities, _settings_language="vi",
        ))
        compatible, warning = ResourcePackController._hardware_compatibility(
            controller, "model-hymt2-gpu",
        )
        self.assertTrue(compatible)
        self.assertNotIn("12 GB", warning)

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

    def test_capability_mapping_selects_independent_recognition_and_translation_models(self):
        manager = ResourcePackManager()
        self.assertEqual(
            manager.required_packs("recognition", {"device": "cpu", "language": "en-US"}),
            ["engine-cpu-py313", "model-whisper-small"],
        )
        self.assertEqual(
            manager.required_packs(
                "recognition", {"device": "gpu", "model": "large-v3-turbo", "language": "en"}
            ),
            ["engine-cuda128-py313", "model-whisper-turbo"],
        )
        self.assertEqual(
            manager.required_packs("recognition", {"device": "gpu", "model": "small"}),
            ["engine-cuda128-py313", "model-whisper-small"],
        )
        self.assertEqual(
            manager.required_packs("translation", {"device": "gpu", "translation_model": "q4"}),
            ["engine-cpu-py313", "model-hymt2-cpu"],
        )
        self.assertEqual(
            manager.required_packs("translation", {"device": "gpu", "translation_model": "full"}),
            ["engine-cuda128-py313", "model-hymt2-gpu"],
        )
        self.assertEqual(manager.required_packs("voice", {"provider": "edge"}), ["engine-cpu-py313", "model-omnivoice"])

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

    def test_full_translation_parent_dispatch_keeps_gpu_selection_on_eight_gib_card(self):
        from haizflow.services import translation

        manager = ResourcePackManager()
        profile = SimpleNamespace(key="cuda_low_memory", total_vram_gib=8)
        with (
            patch("haizflow.services.resource_packs.ResourcePackManager", return_value=manager),
            patch("haizflow.core.hardware.runtime_profile", return_value=profile),
            patch.object(manager, "_engine_is_valid", side_effect=lambda definition: definition.pack_id == "engine-cuda128-py313"),
            patch.object(manager, "engine_command", return_value=["gpu-engine", "--hymt2-worker", "--server"]) as command,
            patch.object(translation, "translation_model_preference", return_value="full"),
            patch.object(translation, "is_frozen", return_value=True),
        ):
            self.assertEqual(translation._worker_command(), ["gpu-engine", "--hymt2-worker", "--server"])
            command.assert_called_once_with("engine-cuda128-py313", "hymt2_server")

    def test_frozen_translation_never_falls_back_to_core_without_matching_engine(self):
        from haizflow.services import translation

        for preference in ("q4", "full", "auto"):
            with (
                self.subTest(preference=preference),
                patch.object(translation, "translation_model_preference", return_value=preference),
                patch.object(translation, "runtime_profile", return_value=SimpleNamespace(key="cuda_low_memory")),
                patch("haizflow.services.resource_packs.installed_engine_command", return_value=[]),
                patch.object(translation, "is_frozen", return_value=True),
            ):
                with self.assertRaisesRegex(ResourcePackError, "HY-MT2"):
                    translation._worker_command()

    def test_model_download_runtime_respects_project_cpu_override_and_gpu_voice(self):
        from haizflow.desktop.resource_pack_controller import ResourcePackController

        manager = ResourcePackManager()
        host = SimpleNamespace(_settings_processing_device="gpu", _speech_recognition_model="small-cpu",
                               _tts_provider="omnivoice-gpu", _target_language="vi")
        controller = SimpleNamespace(_host=host, manager=manager)
        controller._display_context = lambda: ResourcePackController._display_context(controller)
        self.assertEqual(ResourcePackController._supporting_packs(controller, "model-whisper-small"),
                         ["engine-cpu-py313"])
        self.assertEqual(ResourcePackController._supporting_packs(controller, "model-omnivoice"),
                         ["engine-cuda128-py313"])

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
            asset = ModelAsset("test", "Test", "https://example.invalid/model", "test/model.bin", 4,
                               hashlib.sha256(b"data").hexdigest())
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

    def test_voice_translation_and_ocr_status_requires_pinned_content(self):
        for pack_id, capability in (("model-omnivoice", "voice"), ("model-hymt2-cpu", "translation"),
                                    ("model-hymt2-gpu", "translation"), ("model-subtitle-ocr", "ocr")):
            with self.subTest(pack_id=pack_id), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                asset = ModelAsset("test", "Test", "https://example.invalid/model", "model.bin", 4,
                                   hashlib.sha256(b"data").hexdigest())
                manager = ResourcePackManager((ResourcePackDefinition(
                    pack_id, "Test", "tools", "1", capability, assets=(asset,)),))
                manager.required_packs = lambda *_args: [pack_id]
                with patch("haizflow.services.resource_packs.models_dir", return_value=root):
                    self.assertEqual(manager.missing_packs(capability), [pack_id])
                    (root / "model.bin").write_bytes(b"oops")
                    self.assertEqual(manager.status(pack_id), "missing")
                    (root / "model.bin").write_bytes(b"data")
                    self.assertEqual(manager.status(pack_id), "installed")
                    self.assertEqual(manager.missing_packs(capability), [])
                    # A previous successful check must not bless a same-size rewrite.
                    (root / "model.bin").write_bytes(b"oops")
                    self.assertEqual(manager.status(pack_id), "missing")
                    self.assertEqual(manager.missing_packs(capability), [pack_id])

    def test_old_voice_runtime_is_not_ready_despite_a_completion_marker(self):
        definition = ResourcePackManager().definitions["engine-cuda128-py313"]
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "complete.json"
            marker.write_text(json.dumps(dict(pack_id=definition.pack_id, version=definition.version,
                protocol_version=1)), encoding="utf-8")
            (marker.parent / "engine.json").write_text(json.dumps(dict(pack_id=definition.pack_id,
                version=definition.version, profile="cuda128", protocol_version=1, runtime_contract=3)), encoding="utf-8")
            manager = ResourcePackManager((definition,))
            with patch.object(manager, "_engine_marker", return_value=marker), \
                    patch.object(manager, "_bundled_engine_available", return_value=False):
                self.assertEqual(manager.status(definition.pack_id), "missing")


if __name__ == "__main__":
    unittest.main()

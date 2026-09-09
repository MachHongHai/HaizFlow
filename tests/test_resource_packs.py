import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

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
    def test_builtin_pack_inventory_can_be_presented(self):
        rows = ResourcePackManager().snapshot()
        self.assertTrue(rows)
        self.assertEqual({row["packId"] for row in rows}, set(ResourcePackManager().definitions))
        self.assertTrue(all(isinstance(row["installedSize"], int) for row in rows))

    def test_capability_mapping_selects_one_backend_and_one_alignment_language(self):
        manager = ResourcePackManager()
        self.assertEqual(
            manager.required_packs("recognition", {"device": "cpu", "language": "en-US"}),
            ["engine-cpu-py313", "model-whisper-small", "model-alignment-en"],
        )
        self.assertEqual(
            manager.required_packs(
                "recognition", {"device": "gpu", "model": "large-v3-turbo", "language": "en"}
            ),
            ["engine-cuda128-py313", "model-whisper-turbo", "model-alignment-en"],
        )
        self.assertEqual(
            manager.required_packs("recognition", {"device": "gpu", "model": "small"}),
            ["engine-cuda128-py313", "model-whisper-small"],
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


if __name__ == "__main__":
    unittest.main()

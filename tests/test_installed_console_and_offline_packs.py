import ast
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from haizflow.services.resource_packs import ResourcePackDefinition, ResourcePackError, ResourcePackManager


class ConsoleTests(unittest.TestCase):
    def test_background_process_calls_request_no_console(self):
        for path in (ROOT / "src/haizflow").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess"
                        and node.func.attr in {"run", "Popen", "check_output", "check_call", "call"}):
                    continue
                # Intentional, user-requested GUI installer and Linux opener.
                if path.name == "app_update_controller.py" and isinstance(node.args[0], ast.List):
                    continue
                if path.name == "media.py" and "xdg-open" in ast.unparse(node):
                    continue
                if path.name == "audio.py":
                    continue  # tested adapter below sets flags in kwargs
                with self.subTest(path=str(path), line=node.lineno):
                    self.assertIn("creationflags", [keyword.arg for keyword in node.keywords])

    def test_pydub_adapter_is_scoped_and_preserves_existing_flags(self):
        from haizflow.utils import audio
        from pydub import audio_segment, utils

        original = subprocess.Popen
        with patch("haizflow.utils.audio.subprocess.Popen") as popen, \
                patch.object(subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True):
            audio_segment.subprocess.Popen(["ffmpeg"], creationflags=8)
            self.assertEqual(popen.call_args.kwargs["creationflags"], 0x08000008)
            utils.Popen(["ffprobe"])
            self.assertEqual(popen.call_args.kwargs["creationflags"], 0x08000000)
            self.assertIs(audio.AudioSegment, audio_segment.AudioSegment)
        self.assertIs(subprocess.Popen, original)

    def test_library_probe_and_decode_calls_are_also_hidden(self):
        from haizflow.utils.audio import _MediaSubprocess

        with patch.object(subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True):
            for name in ("run", "check_output", "call", "check_call"):
                with self.subTest(name=name), patch.object(subprocess, name) as method:
                    getattr(_MediaSubprocess(), name)(["ffprobe"], creationflags=8)
                    self.assertEqual(method.call_args.kwargs["creationflags"], 0x08000008)

    @unittest.skipUnless(sys.platform == "win32", "Windows child-console regression")
    def test_actual_child_has_no_console(self):
        from haizflow.utils.audio import _hidden_popen

        process = _hidden_popen([sys.executable, "-c",
                                "import ctypes; print(ctypes.windll.kernel32.GetConsoleWindow())"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate(timeout=15)
        self.assertEqual(process.returncode, 0, stderr)
        self.assertEqual(stdout.strip(), "0")


class OfflinePackTests(unittest.TestCase):
    def test_installer_pointer_and_utf16_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            companion = root / "tài nguyên"
            companion.mkdir()
            with patch("haizflow.services.resource_packs.install_root", return_value=root):
                for encoding in ("utf-8-sig", "utf-16"):
                    (root / "offline-resources.ini").write_text(
                        f"[resources]\npath={companion}\n", encoding=encoding)
                    self.assertEqual(ResourcePackManager._offline_root(), companion)
                (root / "offline-resources.ini").write_text("[resources]\npath=../outside\n", encoding="utf-8")
                with self.assertRaises(ResourcePackError):
                    ResourcePackManager._offline_root()

    def _fixture(self, root):
        companion = root / "offline-resources"
        companion.mkdir()
        archive = companion / "engine-cpu-py313-2.zip"
        engine = dict(pack_id="engine-cpu-py313", profile="cpu", version="2", protocol_version=1,
                      smoke_command=["engine.exe", "--smoke"])
        from haizflow.services.resource_packs import ENGINE_REQUIRED_COMMANDS
        for command in ENGINE_REQUIRED_COMMANDS["engine-cpu-py313"]:
            engine.setdefault(command, ["engine.exe", "--" + command])
        with zipfile.ZipFile(archive, "w") as package:
            package.writestr("engine.json", json.dumps(engine))
            package.writestr("engine.exe", b"fixture executable")
        definition = ResourcePackDefinition("engine-cpu-py313", "CPU", "processor", "2", "engine",
            engine_modules=("test_missing_ai_module",), offline_archive=archive.name,
            archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), download_size=archive.stat().st_size,
            installed_size=len(json.dumps(engine).encode()) + len(b"fixture executable"))
        return archive, definition, engine

    def test_offline_install_verifies_without_network_or_duplicate_zip(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, definition, engine = self._fixture(root)
            manager = ResourcePackManager((definition,))
            from contextlib import ExitStack
            with ExitStack() as stack:
                stack.enter_context(patch("haizflow.services.resource_packs.install_root", return_value=root))
                stack.enter_context(patch("haizflow.services.resource_packs.engines_dir", return_value=root / "engines"))
                stack.enter_context(patch("haizflow.services.resource_packs.resource_packages_dir", return_value=root / "packages"))
                stack.enter_context(patch.object(manager, "_verify_engine_staging", return_value=engine))
                stack.enter_context(patch.object(manager, "requirement_summary", return_value={"freeBytes": 10, "requiredBytes": 1}))
                network = stack.enter_context(patch("urllib.request.urlopen", side_effect=AssertionError("Network forbidden")))
                self.assertTrue(manager.archive_available(definition.pack_id))
                self.assertEqual(manager.download_bytes(definition.pack_id), 0)
                events = []
                manager.install(definition.pack_id, lambda _, event: events.append(event.state))
                self.assertEqual(manager.status(definition.pack_id), "installed")
                self.assertEqual(events[-1], "ready")
                self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), definition.archive_sha256)
                self.assertFalse((root / "packages" / archive.name).exists())
                network.assert_not_called()

    def test_corrupt_offline_pack_is_rejected_before_executing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, definition, _ = self._fixture(root)
            archive.write_bytes(b"x" * archive.stat().st_size)
            manager = ResourcePackManager((definition,))
            with patch.object(manager, "_offline_root", return_value=archive.parent), \
                    patch.object(manager, "requirement_summary", return_value={"freeBytes": 10, "requiredBytes": 1}), \
                    patch.object(manager, "_verify_engine_staging") as smoke:
                with self.assertRaisesRegex(ResourcePackError, "bị hỏng"):
                    manager.install(definition.pack_id, lambda *_: None)
                smoke.assert_not_called()
                self.assertEqual(manager._active, set())

    def test_invalid_filename_and_missing_companion_fail_closed(self):
        definition = ResourcePackDefinition("test", "Test", "processor", "1", "engine",
            engine_modules=("test_missing_ai_module",), offline_archive="../evil.zip")
        manager = ResourcePackManager((definition,))
        self.assertFalse(manager.archive_available("test"))
        with self.assertRaises(ResourcePackError):
            manager.install("test", lambda *_: None)

    def test_offline_catalog_remains_forbidden_for_public_release(self):
        spec = importlib.util.spec_from_file_location("verify_catalog", ROOT / "scripts/verify-resource-pack-manifest.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "packs.json"
            payload = dict(schema=1, protocol_version=1, packs={
                name: dict(version="1", url="", sha256="a" * 64, download_size=1,
                           installed_size=1, offline_archive=name + "-1.zip") for name in module.ENGINE_PACKS})
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(module.validate_manifest(path, strict=False)["release_ready"], 0)
            with self.assertRaisesRegex(RuntimeError, "engineering"):
                module.validate_manifest(path, strict=True)


if __name__ == "__main__":
    unittest.main()

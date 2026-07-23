import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


release_preflight = load_script("release-preflight.py")
finalize_release = load_script("finalize-release.py")
generate_icon = load_script("generate-app-icon.py")
generate_version = load_script("generate-version-resource.py")


class ReleaseToolingTests(unittest.TestCase):
    def test_upgrade_space_is_two_artifact_copies_plus_headroom(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "HaizFlow"
            artifact.mkdir()
            (artifact / "HaizFlow.exe").write_bytes(b"a" * 1024)
            (artifact / "payload.bin").write_bytes(b"b" * 2048)
            requirements = release_preflight.requirements(artifact, upgrade=True)

        self.assertEqual(requirements["artifact_bytes"], 3072)
        self.assertEqual(requirements["required_free_bytes"], 3072 * 2 + release_preflight.WORKING_HEADROOM_BYTES)

    def test_generated_icon_and_version_resource_are_valid_build_inputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            icon = root / "HaizFlow.ico"
            version = root / "version.txt"
            self.assertEqual(generate_icon.main(["--output", str(icon)]), 0)
            self.assertEqual(generate_version.main(["--output", str(version)]), 0)

            self.assertEqual(icon.read_bytes()[:4], b"\x00\x00\x01\x00")
            self.assertIn("VSVersionInfo(", version.read_text(encoding="utf-8"))

    def test_manifest_verification_detects_the_final_artifact_set(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "HaizFlow"
            artifact.mkdir()
            (artifact / "HaizFlow.exe").write_bytes(b"release")
            (artifact / "INSTALL-REQUIREMENTS.json").write_text(json.dumps({"required_free_bytes": 1}), encoding="utf-8")
            finalize_release.finalize(artifact, cpu_model=False, gpu_model=False, whisper_model=False)
            finalize_release.verify_manifest(artifact)
            (artifact / "after-checksum.txt").write_text("late mutation", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                finalize_release.verify_manifest(artifact)

    def test_installer_preserves_runtime_and_requires_writable_target(self):
        installer = (ROOT / "installer" / "HaizFlow.iss").read_text(encoding="utf-8")
        self.assertIn('Excludes: "runtime\\*"', installer)
        self.assertIn("DefaultDirName={code:DefaultInstallDir}", installer)
        self.assertIn("ExtractFileDrive(ExpandConstant('{srcexe}'))", installer)
        self.assertIn("ForceDirectories(WizardDirValue)", installer)
        self.assertIn("SaveStringToFile(ProbePath", installer)
        self.assertIn("[InstallDelete]", installer)
        self.assertIn('Name: "{app}\\_internal"', installer)
        self.assertNotIn("[UninstallDelete]", installer)

    def test_installer_eligibility_rejects_dirty_or_partial_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "HaizFlow"
            model_root = artifact / "_internal" / "models"
            (model_root / "whisper" / "small").mkdir(parents=True)
            (model_root / "whisper" / "small" / "model.bin").write_bytes(b"model")
            (model_root / "hymt2-gguf").mkdir()
            (model_root / "hymt2-transformers").mkdir()
            sys.path.insert(0, str(ROOT / "src"))
            from haizflow.core.model_integrity import HYMT2_CPU_FILE
            (model_root / "hymt2-gguf" / HYMT2_CPU_FILE).write_bytes(b"model")
            (model_root / "hymt2-transformers" / "config.json").write_text("{}", encoding="utf-8")
            (model_root / "hymt2-transformers" / "model.safetensors").write_bytes(b"model")
            (artifact / "HaizFlow.exe").write_bytes(b"release")

            def clean_git(*arguments):
                if arguments == ("rev-parse", "HEAD"):
                    return "test-commit"
                if arguments == ("status", "--porcelain"):
                    return ""
                return "main"

            with patch.object(finalize_release, "_git_value", side_effect=clean_git):
                finalize_release.finalize(artifact, cpu_model=True, gpu_model=True, whisper_model=True)
                finalize_release.verify_installer_eligibility(artifact)
                (model_root / "hymt2-transformers" / "config.json").unlink()
                # Re-finalise so the checksum is valid; eligibility must still
                # reject a partial payload rather than relying on the manifest
                # alone to catch this case.
                finalize_release.finalize(artifact, cpu_model=True, gpu_model=True, whisper_model=True)
                with self.assertRaisesRegex(RuntimeError, "Required bundled model payload"):
                    finalize_release.verify_installer_eligibility(artifact)

            def dirty_git(*arguments):
                if arguments == ("status", "--porcelain"):
                    return " M changed.py"
                return clean_git(*arguments)

            with patch.object(finalize_release, "_git_value", side_effect=dirty_git):
                with self.assertRaisesRegex(RuntimeError, "dirty"):
                    finalize_release.verify_installer_eligibility(artifact)


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
import struct
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
download_ffmpeg = load_script("download_ffmpeg.py")


class ReleaseToolingTests(unittest.TestCase):
    def test_ffmpeg_downloader_rejects_unapproved_or_non_https_sources(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            download_ffmpeg.urllib.request, "urlopen"
        ) as urlopen:
            destination = Path(temp_dir) / "ffmpeg.zip"
            for source in ("file:///tmp/ffmpeg.zip", "http://ffmpeg.org/ffmpeg.zip", "https://example.test/a.zip"):
                with self.subTest(source=source), self.assertRaisesRegex(RuntimeError, "unapproved download source"):
                    download_ffmpeg._download(source, destination, "0" * 64)
            urlopen.assert_not_called()

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
            self.assertEqual(struct.unpack("<H", icon.read_bytes()[4:6])[0], 5)
            self.assertIn("VSVersionInfo(", version.read_text(encoding="utf-8"))

    def test_desktop_branding_assets_are_packaged_from_the_runtime_location(self):
        main_source = (ROOT / "src" / "haizflow" / "desktop" / "main.py").read_text(encoding="utf-8")
        build_script = (ROOT / "scripts" / "build-exe.ps1").read_text(encoding="utf-8")
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn('parent / "assets" / "branding"', main_source)
        self.assertNotIn('parent / "qml" / "assets" / "branding"', main_source)
        self.assertIn('$BrandingAssetsPath', build_script)
        self.assertIn('"haizflow-mark.png", "haizflow.ico"', build_script)
        self.assertIn('"assets/branding/haizflow.ico"', pyproject)

    def test_manifest_verification_detects_the_final_artifact_set(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "HaizFlow"
            artifact.mkdir()
            (artifact / "HaizFlow.exe").write_bytes(b"release")
            (artifact / "INSTALL-REQUIREMENTS.json").write_text(json.dumps({"required_free_bytes": 1}), encoding="utf-8")
            finalize_release.finalize(artifact)
            finalize_release.verify_manifest(artifact)
            (artifact / "after-checksum.txt").write_text("late mutation", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                finalize_release.verify_manifest(artifact)

    def test_installer_preserves_runtime_and_requires_writable_target(self):
        installer = (ROOT / "installer" / "HaizFlow.iss").read_text(encoding="utf-8")
        self.assertNotIn('Excludes: "runtime\\*"', installer)
        self.assertIn(
            'Source: "{#SourceDir}\\*"; DestDir: "{app}"; '
            "Flags: ignoreversion recursesubdirs createallsubdirs",
            installer,
        )
        self.assertIn("DefaultDirName={localappdata}\\Programs\\{#AppName}", installer)
        self.assertIn("UsePreviousAppDir=yes", installer)
        self.assertIn("DisableDirPage=auto", installer)
        self.assertNotIn("ExtractFileDrive(ExpandConstant('{srcexe}'))", installer)
        self.assertNotIn("PrivilegesRequiredOverridesAllowed", installer)
        self.assertIn("ForceDirectories(WizardDirValue)", installer)
        self.assertIn("FreshTargetHasConflictingContent", installer)
        self.assertIn("The selected folder is not empty", installer)
        self.assertIn("SaveStringToFile(ProbePath", installer)
        self.assertIn("GetSpaceOnDisk64(WizardDirValue, FreeBytes, TotalBytes)", installer)
        self.assertNotIn("GetSpaceOnDisk(WizardDirValue, False", installer)
        self.assertIn("RequiredBytes := {#RequiredFreshBytes}", installer)
        self.assertIn("RequiredBytes := {#RequiredFreeBytes}", installer)
        self.assertIn("[InstallDelete]", installer)
        self.assertIn('Name: "{app}\\_internal"', installer)
        self.assertNotIn("[UninstallDelete]", installer)
        self.assertIn('Name: "{app}\\runtime"; Flags: uninsneveruninstall', installer)
        self.assertIn("DeleteRuntimeOnUninstall", installer)
        self.assertIn("UninstallSilent", installer)
        self.assertIn("DelTree(ExpandConstant('{app}\\runtime')", installer)

    def test_installer_targets_supported_windows_and_uses_generated_icon(self):
        installer = (ROOT / "installer" / "HaizFlow.iss").read_text(encoding="utf-8")
        build_script = (ROOT / "scripts" / "build-installer.ps1").read_text(encoding="utf-8")

        self.assertIn("ArchitecturesAllowed=x64compatible", installer)
        self.assertIn("ArchitecturesInstallIn64BitMode=x64compatible", installer)
        self.assertIn("MinVersion=10.0.17763", installer)
        self.assertIn("AllowUNCPath=no", installer)
        self.assertIn("AllowNetworkDrive=no", installer)
        self.assertIn("SetupIconFile={#SetupIconPath}", installer)
        self.assertIn("generate-app-icon.py", build_script)
        self.assertIn('"/DSetupIconPath=$SetupIconPath"', build_script)
        self.assertIn('"/DRequiredFreshBytes=$($FreshRequirements.required_free_bytes)"', build_script)
        self.assertIn("function PrepareToInstall(var NeedsRestart: Boolean): String;", installer)
        self.assertIn("FileExists(AddBackslash(Path) + 'HaizFlow.exe') and", installer)
        self.assertIn("FileExists(AddBackslash(Path) + 'BUILD-INFO.json') and", installer)
        self.assertIn("DirExists(AddBackslash(Path) + '_internal');", installer)
        self.assertNotIn("DirExists(AddBackslash(Path) + 'runtime')", installer)

    def test_release_build_enforces_dependency_vulnerability_audit(self):
        build_script = (ROOT / "scripts" / "build-exe.ps1").read_text(encoding="utf-8")
        audit_script = (ROOT / "scripts" / "audit-dependencies.ps1").read_text(encoding="utf-8")
        test_script = (ROOT / "scripts" / "test.ps1").read_text(encoding="utf-8")
        smoke_script = (ROOT / "scripts" / "smoke-test-frozen.ps1").read_text(encoding="utf-8")

        self.assertIn('Join-Path $PSScriptRoot "test.ps1"', build_script)
        self.assertIn('Join-Path $PSScriptRoot "audit-dependencies.ps1"', build_script)
        self.assertIn('"$WhisperxMelFilters;whisperx\\assets"', build_script)
        self.assertNotIn('@("--collect-data", "whisperx")', build_script)
        self.assertIn('@("--collect-all", "demucs")', build_script)
        self.assertNotIn("--add-data\", \"$ModelPath;models", build_script)
        self.assertNotIn("--demucs-model", build_script)
        self.assertNotIn("--alignment-models", build_script)
        self.assertIn("PreFinalize = $true", build_script)
        self.assertIn("$env:HAIZFLOW_HOME = $SmokeRoot", smoke_script)
        self.assertIn("$env:MODELS_DIR = $SmokeModels", smoke_script)
        self.assertIn("Wait-Process -Id $Process.Id -Timeout $TimeoutSeconds", smoke_script)
        self.assertNotIn('"--runtime-probe"', smoke_script)
        self.assertNotIn('"--demucs-separate"', smoke_script)
        self.assertLess(
            smoke_script.index('$env:HAIZFLOW_SMOKE_TEST = "1"'),
            smoke_script.index("Invoke-FrozenCheck -Arguments $ReleaseArguments"),
        )
        self.assertIn("qmllint.exe", test_script)
        self.assertIn('Join-Path $Root "build\\test-temp"', test_script)
        self.assertIn("$env:TEMP = $TestTemp", test_script)
        self.assertIn('"pip-audit==2.10.1"', audit_script)
        self.assertIn("$CanonicalTorchPackages", audit_script)
        self.assertIn("Canonical PyTorch vulnerability audit found an unreviewed advisory.", audit_script)
        self.assertIn("Dependency vulnerability audit found an unreviewed advisory.", audit_script)
        self.assertNotIn("--ignore-vuln *", audit_script)

        entrypoint = (ROOT / "haizflow_desktop.py").read_text(encoding="utf-8")
        self.assertIn('"--demucs-separate"', entrypoint)
        self.assertIn("from demucs.separate import main as run_demucs", entrypoint)

    def test_transformer_model_loading_disables_remote_code_and_requires_safetensors(self):
        worker = (ROOT / "src" / "haizflow" / "services" / "hymt2_worker.py").read_text(encoding="utf-8")

        self.assertGreaterEqual(worker.count("trust_remote_code=False"), 1)
        self.assertIn('"trust_remote_code": False', worker)
        self.assertIn('"use_safetensors": True', worker)
        self.assertNotIn("trust_remote_code=True", worker)

    def test_installer_eligibility_rejects_dirty_or_partial_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "HaizFlow"
            model_root = artifact / "_internal" / "models"
            artifact.mkdir(parents=True)
            (artifact / "HaizFlow.exe").write_bytes(b"release")

            def clean_git(*arguments):
                if arguments == ("rev-parse", "HEAD"):
                    return "test-commit"
                if arguments == ("status", "--porcelain"):
                    return ""
                return "main"

            with patch.object(finalize_release, "_git_value", side_effect=clean_git):
                finalize_release.finalize(artifact)
                finalize_release.verify_installer_eligibility(artifact)
                model_root.mkdir(parents=True)
                (model_root / "accidental-model.bin").write_bytes(b"model")
                # Re-finalise so checksums are valid; eligibility must reject
                # even an internally consistent artifact that embeds a model.
                finalize_release.finalize(artifact)
                with self.assertRaisesRegex(RuntimeError, "must not be bundled"):
                    finalize_release.verify_installer_eligibility(artifact)
                (model_root / "accidental-model.bin").unlink()
                model_root.rmdir()
                runtime_root = artifact / "runtime"
                runtime_root.mkdir()
                finalize_release.finalize(artifact)
                with self.assertRaisesRegex(RuntimeError, "root runtime"):
                    finalize_release.verify_installer_eligibility(artifact)
                runtime_root.rmdir()

            def dirty_git(*arguments):
                if arguments == ("status", "--porcelain"):
                    return " M changed.py"
                return clean_git(*arguments)

            with patch.object(finalize_release, "_git_value", side_effect=dirty_git):
                with self.assertRaisesRegex(RuntimeError, "dirty"):
                    finalize_release.verify_installer_eligibility(artifact)


if __name__ == "__main__":
    unittest.main()

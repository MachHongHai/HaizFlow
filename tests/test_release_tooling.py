import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image


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
generate_version = load_script("generate-version-resource.py")
download_ffmpeg = load_script("download_ffmpeg.py")


class ReleaseToolingTests(unittest.TestCase):
    def test_ffmpeg_downloader_rejects_unapproved_or_non_https_sources(self):
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch.object(download_ffmpeg.urllib.request, "urlopen") as urlopen,
        ):
            destination = Path(temp_dir) / "ffmpeg.zip"
            for source in ("file:///tmp/ffmpeg.zip", "http://ffmpeg.org/ffmpeg.zip", "https://example.test/a.zip"):
                with self.subTest(source=source), self.assertRaisesRegex(RuntimeError, "unapproved download source"):
                    download_ffmpeg._download(source, destination, "0" * 64)
            urlopen.assert_not_called()

    def test_upgrade_space_only_counts_core_copies_and_safety_headroom(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "HaizFlow"
            artifact.mkdir()
            (artifact / "HaizFlow.exe").write_bytes(b"a" * 1024)
            (artifact / "payload.bin").write_bytes(b"b" * 2048)
            requirements = release_preflight.requirements(artifact, upgrade=True)

        self.assertEqual(requirements["artifact_bytes"], 3072)
        self.assertEqual(
            requirements["required_free_bytes"],
            3072 * 2 + release_preflight.WORKING_HEADROOM_BYTES,
        )
        self.assertEqual(requirements["first_run_model_bytes"], 0)
        self.assertEqual(requirements["recommended_free_bytes"], release_preflight.RECOMMENDED_HEADROOM_BYTES)
        self.assertEqual(
            requirements["working_headroom_bytes"],
            release_preflight.MINIMUM_OPERATIONAL_FREE_BYTES,
        )
        self.assertEqual(requirements["cpu_first_run_model_bytes"], 0)
        self.assertEqual(requirements["gpu_first_run_model_bytes"], 0)
        self.assertFalse(requirements["resource_packs_included"])

    def test_embedded_storage_manifest_counts_its_own_final_size(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "HaizFlow"
            artifact.mkdir()
            (artifact / "HaizFlow.exe").write_bytes(b"release")
            manifest = artifact / "INSTALL-REQUIREMENTS.json"
            payload, serialized = release_preflight.requirements_with_embedded_manifest(
                artifact,
                manifest,
                upgrade=True,
            )
            manifest.write_text(serialized, encoding="utf-8", newline="\n")

            self.assertEqual(payload["artifact_bytes"], release_preflight.directory_size(artifact))
            self.assertEqual(json.loads(manifest.read_text(encoding="utf-8")), payload)

    def test_brand_icon_and_generated_version_resource_are_valid_build_inputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            version = root / "version.txt"
            self.assertEqual(generate_version.main(["--output", str(version)]), 0)

            icon = ROOT / "src" / "haizflow" / "desktop" / "assets" / "branding" / "haizflow.ico"
            self.assertEqual(icon.read_bytes()[:4], b"\x00\x00\x01\x00")
            self.assertIn("VSVersionInfo(", version.read_text(encoding="utf-8"))

    def test_desktop_brand_asset_uses_the_supplied_warm_mark(self):
        mark_path = ROOT / "src" / "haizflow" / "desktop" / "assets" / "branding" / "haizflow-mark.png"
        with Image.open(mark_path) as mark:
            self.assertEqual(mark.size, (1254, 1254))
            pixels = list(mark.convert("RGBA").get_flattened_data())
        self.assertTrue(any(r > 210 and g > 110 and b < 150 and a > 0 for r, g, b, a in pixels))
        self.assertTrue(any(20 < r < 100 and g < 55 and b < 55 and a > 0 for r, g, b, a in pixels))

    def test_desktop_branding_assets_are_packaged_from_the_runtime_location(self):
        main_source = (ROOT / "src" / "haizflow" / "desktop" / "main.py").read_text(encoding="utf-8")
        build_script = (ROOT / "scripts" / "build-exe.ps1").read_text(encoding="utf-8")
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn('parent / "assets" / "branding"', main_source)
        self.assertNotIn('parent / "qml" / "assets" / "branding"', main_source)
        self.assertIn("$BrandingAssetsPath", build_script)
        self.assertNotIn("generate-brand-assets.py", build_script)
        self.assertNotIn("generate-app-icon.py", build_script)
        self.assertIn('"haizflow-mark.png", "haizflow.ico"', build_script)
        self.assertIn('"assets/branding/haizflow.ico"', pyproject)

    def test_qml_icons_and_translation_catalog_are_packaged(self):
        build_script = (ROOT / "scripts" / "build-exe.ps1").read_text(encoding="utf-8")
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        catalog = ROOT / "src" / "haizflow" / "desktop" / "translations" / "haizflow_en.qm"

        self.assertTrue(catalog.is_file())
        self.assertIn("$QmlPath;haizflow\\desktop\\qml", build_script)
        self.assertIn("$TranslationsPath;haizflow\\desktop\\translations", build_script)
        self.assertIn('"qml/*.qml"', pyproject)
        self.assertIn('"qml/icons/*.svg"', pyproject)
        self.assertIn('"translations/*.qm"', pyproject)

    def test_manifest_verification_detects_the_final_artifact_set(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "HaizFlow"
            artifact.mkdir()
            (artifact / "HaizFlow.exe").write_bytes(b"release")
            (artifact / "INSTALL-REQUIREMENTS.json").write_text(
                json.dumps({"required_free_bytes": 1}), encoding="utf-8"
            )
            finalize_release.finalize(artifact)
            finalize_release.verify_manifest(artifact)
            (artifact / "after-checksum.txt").write_text("late mutation", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                finalize_release.verify_manifest(artifact)

    def test_installer_preserves_runtime_and_requires_writable_target(self):
        installer = (ROOT / "installer" / "HaizFlow.iss").read_text(encoding="utf-8")
        self.assertNotIn('Excludes: "runtime\\*"', installer)
        self.assertIn(
            'Source: "{#SourceDir}\\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs',
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
        self.assertIn("RecommendedBytes := {#RecommendedFreshBytes}", installer)
        self.assertIn("RecommendedBytes := {#RecommendedFreeBytes}", installer)
        self.assertNotIn("CpuModelBytes", installer)
        self.assertNotIn("GpuModelBytes", installer)
        self.assertIn("AI engines and models are optional", installer)
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
        self.assertIn("WizardStyle=modern dark slate includetitlebar hidebevels", installer)
        self.assertIn("WizardImageFile={#BrandingMarkPath}", installer)
        self.assertIn("WizardSmallImageFile={#BrandingMarkPath}", installer)
        self.assertIn("System requirements", installer)
        self.assertIn("CPU mode works without an NVIDIA GPU", installer)
        self.assertIn("CloseApplicationsFilter=HaizFlow.exe", installer)
        self.assertIn("SetupLogging=yes", installer)
        self.assertNotIn("generate-app-icon.py", build_script)
        self.assertIn('"/DSetupIconPath=$SetupIconPath"', build_script)
        self.assertIn('"/DBrandingMarkPath=$BrandingMarkPath"', build_script)
        self.assertIn('"/DOutputBaseFilename=$OutputBaseFilename"', build_script)
        self.assertIn('"/DRequiredFreshBytes=$($FreshRequirements.required_free_bytes)"', build_script)
        self.assertIn('"/DRecommendedFreshBytes=$($FreshRequirements.recommended_free_bytes)"', build_script)
        self.assertIn('"/DArtifactBytes=$($FreshRequirements.artifact_bytes)"', build_script)
        self.assertNotIn("/DCpuModelBytes", build_script)
        self.assertNotIn("/DGpuModelBytes", build_script)
        self.assertIn("function PrepareToInstall(var NeedsRestart: Boolean): String;", installer)
        self.assertIn("FileExists(AddBackslash(Path) + 'HaizFlow.exe') and", installer)
        self.assertIn("FileExists(AddBackslash(Path) + 'BUILD-INFO.json') and", installer)
        self.assertIn("DirExists(AddBackslash(Path) + '_internal');", installer)
        self.assertNotIn("DirExists(AddBackslash(Path) + 'runtime')", installer)

    def test_public_builds_require_signing_and_installer_is_smoke_tested(self):
        executable_build = (ROOT / "scripts" / "build-exe.ps1").read_text(encoding="utf-8")
        installer_build = (ROOT / "scripts" / "build-installer.ps1").read_text(encoding="utf-8")
        installer_smoke = (ROOT / "scripts" / "test-installer.ps1").read_text(encoding="utf-8")

        self.assertIn("[switch]$AllowUnsigned", executable_build)
        self.assertIn("[switch]$AllowUnsigned", installer_build)
        self.assertIn("A public release requires Authenticode signing", executable_build)
        self.assertIn("A public release installer requires Authenticode signing", installer_build)
        self.assertIn("-UNSIGNED-Setup", installer_build)
        self.assertIn('Join-Path $PSScriptRoot "test-installer.ps1"', installer_build)
        self.assertIn('"/VERYSILENT"', installer_smoke)
        self.assertIn("-InstalledLayout", installer_smoke)
        self.assertIn("Silent uninstall must preserve runtime data", installer_smoke)

    def test_release_build_temporary_files_stay_below_project_build_directory(self):
        executable_build = (ROOT / "scripts" / "build-exe.ps1").read_text(encoding="utf-8")
        installer_build = (ROOT / "scripts" / "build-installer.ps1").read_text(encoding="utf-8")

        self.assertIn('Join-Path $Root "build\\release-temp"', executable_build)
        self.assertIn("$env:TEMP = $ReleaseTemp", executable_build)
        self.assertIn('Join-Path $Root "build\\pyinstaller-config"', executable_build)
        self.assertIn("$env:PYINSTALLER_CONFIG_DIR = $PyInstallerConfigPath", executable_build)
        self.assertIn("$env:PYINSTALLER_CONFIG_DIR = $PreviousPyInstallerConfig", executable_build)
        self.assertIn("$env:PATH = $IsolatedBuildPath", executable_build)
        self.assertIn("Frozen native dependency collision detected", executable_build)
        self.assertIn('Label "Final release disk requirements"', executable_build)
        self.assertIn('Label "Final release manifest generation"', executable_build)
        self.assertIn('Join-Path $Root "build\\installer-temp"', installer_build)
        self.assertIn("$env:TEMP = $InstallerTemp", installer_build)

    def test_environment_sync_handles_exact_hash_locked_packages_across_indexes(self):
        install_script = (ROOT / "scripts" / "install-desktop-env.ps1").read_text(encoding="utf-8")
        lock_script = (ROOT / "scripts" / "lock-dependencies.ps1").read_text(encoding="utf-8")
        engine_lock_script = (ROOT / "scripts" / "lock-engine-dependencies.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("pip sync --python $Python --strict $DependencyLock", install_script)
        self.assertNotIn("--index-strategy unsafe-first-match", install_script)
        self.assertNotIn("--index-strategy unsafe-best-match", install_script)
        self.assertIn("--index-strategy unsafe-best-match", engine_lock_script)
        self.assertIn("--write-manifest --no-installed-check", lock_script)

    def test_release_build_enforces_dependency_vulnerability_audit(self):
        build_script = (ROOT / "scripts" / "build-exe.ps1").read_text(encoding="utf-8")
        audit_script = (ROOT / "scripts" / "audit-dependencies.ps1").read_text(encoding="utf-8")
        test_script = (ROOT / "scripts" / "test.ps1").read_text(encoding="utf-8")
        smoke_script = (ROOT / "scripts" / "smoke-test-frozen.ps1").read_text(encoding="utf-8")

        self.assertIn('Join-Path $PSScriptRoot "test.ps1"', build_script)
        self.assertIn('Join-Path $PSScriptRoot "audit-dependencies.ps1"', build_script)
        self.assertNotIn("WhisperxMelFilters", build_script)
        self.assertNotIn('@("--collect-data", "whisperx")', build_script)
        self.assertNotIn('@("--collect-all", "demucs")', build_script)
        self.assertIn('"--profile", "core"', build_script)
        self.assertIn('"torch", "torchaudio", "torchvision"', build_script)
        self.assertIn('"psutil"', build_script)
        self.assertIn('"soundfile"', build_script)
        self.assertIn('"rich"', build_script)
        self.assertIn('"pygments"', build_script)
        self.assertIn('"Qt6WebEngine"', build_script)
        self.assertIn('"Qt6Quick3D"', build_script)
        self.assertIn("Refusing to prune an unsafe QML module path", build_script)
        self.assertNotIn('--add-data", "$ModelPath;models', build_script)
        self.assertNotIn("--demucs-model", build_script)
        self.assertNotIn("--alignment-models", build_script)
        self.assertIn("PreFinalize = $true", build_script)
        self.assertIn("$env:HAIZFLOW_HOME = $SmokeRoot", smoke_script)
        self.assertIn("$env:MODELS_DIR = $SmokeModels", smoke_script)
        self.assertIn("Wait-Process -Id $Process.Id -Timeout $TimeoutSeconds", smoke_script)
        self.assertIn("-RedirectStandardOutput $StandardOutput", smoke_script)
        self.assertIn("-RedirectStandardError $StandardError", smoke_script)
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
        self.assertIn("Dependency vulnerability audit found an unreviewed advisory in", audit_script)
        self.assertIn('"PYSEC-2026-3740"', audit_script)
        self.assertIn('"CVE-2026-9856"', audit_script)
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
        self.assertNotIn("save_pretrained(", worker)

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

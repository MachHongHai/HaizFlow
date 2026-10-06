import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.core.model_integrity import DEMUCS_MODEL_SIGNATURE, ModelIntegrityError
from haizflow.pipeline import audio_separation


class AudioSeparationTests(unittest.TestCase):
    def test_demucs_runtime_selection_obeys_cpu_gpu_setting(self):
        from haizflow.core.hardware import HardwareCapabilities, runtime_profile_for

        capabilities = HardwareCapabilities(
            cuda_available=True, cuda_name="RTX 4060", total_vram_bytes=8 * 1024**3,
            free_vram_bytes=7 * 1024**3,
            total_ram_bytes=16 * 1024**3, logical_cpu_count=8, ac_powered=True, battery_percent=100,
        )
        for preference in ("cpu", "gpu"):
            with self.subTest(preference=preference), mock.patch.object(
                audio_separation, "runtime_profile", return_value=runtime_profile_for(capabilities, preference)
            ), mock.patch("haizflow.services.resource_packs.installed_engine_command", return_value=["engine.exe", "--demucs-separate"]) as command:
                self.assertEqual(audio_separation._demucs_command(), ["engine.exe", "--demucs-separate"])
                self.assertEqual(command.call_args.args[2], {"device": preference})

    def test_publish_retries_transient_windows_directory_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / ".staging"
            target = Path(directory) / "separated"
            source.mkdir()
            (source / "audio.wav").write_bytes(b"audio")
            replace = audio_separation.os.replace
            attempts = []

            def locked_once(old, new):
                attempts.append((old, new))
                if len(attempts) == 1:
                    raise PermissionError("Windows sharing lock")
                return replace(old, new)

            with mock.patch.object(audio_separation.os, "replace", side_effect=locked_once), \
                 mock.patch.object(audio_separation.time, "sleep"), \
                 mock.patch.object(audio_separation, "check_cancellation"):
                audio_separation._replace_separation_directory(str(source), str(target), "fixture")
            self.assertEqual(len(attempts), 2)
            self.assertEqual((target / "audio.wav").read_bytes(), b"audio")

    def test_directory_publish_never_retries_unrelated_errors_or_moves_outside_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / ".staging"
            destination = Path(directory) / "separated"
            with mock.patch.object(audio_separation.os, "replace", side_effect=FileNotFoundError("missing")) as replace:
                with self.assertRaises(FileNotFoundError):
                    audio_separation._replace_separation_directory(str(source), str(destination))
                replace.assert_called_once()
            with mock.patch.object(audio_separation.os, "replace") as replace:
                with self.assertRaises(ValueError):
                    audio_separation._replace_separation_directory(str(source), str(Path(directory) / "other" / "separated"))
                replace.assert_not_called()

    def test_frozen_demucs_uses_internal_executable_mode(self):
        with mock.patch.object(audio_separation, "is_frozen", return_value=True):
            self.assertEqual(
                audio_separation._demucs_command(),
                [sys.executable, "--demucs-separate"],
            )

    def test_pipeline_never_downloads_a_missing_demucs_model(self):
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            mock.patch.object(audio_separation, "MODELS_DIR", temp_dir),
            mock.patch.object(
                audio_separation,
                "verify_demucs_model",
                side_effect=ModelIntegrityError("missing"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "missing or corrupted"):
                audio_separation._demucs_model_directory("video-1")

    def test_demucs_subprocess_is_forced_to_verified_local_repository(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "audio.wav"
            source.write_bytes(b"RIFF" + b"\0" * 64)
            output = root / "separated"
            repository = root / "models"
            repository.mkdir()
            captured_command = []
            captured_environment = {}

            def start_process(command, **kwargs):
                captured_command.extend(command)
                captured_environment.update(kwargs["env"])
                staging = Path(command[command.index("-o") + 1])
                track = staging / DEMUCS_MODEL_SIGNATURE / source.stem
                track.mkdir(parents=True)
                (track / "vocals.wav").write_bytes(b"RIFF" + b"voice" * 20)
                (track / "no_vocals.wav").write_bytes(b"RIFF" + b"music" * 20)
                return SimpleNamespace(returncode=0)

            with (
                mock.patch.object(audio_separation, "_demucs_model_directory", return_value=repository),
                mock.patch.object(
                    audio_separation,
                    "runtime_profile",
                    return_value=SimpleNamespace(
                        cuda_available=True,
                        key="gpu",
                        cpu_threads=8,
                    ),
                ),
                mock.patch.object(audio_separation.subprocess, "Popen", side_effect=start_process),
                mock.patch.object(audio_separation, "communicate_process", return_value=("", "")),
                mock.patch.object(audio_separation, "check_cancellation"),
                mock.patch.object(audio_separation, "log_to_video"),
            ):
                vocals, background = audio_separation.separate_audio(
                    str(source),
                    str(output),
                    "video-1",
                )

            self.assertEqual(captured_command[captured_command.index("-n") + 1], DEMUCS_MODEL_SIGNATURE)
            self.assertEqual(
                Path(captured_command[captured_command.index("--repo") + 1]),
                repository,
            )
            self.assertEqual(
                captured_environment["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"],
                "1",
            )
            self.assertTrue(Path(vocals).is_file())
            self.assertTrue(Path(background).is_file())
            self.assertEqual(captured_command[captured_command.index("--segment") + 1], "4")


if __name__ == "__main__":
    unittest.main()

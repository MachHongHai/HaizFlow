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


if __name__ == "__main__":
    unittest.main()

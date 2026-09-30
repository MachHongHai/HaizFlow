import tempfile
from pathlib import Path
from unittest import mock

import pytest

from haizflow.pipeline import omnivoice_tts, voice_reference
from haizflow.schemas.video import VideoConfig
from haizflow.services.resource_packs import ResourcePackManager
from haizflow.services.video_store import _migrate_video_metadata


@pytest.mark.parametrize("provider", ["omnivoice", "omnivoice-gpu"])
def test_explicit_local_provider_survives_config_and_metadata_migration(provider):
    voice = "omnivoice:female"
    config = VideoConfig(tts_provider=provider, tts_voice=voice)
    assert config.tts_provider == provider
    migrated, _changed = _migrate_video_metadata({"schema_version": 18, "tts_provider": provider, "tts_voice": voice})
    assert migrated["tts_provider"] == provider
    assert migrated["tts_voice"] == voice


def test_resource_requirements_follow_explicit_voice_device_not_global_setting():
    manager = ResourcePackManager()
    assert manager.required_packs("voice", {"provider": "omnivoice", "device": "gpu"}) == [
        "engine-cpu-py313",
        "model-omnivoice",
    ]
    assert manager.required_packs("voice", {"provider": "omnivoice-gpu", "device": "cpu"}) == [
        "engine-cuda128-py313",
        "model-omnivoice",
    ]


def test_blank_clone_transcript_is_prepared_before_omnivoice_runtime_loads():
    events = []
    with tempfile.TemporaryDirectory() as directory:
        with (
            mock.patch.object(
                voice_reference, "transcribe_reference", side_effect=lambda *a, **k: events.append("asr") or "My sample"
            ),
            mock.patch.object(omnivoice_tts, "_prepare_isolated_runtime", side_effect=lambda: events.append("tts")),
            mock.patch.object(omnivoice_tts, "verify_omnivoice_model", side_effect=RuntimeError("stop-after-prepare")),
            mock.patch.object(omnivoice_tts, "check_cancellation"),
            mock.patch.object(omnivoice_tts, "log_to_video"),
            pytest.raises(RuntimeError, match="stop-after-prepare"),
        ):
            omnivoice_tts.synthesize_batch_to_mp3(
                [
                    {
                        "text": "Hello",
                        "voice": "omnivoice:clone",
                        "reference_path": str(Path(directory) / "reference.wav"),
                        "reference_text": "",
                        "output_path": str(Path(directory) / "out.mp3"),
                    }
                ],
                "v",
                language_id="en",
            )
    assert events == ["asr", "tts"]


def test_omnivoice_workers_load_weights_sequentially_even_if_parent_enables_async():
    with mock.patch.dict("os.environ", {"HF_DEACTIVATE_ASYNC_LOAD": "0"}):
        assert omnivoice_tts._worker_environment()["HF_DEACTIVATE_ASYNC_LOAD"] == "1"


def test_busy_metadata_log_does_not_stop_the_worker_progress_monitor():
    with mock.patch.object(omnivoice_tts, "log_to_video", side_effect=TimeoutError("busy")):
        omnivoice_tts._log_monitor_event("v", "progress")

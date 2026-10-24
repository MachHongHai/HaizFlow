"""Translation story guidance must never leak across source replacements."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from haizflow.desktop.project_import_controller import ProjectImportController
from haizflow.desktop.project_workspace_controller import ProjectWorkspaceController
from haizflow.schemas.video import VideoConfig
from haizflow.services import project_store, video_store


@pytest.fixture
def configured_video(tmp_path, monkeypatch):
    monkeypatch.setattr(project_store, "PROJECT_INDEX_PATH", str(tmp_path / "projects.json"))
    monkeypatch.setattr(video_store, "LEGACY_VIDEO_WORKSPACES_DIR", str(tmp_path / "legacy"))

    def create(project_type="manual", suffix="old"):
        video = video_store.create_video("guidance-" + suffix + "-" + tmp_path.name, suffix + ".mp4",
            VideoConfig(project_type=project_type, project_directory=str(tmp_path),
                speech_recognition_model="small-cpu", translation_model="gemini-3.5-flash-lite",
                tts_provider="vieneu", target_language="vi", gemini_translation_style="literal",
                gemini_translation_instructions="Bối cảnh: vợ bỏ chồng, chồng nhập viện.",
                gemini_translation_glossary="Vợ chồng xưng anh–em, người khác xưng tôi."))
        Path(video.files["video_input"]).write_bytes(b"OLD INPUT")
        return video

    return create


@pytest.mark.parametrize("project_type", ["manual", "single", "batch"])
@pytest.mark.parametrize("remote", [False, True])
def test_replacement_clears_story_rules_on_disk_and_in_selected_ui(configured_video, tmp_path,
                                                                 project_type, remote):
    video = configured_video(project_type)
    other = configured_video(project_type, "other")
    source = tmp_path / "new.mp4"
    source.write_bytes(b"NEW INPUT")
    media_source = {"type": "video_url", "platform": "douyin", "source_url": "https://example.invalid/new"} if remote else None
    replaced = video_store.replace_video_input(video.video_id, str(source), media_source=media_source)
    video_store._VIDEO_METADATA_CACHE.pop(video.video_id, None)
    reloaded = video_store.get_video(video.video_id)
    assert reloaded.gemini_translation_instructions == reloaded.gemini_translation_glossary == ""
    assert reloaded.gemini_translation_style == "literal"
    assert reloaded.translation_model == video.translation_model
    assert reloaded.target_language == video.target_language
    assert reloaded.tts_provider == video.tts_provider
    assert reloaded.checkpoints == reloaded.processing_configuration == {}
    assert video_store.get_video(other.video_id).gemini_translation_instructions == other.gemini_translation_instructions

    host = Mock(_selected_video_id=video.video_id, _project_directory=str(tmp_path),
        _settings_processing_device="cpu", _startup_hardware_resolved=False,
        _hardware_capabilities=SimpleNamespace(total_vram_bytes=0),
        _processing_queue=SimpleNamespace(active_video_id=None, contains=lambda _: False),
        _manual_settings_drafts={video.video_id: video.model_copy(deep=True), other.video_id: other},
        _manual_cache_indexed={video.video_id}, _editor_transform_drafts={},
        _gemini_translation_instructions=video.gemini_translation_instructions,
        _gemini_translation_glossary=video.gemini_translation_glossary,
        _normalized_tts_provider=lambda _language, provider: provider,
        _normalized_voice_for_language=lambda _language, voice, _provider: voice,
        _video_project_key=lambda selected: selected.project_key,
        _resolve_video_file=lambda selected, *_: selected.files["video_input"])
    host._select_video = lambda selected: ProjectWorkspaceController(host).select_video(selected)
    assert ProjectImportController(host)._reset_replaced_source_view(replaced)
    assert host._gemini_translation_instructions == host._gemini_translation_glossary == ""
    assert host._gemini_translation_style == "literal"
    host.geminiGuidanceChanged.emit.assert_called_once()
    assert video.video_id not in host._manual_settings_drafts
    assert host._manual_settings_drafts[other.video_id] is other


def test_failed_replacement_restores_guidance_with_original_source(configured_video, tmp_path, monkeypatch):
    video = configured_video()
    source = tmp_path / "new.mp4"
    source.write_bytes(b"NEW INPUT")
    save = video_store._save_video_unlocked

    def fail_new_source(candidate):
        if candidate.original_filename == "new.mp4":
            assert candidate.gemini_translation_instructions == candidate.gemini_translation_glossary == ""
            raise OSError("simulated metadata write failure")
        return save(candidate)

    monkeypatch.setattr(video_store, "_save_video_unlocked", fail_new_source)
    with pytest.raises(OSError, match="simulated"):
        video_store.replace_video_input(video.video_id, str(source))
    restored = video_store.get_video(video.video_id)
    assert Path(restored.files["video_input"]).read_bytes() == b"OLD INPUT"
    assert restored.gemini_translation_instructions == video.gemini_translation_instructions
    assert restored.gemini_translation_glossary == video.gemini_translation_glossary


@pytest.mark.parametrize("operation", ["same_input", "restart"])
def test_same_source_operations_preserve_guidance(configured_video, operation):
    video = configured_video()
    if operation == "same_input":
        result = video_store.replace_video_input(video.video_id, video.files["video_input"])
    else:
        result = video_store.prepare_video_restart(video.video_id)
    assert result.gemini_translation_instructions == video.gemini_translation_instructions
    assert result.gemini_translation_glossary == video.gemini_translation_glossary
    assert result.gemini_translation_style == "literal"

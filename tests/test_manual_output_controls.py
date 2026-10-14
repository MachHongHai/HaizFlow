from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from hflow.desktop.presenters import voice_options_for_language
from hflow.desktop.project_workspace_controller import ProjectWorkspaceController
from hflow.desktop.qml_controller import HFlowController
from hflow.pipeline import manual_tools, tts
from hflow.schemas.video import VideoConfig, VideoInfo
from hflow.services.subtitle_language import manual_subtitle_language


def video_for(**changes):
    values = VideoConfig(project_type="manual").model_dump()
    values.update(video_id="manual-test", original_filename="clip.mp4", status="manual_ready",
                  created_at="2026-10-13T00:00:00Z", updated_at="2026-10-13T00:00:00Z")
    values.update(changes)
    return VideoInfo.model_validate(values)


@pytest.mark.parametrize("published", ["vi", "en", "zh"])
@pytest.mark.parametrize("next_language", ["vi", "zh"])
def test_published_language_is_independent_of_next_translation(published, next_language):
    video = video_for(target_language=next_language, subtitle_language=published)
    assert manual_subtitle_language(video) == published
    if published != "zh":
        assert tts.resolve_tts_provider("vieneu-gpu", published) == "vieneu"


@pytest.mark.parametrize("text,language", [
    ("你好，这个多少钱", "zh"), ("Hello, how much is this?", "en"),
    ("Xin chào, cái này giá bao nhiêu?", "vi"),
])
def test_legacy_chinese_target_checks_real_text(text, language):
    assert manual_subtitle_language(video_for(target_language="zh"), [{"text": text}]) == language


@pytest.mark.parametrize("provider", ["vieneu", "vieneu-gpu"])
def test_manual_translation_choice_keeps_vieneu_until_chinese_is_published(provider):
    video = video_for(subtitle_language="vi", tts_provider=provider, tts_voice="vieneu:Hải Đăng")
    host = SimpleNamespace(_project_type="manual", _selected_video=lambda: video,
        _target_language="vi", _tts_provider=provider, _tts_voice=video.tts_voice,
        _audio_preview=Mock(), appAlertRequested=Mock(), targetLanguageChanged=Mock(),
        languageOptionsChanged=Mock(), ttsVoiceChanged=Mock(), ttsProviderChanged=Mock(),
        ttsProviderOptionsChanged=Mock(), ttsVoiceOptionsChanged=Mock(),
        _voice_options_for_language=lambda language, backend: voice_options_for_language(language, "vi", backend))
    host._normalized_voice_for_language = HFlowController._normalized_voice_for_language.__get__(host)
    HFlowController.targetLanguage.fset(host, "zh")
    assert host._target_language == "zh" and host._tts_provider == provider
    assert host._tts_voice == "vieneu:Hải Đăng"
    host.appAlertRequested.emit.assert_not_called()


@pytest.mark.parametrize("project_type", ["manual", "single"])
def test_every_invalid_vieneu_provider_attempt_warns_and_keeps_previous_choice(project_type):
    video = video_for(target_language="vi", subtitle_language="zh")
    host = SimpleNamespace(_project_type=project_type, _selected_video=lambda: video,
        _target_language="zh" if project_type == "single" else "vi", _tts_provider="omnivoice",
        _normalized_tts_provider=HFlowController._normalized_tts_provider, appAlertRequested=Mock())
    for _ in range(3):
        HFlowController.ttsProvider.fset(host, "vieneu")
    assert host._tts_provider == "omnivoice"
    assert host.appAlertRequested.emit.call_count == 3


@pytest.mark.parametrize("provider,fallback", [("vieneu", "omnivoice"), ("vieneu-gpu", "omnivoice-gpu")])
def test_chinese_translation_falls_back_only_after_successful_publication(provider, fallback):
    video = video_for(target_language="zh", subtitle_language="vi", tts_provider=provider,
        files={"voice_output": "old.wav", "manual_voice_overrides": {
            "old": {"provider": provider}, "edge": {"provider": "edge"}}})
    with (patch.object(manual_tools.video_store, "get_video", return_value=video),
          patch.object(manual_tools, "_publish_subtitles", return_value={"artifact_id": "new"}),
          patch.object(manual_tools.manual_artifacts, "deactivate"),
          patch.object(manual_tools.video_store, "log_to_video"),
          patch.object(manual_tools.video_store, "update_video") as update):
        manual_tools._replace_subtitles_from_translation(video.video_id, "translated.json")
    values = update.call_args.kwargs
    assert values["subtitle_language"] == "zh" and values["tts_provider"] == fallback
    assert "voice_output" not in values["files"]
    assert values["files"]["manual_voice_overrides"] == {"edge": {"provider": "edge"}}


@pytest.mark.parametrize("provider,fallback", [("vieneu", "omnivoice"), ("vieneu-gpu", "omnivoice-gpu")])
@pytest.mark.parametrize("stored", ["zh", ""])
def test_existing_chinese_import_dialog_projects_compatible_voice_without_mutation(provider, fallback, stored):
    video = video_for(tts_provider=provider, tts_voice="vieneu:Hải Đăng", subtitle_language=stored,
                      target_language="vi", files={"imported_source_srt": {"name": "legacy.srt"}})
    original = video.model_dump()
    host = SimpleNamespace(_project_type="manual", _selected_video=lambda: video,
                           _manual_subtitles=SimpleNamespace(video_id=video.video_id, segments=[{"text": "你好世界"}]))
    with patch.object(manual_tools, "published_voice_record", return_value=None):
        configuration = HFlowController.manualVoiceConfiguration(host, "")
    assert configuration["globalProvider"] == fallback and configuration["provider"] == fallback
    assert configuration["globalVoice"] == "omnivoice:female_gentle"
    assert video.model_dump() == original


def test_chinese_dialog_keeps_edge_but_repairs_unsupported_segment_override():
    video = video_for(tts_provider="edge", tts_voice="zh-CN-XiaoxiaoNeural", subtitle_language="zh",
                     files={"manual_voice_overrides": {"cue": {"provider": "vieneu-gpu", "voice": "vieneu:Hải Đăng"}}})
    host = SimpleNamespace(_project_type="manual", _selected_video=lambda: video)
    with patch.object(manual_tools, "published_voice_record", return_value=None):
        configuration = HFlowController.manualVoiceConfiguration(host, "cue")
    assert configuration["globalProvider"] == "edge" and configuration["globalVoice"] == "zh-CN-XiaoxiaoNeural"
    assert configuration["provider"] == "omnivoice-gpu"


def test_confirming_full_manual_voice_requests_fresh_generation():
    video = video_for(tts_provider="vieneu-gpu", tts_voice="vieneu:Hải Đăng", subtitle_language="vi")
    host = SimpleNamespace(_project_type="manual", _selected_video=lambda: video,
        _processing_queue=SimpleNamespace(contains=lambda _: False),
        _normalized_tts_provider=HFlowController._normalized_tts_provider,
        _normalized_voice_for_language=lambda _lang, value, _provider: value,
        _manual_subtitles=SimpleNamespace(video_id=video.video_id, segments=[{"segment_id": "cue", "text": "Xin chào"}]),
        voiceCloneReferencePath="", appAlertRequested=Mock(), ttsProviderChanged=Mock(), ttsVoiceChanged=Mock(),
        ttsProviderOptionsChanged=Mock(), ttsVoiceOptionsChanged=Mock(), _apply_setup_to_video=Mock(),
        speakerModeChanged=Mock(), _manual_voice_configuration_snapshot=HFlowController._manual_voice_configuration_snapshot,
        _record_manual_voice_configuration_change=Mock(), runManualTool=Mock(return_value=True))
    with (patch("hflow.desktop.qml_controller.video_store.update_video"),
          patch("hflow.desktop.qml_controller.video_store.log_to_video")):
        assert HFlowController.configureAndRunManualVoice(host, "vieneu-gpu", "vieneu:Hải Đăng", "all", "", "multiple")
    host.runManualTool.assert_called_once_with("voice", True)


def test_manual_speed_save_does_not_touch_preview_or_other_drafts():
    video = video_for(output_speed=1, active_artifacts={"export": "old-export", "ocr_region": "ocr", "tts_manifest": "voice"})
    current = [video]
    def update(_id, **values):
        current[0] = current[0].model_copy(update=values)
        return current[0]
    def deactivate(_id, kinds):
        assert kinds == {"export"}
        current[0] = current[0].model_copy(update={"active_artifacts": {"ocr_region": "ocr", "tts_manifest": "voice"}})
    host = SimpleNamespace(_selected_video_id=video.video_id, _settings_owner_video_id=video.video_id,
        _processing_queue=SimpleNamespace(contains=lambda _: False), videoExportBusy=False,
        _record_video_settings_change=Mock(), _manual_settings_drafts={video.video_id: VideoConfig(watermark_text="Pending")},
        outputSpeed=1, selectedVideoChanged=Mock(), refreshVideos=Mock(), refreshManualPreviewAudio=Mock())
    with (patch("hflow.desktop.qml_controller.video_store.get_video", side_effect=lambda _: current[0]),
          patch("hflow.desktop.qml_controller.video_store.update_video", side_effect=update),
          patch("hflow.desktop.qml_controller.manual_artifacts.deactivate", side_effect=deactivate)):
        assert HFlowController.setManualOutputSpeed(host, 1.5)
    assert current[0].output_speed == 1.5 and current[0].active_artifacts == {"ocr_region": "ocr", "tts_manifest": "voice"}
    assert host._manual_settings_drafts[video.video_id].watermark_text == "Pending"
    assert host._manual_settings_drafts[video.video_id].output_speed == 1.5
    assert host._selected_video_snapshot.output_speed == 1.5
    host.selectedVideoChanged.emit.assert_not_called()
    host.refreshVideos.assert_not_called()
    host.refreshManualPreviewAudio.assert_not_called()


@pytest.mark.parametrize("speed_only", [True, False])
def test_metadata_poll_does_not_reload_preview_for_output_speed_only(speed_only):
    previous = video_for(output_speed=1, project_key="p")
    current = previous.model_copy(update={"output_speed": 1.5, **({} if speed_only else {"tts_voice": "other"})})
    host = SimpleNamespace(_selected_video_id=previous.video_id, _catalog_videos={previous.video_id: previous},
        _video_project_key=lambda _: "p", _project_summaries_by_key={"p": {"project_type": "manual"}},
        _build_project_summaries=lambda *_: [{"project_type": "manual"}], videos=Mock(), batch_videos=Mock(),
        projects=Mock(), manual_projects=Mock(), single_projects=Mock(), batch_projects=Mock(),
        download_projects=Mock(), publish_projects=Mock(), selectedVideoChanged=Mock())
    with patch("hflow.desktop.project_workspace_controller.video_store.get_video", return_value=current):
        assert ProjectWorkspaceController(host).apply_video_metadata_changes({previous.video_id})
    assert host.selectedVideoChanged.emit.call_count == (0 if speed_only else 1)


def test_speed_toolbar_never_requests_preview_and_srt_action_is_guarded():
    qml = Path(__file__).parents[1] / "src/hflow/desktop/qml"
    workspace = (qml / "ManualWorkspace.qml").read_text(encoding="utf-8")
    handler = workspace.split("onOutputSpeedEdited: function(value) {", 1)[1].split("}", 1)[0]
    assert "setManualOutputSpeed" in handler and "saveNow" not in handler and "schedulePreview" not in handler
    assert "enabled: !AppController.isProcessing" in workspace
    assert "enabled: modelData.enabled !== false" in (qml / "ManualToolNavigator.qml").read_text(encoding="utf-8")

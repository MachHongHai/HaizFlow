"""Scoped requests validate IDs before editing any project configuration."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.services import video_store
from haizflow.services.manual_voice_scope import selected_ids


@pytest.fixture
def setup_scope(monkeypatch):
    rows = [{"segment_id": name, "text": "Xin chào"} for name in ("a", "b", "c")]
    video = SimpleNamespace(video_id="scope", project_type="manual", target_language="vi",
        tts_provider="edge", tts_voice="vi-VN-NamMinhNeural", speaker_mode="single",
        files={"manual_voice_overrides": {"b": {"provider": "edge", "voice": "vi-VN-HoaiMyNeural"}}})
    def update(_key, **values):
        video.__dict__.update(values)
        return video
    monkeypatch.setattr(video_store, "get_video", lambda _: video)
    monkeypatch.setattr(video_store, "update_video", update)
    monkeypatch.setattr(video_store, "log_to_video", Mock())
    host = SimpleNamespace(_project_type="manual", _selected_video=lambda: video,
        _processing_queue=SimpleNamespace(contains=lambda _: False),
        _manual_subtitles=SimpleNamespace(video_id=video.video_id, segments=rows),
        _normalized_tts_provider=lambda language, provider: provider,
        _normalized_voice_for_language=lambda language, voice, provider: voice,
        voiceCloneReferencePath="", appAlertRequested=Mock(),
        _manual_voice_configuration_snapshot=HaizFlowController._manual_voice_configuration_snapshot,
        _record_manual_voice_configuration_change=Mock(), runManualTool=Mock(return_value=True))
    return host, video, rows


def test_selection_keeps_globals_and_unselected_override(setup_scope):
    host, video, _ = setup_scope
    old = deepcopy(video.files["manual_voice_overrides"]["b"])
    assert HaizFlowController.configureAndRunManualVoice(
        host, "vieneu-gpu", "vieneu:Trúc Ly", "selection", "", "single", ["c", "a"])
    assert video.files["manual_voice_selection"] == ["a", "c"]
    assert video.files["manual_voice_overrides"]["b"] == old
    assert video.tts_provider == "edge" and video.tts_voice == "vi-VN-NamMinhNeural"
    assert video.speaker_mode == "single"
    first = video.files["manual_voice_overrides"]["a"]["generation"]
    assert HaizFlowController.configureAndRunManualVoice(
        host, "vieneu-gpu", "vieneu:Trúc Ly", "selection", "", "single", ["a"])
    assert video.files["manual_voice_overrides"]["a"]["generation"] != first


@pytest.mark.parametrize("ids", [None, [], ["missing"], ["a", "a"], ["a", 1], "a"])
def test_invalid_selection_has_no_side_effects(setup_scope, ids):
    host, video, rows = setup_scope
    original = deepcopy(video.files)
    assert not HaizFlowController.configureAndRunManualVoice(
        host, "vieneu-gpu", "vieneu:Trúc Ly", "selection", "", "single", ids)
    assert video.files == original
    host.runManualTool.assert_not_called()
    with pytest.raises(ValueError):
        selected_ids({"manual_voice_selection": ids}, rows)


def test_unsaved_subtitles_cannot_be_generated(setup_scope):
    host, video, _ = setup_scope
    host._manual_subtitles._states = {"a": "saving"}
    original = deepcopy(video.files)
    assert not HaizFlowController.configureAndRunManualVoice(
        host, "edge", "vi-VN-HoaiMyNeural", "segment", "a", "single")
    assert video.files == original
    host.runManualTool.assert_not_called()


def test_vieneu_checks_only_selected_text_but_still_blocks_han_in_that_scope(setup_scope):
    host, video, rows = setup_scope
    rows[1]["text"] = "你好"
    assert HaizFlowController.configureAndRunManualVoice(
        host, "vieneu-gpu", "vieneu:Trúc Ly", "selection", "", "single", ["a", "c"])
    original = deepcopy(video.files)
    host.runManualTool.reset_mock()
    assert not HaizFlowController.configureAndRunManualVoice(
        host, "vieneu-gpu", "vieneu:Trúc Ly", "segment", "b", "single")
    assert video.files == original
    host.runManualTool.assert_not_called()


def test_qml_bridge_exposes_scoped_voice_overload():
    assert HaizFlowController.staticMetaObject.indexOfMethod(
        "configureAndRunManualVoice(QString,QString,QString,QString,QString,QVariantList)") >= 0


def test_scoped_edge_voice_cannot_inherit_multiple_speaker_mode(setup_scope):
    host, video, _ = setup_scope
    video.speaker_mode = "multiple"
    assert HaizFlowController.configureAndRunManualVoice(
        host, "edge", "vi-VN-HoaiMyNeural", "segment", "a", "multiple")
    assert video.files["manual_voice_overrides"]["a"]["speaker_mode"] == "single"
    assert video.speaker_mode == "multiple"

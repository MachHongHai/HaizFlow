from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from hflow.desktop.qml_controller import HFlowController
from hflow.desktop.subtitle_voice_edit_notice import SubtitleVoiceEditNotice


def test_warning_waits_for_success_and_only_once_per_project_session():
    alert = Mock()
    notice = SubtitleVoiceEditNotice(alert)
    notice.prepare("project-a", "video-a", "sentence-1", "save-1")
    alert.assert_not_called()
    notice.saved("video-a", "sentence-1", "save-1")
    alert.assert_called_once()
    assert alert.call_args.args[2] == "warning"
    assert "các câu khác" in alert.call_args.args[1]
    # More sentences, reopen the project, change video/source, same session.
    notice.prepare("project-a", "video-a", "sentence-2", "save-2")
    notice.saved("video-a", "sentence-2", "save-2")
    notice.prepare("project-a", "new-source", "sentence-1", "save-3")
    notice.saved("new-source", "sentence-1", "save-3")
    assert alert.call_count == 1
    notice.prepare("project-b", "video-b", "sentence-1", "save-1")
    notice.saved("video-b", "sentence-1", "save-1")
    assert alert.call_count == 2
    # New app instance: nothing was persisted to settings or project files.
    restarted = SubtitleVoiceEditNotice(alert)
    restarted.prepare("project-a", "video-a", "sentence-1", "save-1")
    restarted.saved("video-a", "sentence-1", "save-1")
    assert alert.call_count == 3


def test_failure_does_not_spend_notice_and_foreign_reply_cannot_trigger_it():
    alert = Mock()
    notice = SubtitleVoiceEditNotice(alert)
    notice.prepare("project", "video", "sentence", "save-1")
    notice.failed("video", "sentence", "save-1")
    notice.saved("video", "sentence", "save-1")
    alert.assert_not_called()
    notice.prepare("project", "video", "sentence", "save-2")
    notice.saved("other-video", "sentence", "save-2")
    alert.assert_not_called()
    notice.saved("video", "sentence", "save-2")
    alert.assert_called_once()


@pytest.mark.parametrize("had_voice,changed,accepted", [
    (False, True, True), (True, False, True), (True, True, False), (True, True, True),
])
def test_controller_prepares_notice_only_for_changed_voiced_subtitle(had_voice, changed, accepted):
    alert = Mock()
    video = SimpleNamespace(video_id="video", project_key="project")
    host = SimpleNamespace(
        _selected_video_id="video", _selected_project_key="project",
        _manual_voice_refresh_enabled=False, _manual_voice_refresh_pending=False,
        _subtitle_voice_edit_notice=SubtitleVoiceEditNotice(alert),
        _manual_subtitles=SimpleNamespace(
            video_id="video", segments=[{"segment_id": "sentence", "text": "Original"}],
            saveText=Mock(return_value=accepted),
        ),
    )
    with patch("hflow.desktop.qml_controller.video_store.get_video", return_value=video), \
            patch("hflow.pipeline.manual_tools.published_voice_record", return_value={} if not had_voice else {"id": "voice"}), \
            patch("hflow.pipeline.manual_tools.ensure_narrator_anchor"):
        result = HFlowController.saveManualSubtitleText(
            host, "sentence", "Changed" if changed else "Original", 0, "save",
        )
    assert result is accepted
    alert.assert_not_called()  # Accepted is not the same as durable success.
    HFlowController._subtitle_voice_edit_saved(host, "sentence", 1, "save")
    assert alert.call_count == int(had_voice and changed and accepted)

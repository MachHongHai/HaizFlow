from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from haizflow.desktop.processing_lifecycle_controller import ProcessingLifecycleController
from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.desktop.project_commands_controller import ProjectCommandsController
from haizflow.schemas.video import VideoConfig
from haizflow.services.processing_resume import can_resume, configuration_snapshot


def fixture():
    video = SimpleNamespace(**VideoConfig(project_type="manual").model_dump(), video_id="fixture",
                            status="paused", manual_target_tool="translation", files={})
    video.processing_configuration = configuration_snapshot(video, "cpu")
    host = SimpleNamespace(_selected_video_id="fixture", _settings_language="vi",
                           _settings_processing_device="cpu", appAlertRequested=Mock())
    return host, video


@pytest.mark.parametrize("field,value", [("translation_model", "q4"), ("target_language", "en"),
                                        ("speech_recognition_model", "small-gpu"), ("enable_audio_separation", False)])
def test_changed_processing_setting_blocks_resume(field, value):
    host, video = fixture()
    setattr(video, field, value)
    assert not can_resume(host, video)
    assert host.appAlertRequested.emit.call_args.args[2] == "warning"


def test_device_change_and_unsaved_draft_block_resume_but_restoring_settings_allows_it():
    host, video = fixture()
    assert can_resume(host, video)
    host._settings_processing_device = "gpu"
    assert not can_resume(host, video)
    host._settings_processing_device = "cpu"
    host._build_config = lambda: VideoConfig(project_type="manual", target_language="en")
    assert not can_resume(host, video)
    host._build_config = lambda: VideoConfig(project_type="manual")
    assert can_resume(host, video)


def test_identity_and_unrelated_manual_settings_do_not_block_translation():
    host, video = fixture()
    video.project_name = "Renamed"
    video.watermark_text = "Another watermark"
    video.tts_voice = "omnivoice:male"
    assert can_resume(host, video)


def test_legacy_pause_without_snapshot_is_not_silently_resumed():
    host, video = fixture()
    video.processing_configuration = {}
    assert not can_resume(host, video)
    assert "Tác vụ cũ" in host.appAlertRequested.emit.call_args.args[1]


def test_direct_enqueue_cannot_bypass_resume_guard():
    host, video = fixture()
    video.target_language = "en"
    host._processing_queue = SimpleNamespace(contains=lambda _: False, enqueue=Mock())
    with patch("haizflow.desktop.processing_lifecycle_controller.video_store.get_video", return_value=video):
        assert not ProcessingLifecycleController(host).enqueue_video("fixture")
    host._processing_queue.enqueue.assert_not_called()


def test_batch_resume_is_atomic_when_one_videos_settings_changed():
    host, video = fixture()
    video.target_language = "en"
    other = SimpleNamespace(video_id="new", status="pending")
    host._batch_video_ids = [video.video_id, other.video_id]
    host._processing_queue = SimpleNamespace(contains=lambda _: False)
    host._enqueue_videos = Mock()
    with patch("haizflow.desktop.project_commands_controller.video_store.get_video", side_effect=lambda key: video if key == video.video_id else other):
        ProjectCommandsController(host).resume_batch()
    host._enqueue_videos.assert_not_called()


def test_input_changes_block_resume(tmp_path):
    host, video = fixture()
    source = tmp_path / "video.mp4"
    source.write_bytes(b"initial input")
    video.files["video_input"] = str(source)
    video.processing_configuration = configuration_snapshot(video, "cpu")
    source.write_bytes(b"a different source")
    assert not can_resume(host, video)


def test_manual_restart_confirmation_cannot_discard_progress_on_rejection():
    host, video = fixture()
    host._selected_video = lambda: video
    host._processing_queue = SimpleNamespace(contains=lambda _: False)
    host.runManualTool = Mock(return_value=True)
    from haizflow.desktop.localization import QMessageBox

    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
        assert not HaizFlowController.restartManualTool(host, "translation")
    host.runManualTool.assert_not_called()
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        assert HaizFlowController.restartManualTool(host, "translation")
    host.runManualTool.assert_called_once_with("translation")


def test_explicit_restart_invalidates_an_unfinished_branch_without_deleting_outputs():
    from haizflow.pipeline import manual_tools

    _, video = fixture()
    video.manual_tool_generations = {"voice": 2}
    video.active_artifacts = {"subtitle_document": "kept"}
    with (
        patch.object(manual_tools.video_store, "get_video", return_value=video),
        patch.object(manual_tools.video_store, "update_video") as update,
        patch.object(manual_tools.video_store, "log_to_video"),
        patch.object(manual_tools, "_requested_artifact", side_effect=AssertionError("No final artifact required")),
    ):
        assert manual_tools.prepare_manual_rerun("fixture", "voice", force=True)
    assert update.call_args.kwargs == {"manual_tool_generations": {"voice": 3}}
    assert video.active_artifacts == {"subtitle_document": "kept"}

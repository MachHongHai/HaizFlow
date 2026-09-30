"""Stopped tools release the editor lock without deleting completed cache."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.pipeline import manual_tools, process_registry
from haizflow.schemas.video import VideoConfig


def video_snapshot(status="paused"):
    return SimpleNamespace(**VideoConfig(project_type="manual").model_dump(),
                           video_id="paused-manual", status=status, progress=45,
                           step_detail="Đã tạm dừng", manual_target_tool="voice",
                           active_artifacts={"subtitle_document": "kept-subtitles"}, files={})


@pytest.mark.parametrize("status,other_available", [("paused", True), ("processing", False), ("pending", False)])
def test_only_a_live_job_blocks_other_tools(status, other_available):
    video = video_snapshot(status)
    with (
        patch.object(manual_tools, "_separation_ready", return_value=True),
        patch.object(manual_tools, "_translation_ready", return_value=True),
        patch.object(manual_tools, "_subtitle_ready", return_value=True),
        patch.object(manual_tools, "_image_ready", return_value=False),
        patch.object(manual_tools, "_voice_ready", return_value=False),
        patch.object(manual_tools, "_audio_ready", return_value=False),
        patch.object(manual_tools, "_artifact_ready", return_value=False),
        patch.object(manual_tools, "published_voice_record", return_value=None),
        patch.object(manual_tools, "export_signature", return_value="export"),
    ):
        rows = {row["toolId"]: row for row in manual_tools.tool_states(video)}
    for tool in ("source", "translation", "subtitle", "image", "audio", "export"):
        assert rows[tool]["canRun"] is other_available
    assert rows["voice"]["state"] == {"paused": "paused", "processing": "running", "pending": "queued"}[status]
    assert rows["voice"]["progress"] == 45
    assert video.active_artifacts == {"subtitle_document": "kept-subtitles"}


def test_starting_another_tool_clears_pause_flags_and_resume_target_without_erasing_cache():
    video = video_snapshot()
    host = SimpleNamespace(
        _project_type="manual", _settings_language="vi", _selected_video=lambda: video,
        _processing_queue=SimpleNamespace(contains=lambda _: False),
        appAlertRequested=Mock(), _apply_setup_to_video=Mock(), _enqueue_video=Mock(return_value=True),
        manualToolStateChanged=Mock(), selectedVideoChanged=Mock(), refreshVideos=Mock(),
    )
    process_registry.pause_video(video.video_id)
    try:
        with (
            patch.object(manual_tools, "tool_states", return_value=[{"toolId": "source", "canRun": True}]),
            patch.object(manual_tools, "prepare_manual_rerun") as rerun,
            patch("haizflow.desktop.qml_controller.video_store.update_video") as update,
            patch("haizflow.desktop.qml_controller.video_store.log_to_video"),
        ):
            assert HaizFlowController.runManualTool(host, "source")
        assert not process_registry.is_paused(video.video_id)
        assert not process_registry.is_cancelled(video.video_id)
        assert update.call_args.kwargs["manual_target_tool"] == "source"
        assert update.call_args.kwargs["resume_step"] == ""
        assert "active_artifacts" not in update.call_args.kwargs
        assert video.active_artifacts == {"subtitle_document": "kept-subtitles"}
        rerun.assert_called_once_with(video.video_id, "source")
    finally:
        process_registry.prepare_video_resume(video.video_id)


def test_a_pause_request_does_not_allow_switching_before_the_worker_leaves_queue():
    video = video_snapshot()
    host = SimpleNamespace(
        _project_type="manual", _selected_video=lambda: video,
        _processing_queue=SimpleNamespace(contains=lambda _: True), appAlertRequested=Mock(),
        _enqueue_video=Mock(),
    )
    assert not HaizFlowController.runManualTool(host, "source")
    host._enqueue_video.assert_not_called()

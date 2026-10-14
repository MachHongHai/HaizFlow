"""Deterministic batch tests; no real AI model inference or user projects."""

import copy
import queue
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from hflow.desktop.processing_lifecycle_controller import ProcessingLifecycleController
from hflow.desktop.project_commands_controller import ProjectCommandsController, _batch_values_for_device
from hflow.desktop.qml_controller import HFlowController
from hflow.schemas.video import VideoConfig
from hflow.services import batch_feedback, batch_settings
from hflow.services.processing_queue import SerialProcessingQueue


def video(identifier="one", **kwargs):
    config = VideoConfig()
    fields = {field: getattr(config, field) for field in batch_settings.FIELDS.values()}
    return SimpleNamespace(**{**fields, "subtitle_style": config.subtitle_style,
                              "subtitle_layout_override": False, "files": {}, "video_id": identifier,
                              "original_filename": identifier + ".mp4", "status": "pending", "error": None,
                              "step": "recognition", "progress": 0, "video_width": 1080,
                              "video_height": 1920, **kwargs})


@pytest.mark.parametrize("key", [*batch_settings.FIELDS, "subtitleStyle", *batch_settings.ASSETS])
def test_every_batch_setting_has_visible_individual_override(key):
    current = video()
    baseline = batch_settings.values_for(current)
    baseline[key] = {"different": True} if key == "subtitleStyle" else "different"
    commands = ProjectCommandsController(SimpleNamespace(
        _selected_project_key="batch", _batch_video_ids=[current.video_id],
        _settings_processing_device="cpu"))
    actual = _batch_values_for_device(batch_settings.values_for(current), "cpu")
    for model in ("speechRecognitionModel", "translationModel", "ttsProvider"):
        if model != key:
            baseline[model] = actual[model]
    with patch.object(commands, "batch_settings_values", return_value=baseline), \
            patch("hflow.desktop.project_commands_controller.video_store.get_video", return_value=current):
        overrides = commands.batch_setting_overrides()
    assert overrides == [{"videoId": "one", "fileName": "one.mp4", "differences": [key]}]


@pytest.mark.parametrize("gib", [4, 8, 16])
def test_legacy_model_choices_do_not_create_false_overrides(gib):
    current = video(speech_recognition_model="small", translation_model="auto")
    capabilities = SimpleNamespace(total_vram_bytes=gib * 1024**3)
    commands = ProjectCommandsController(SimpleNamespace(
        _selected_project_key="batch", _batch_video_ids=[current.video_id],
        _settings_processing_device="gpu", _hardware_capabilities=capabilities))
    expected = _batch_values_for_device(batch_settings.values_for(current), "gpu",
                                        total_vram_bytes=capabilities.total_vram_bytes)
    with patch.object(commands, "batch_settings_values", return_value=expected), \
            patch("hflow.desktop.project_commands_controller.video_store.get_video", return_value=current):
        assert commands.batch_setting_overrides() == []


def test_preview_sources_keep_import_order_dimensions_and_never_select_or_edit(tmp_path):
    source = tmp_path / "input.mp4"
    source.write_bytes(b"source")
    first = video("first", files={"video_input": str(source)}, video_width=1920, video_height=1080)
    second = video("second", files={"video_input": str(source)})
    missing = video("missing", files={"video_input": str(tmp_path / "missing.mp4")})
    videos = {item.video_id: item for item in [first, second, missing]}
    host = SimpleNamespace(_batch_video_ids=list(videos), _selected_video_id="second", selectVideo=Mock())
    saved = copy.deepcopy(videos)
    with patch("hflow.desktop.project_commands_controller.video_store.get_video", side_effect=videos.get):
        sources = ProjectCommandsController(host).batch_preview_sources()
    assert [item["videoId"] for item in sources] == ["first", "second"]
    assert [(item["videoWidth"], item["videoHeight"]) for item in sources] == [(1920, 1080), (1080, 1920)]
    assert videos == saved
    host.selectVideo.assert_not_called()
    assert host._selected_video_id == "second"


def test_batch_preview_rejects_another_project_without_probing():
    host = SimpleNamespace(_batch_video_ids=["owned"])
    with patch("hflow.desktop.qml_controller.video_store.get_video") as read:
        assert HFlowController.batchPreviewMedia(host, "other-project") == {}
    read.assert_not_called()


def test_summary_distinguishes_pipeline_success_export_failure_pause_and_cancel():
    videos = [video("done", status="done"), video("failed", status="failed", error="Whisper failed"),
              video("cancelled", status="cancelled"), video("paused", status="paused"),
              video("review", status="awaiting_review")]
    jobs = [{"videoId": "done", "status": "failed", "error": "Disk full"}]
    result = batch_feedback.results(videos, jobs)
    assert (result["succeeded"], result["failed"], result["cancelled"], result["waiting"]) == (0, 2, 1, 2)
    assert result["rows"][0]["error"] == "Disk full"
    assert result["rows"][1]["error"] == "Whisper failed"
    assert "2 lỗi" in batch_feedback.completion_notice(result)[1]


def test_finished_count_and_progress_never_count_failure_as_success():
    host = SimpleNamespace(_batch_catalog_videos=lambda: [
        video("ok", status="done", progress=100), video("bad", status="failed", progress=20)])
    assert HFlowController.batchCompletedCount.fget(host) == 1
    assert HFlowController.batchProgress.fget(host) == 100


@pytest.mark.parametrize("status", ["paused", "awaiting_review", "failed", "done"])
def test_processing_only_summary_waits_for_resume_and_is_emitted_once(status):
    host = SimpleNamespace(_log_queue=queue.Queue(), _selected_video_id="",
                           _processing_queue=SimpleNamespace(has_work=False),
                           _batch_summary_ids=["one"], _settings_language="vi",
                           refreshVideos=Mock(), processingChanged=SimpleNamespace(emit=Mock()),
                           batchChanged=SimpleNamespace(emit=Mock()), appAlertRequested=SimpleNamespace(emit=Mock()))
    lifecycle = ProcessingLifecycleController(host)
    with patch("hflow.desktop.processing_lifecycle_controller.video_store.get_video",
               return_value=video(status=status)):
        for _ in range(2):
            host._log_queue.put("__QUEUE_IDLE__")
            lifecycle.drain_log_queue()
    assert host.appAlertRequested.emit.call_count == (0 if status in {"paused", "awaiting_review"} else 1)


def test_batch_dialogs_use_explicit_source_and_local_drafts():
    directory = Path(__file__).parents[1] / "src/hflow/desktop/qml"
    settings = (directory / "BatchSettingsDialog.qml").read_text(encoding="utf-8")
    assert "AppController.batchPreviewSources()" in settings
    assert "item.videoId === AppController.selectedVideoId" in settings
    assert "previewMedia: root.previewMedia" in settings
    assert "videoThumbnailSource: root.previewSource.thumbnailSource" in settings
    assert "AppController.selectBatchVideo(" not in settings
    assert "AppController.reviewPreviewMedia" not in settings
    assert "AppController.subtitleAppearance =" not in settings


@pytest.mark.parametrize("stage", ["Whisper", "translation", "OmniVoice", "Demucs", "OCR", "FFmpeg"])
def test_real_serial_queue_continues_after_each_simulated_stage_failure(stage):
    release = threading.Event()
    idle = threading.Event()
    records = {key: video(key) for key in ["before", "bad", "after"]}
    completed = []
    def runner(key):
        if key == "before":
            assert release.wait(3)
        records[key].status = "processing"
        if key == "bad":
            raise RuntimeError(f"{stage}: simulated failure")
        records[key].status = "done"
    def error(key, exc):
        records[key].status = "failed"
        records[key].error = str(exc)
    processing = SerialProcessingQueue(runner, on_error=error, on_finished=completed.append, on_idle=idle.set)
    try:
        for key in records:
            assert processing.enqueue(key)
        release.set()
        assert idle.wait(5)
        assert completed == ["before", "bad", "after"]
        summary = batch_feedback.results(records.values())
        assert (summary["succeeded"], summary["failed"]) == (2, 1)
        assert summary["rows"][1]["error"] == f"{stage}: simulated failure"
    finally:
        release.set()
        assert processing.shutdown(timeout_seconds=5)


def test_resume_process_export_has_no_duplicate_processing_only_notice():
    current = video(status="paused")
    host = SimpleNamespace(_batch_video_ids=["one"], _enqueue_videos=Mock(return_value=1),
                           _processing_queue=SimpleNamespace(contains=lambda _key: False),
                           batchChanged=SimpleNamespace(emit=Mock()),
                           _video_exports=SimpleNamespace(jobs=[{"videoId": "one", "process": True, "status": "paused"}]))
    commands = ProjectCommandsController(host)
    with patch("hflow.desktop.project_commands_controller.video_store.get_video", return_value=current), \
            patch.object(commands, "_resources_ready_for_videos", return_value=True), \
            patch("hflow.services.processing_resume.can_resume", return_value=True):
        commands.resume_batch()
    assert host._batch_summary_ids == []
    host._enqueue_videos.assert_called_once_with(["one"])

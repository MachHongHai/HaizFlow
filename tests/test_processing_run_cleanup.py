"""Cancel rolls back this run; pause/resume preserves it; restart discards it."""

import uuid
from pathlib import Path

import pytest

from hflow.schemas.video import VideoConfig
from hflow.services import manual_artifacts, processing_runs, project_store, video_store


@pytest.fixture
def video_factory(tmp_path, monkeypatch):
    monkeypatch.setattr(processing_runs, "_RUNS", {})
    monkeypatch.setattr(processing_runs, "_CHECKED", set())
    monkeypatch.setattr(processing_runs, "_ARMED_EXPORTS", {})
    monkeypatch.setattr(processing_runs, "_ARMED_EXPORT_STATES", {})
    processing_runs._CURRENT.run = None
    def create(kind="manual"):
        project = project_store.create_project("Run " + uuid.uuid4().hex[:8], str(tmp_path), kind)
        config = VideoConfig(project_type=kind, project_key=project["key"], project_id=project["project_id"],
                             project_name=project["project_name"], project_directory=str(tmp_path))
        video = video_store.create_video(uuid.uuid4().hex, "source.mp4", config)
        Path(video.files["video_input"]).write_bytes(b"original source")
        video_store.update_video(video.video_id, manual_target_tool="export" if kind == "manual" else "",
                                 status="processing")
        return video_store.get_video(video.video_id)
    yield create
    processing_runs._CURRENT.run = None


def artifact(video, kind, signature, data=b"result", activate=True):
    staged = manual_artifacts.create_staging_directory(video.video_id, kind)
    (staged / "result.bin").write_bytes(data)
    return manual_artifacts.publish(video.video_id, kind, signature, staged, {"data": "result.bin"},
                                    activate_artifact=activate)


def test_cancel_removes_new_complete_cache_but_restores_previous_result(video_factory):
    video = video_factory()
    old = artifact(video, "export", "old", b"old complete result")
    old_path = Path(old["resolved_outputs"]["data"])
    video_store.update_video(video.video_id, files={**video.files, "final_video": str(old_path)})
    scope_id = processing_runs.arm_export(video.video_id)
    processing_runs.begin(video.video_id)
    new = artifact(video, "export", "new", b"new complete result")
    new_path = Path(new["resolved_outputs"]["data"])
    video_store.update_video(video.video_id, files={**video.files, "final_video": str(new_path)}, status="cancelled")
    processing_runs.request_discard(video.video_id, scope_id)
    processing_runs.finish(video.video_id)
    assert old_path.read_bytes() == b"old complete result"
    assert not new_path.exists()
    restored = video_store.get_video(video.video_id)
    assert restored.active_artifacts["export"] == "old"
    assert restored.files["final_video"] == str(old_path)
    assert Path(video.files["video_input"]).read_bytes() == b"original source"
    assert processing_runs._get(video.video_id) is None


@pytest.mark.parametrize("prior_status", ["manual_ready", "done", "paused"])
def test_cancelled_manual_export_restores_exact_idle_state_after_cache_rollback(video_factory, prior_status):
    video = video_factory()
    old = artifact(video, "export", "old-state")
    fields = {"status": prior_status, "step": "manual_voice", "step_detail": "Giọng đã tạo",
              "progress": 81, "current_item": 7, "total_items": 7, "error": None,
              "manual_target_tool": "voice" if prior_status == "paused" else "",
              "resume_step": "voice" if prior_status == "paused" else ""}
    video_store.update_video(video.video_id, **fields)
    identifier = processing_runs.arm_export(video.video_id)
    # Queue updates happen after capture, before the worker journal exists.
    video_store.update_video(video.video_id, status="processing", progress=0, manual_target_tool="export")
    processing_runs.begin(video.video_id)
    new = artifact(video, "export", "cancelled-new")
    video_store.update_video(video.video_id, status="cancelled", step="cancelled", progress=99, resume_step="")
    processing_runs.request_discard(video.video_id, identifier)
    processing_runs.finish(video.video_id)
    restored = video_store.get_video(video.video_id)
    for name, value in fields.items():
        assert getattr(restored, name) == value
    assert restored.active_artifacts["export"] == "old-state"
    assert Path(old["resolved_outputs"]["data"]).exists()
    assert not Path(new["resolved_outputs"]["data"]).exists()


def test_cancelled_export_idle_snapshot_survives_app_restart_journal_load(video_factory, monkeypatch):
    video = video_factory()
    video_store.update_video(video.video_id, status="manual_ready", manual_target_tool="", progress=87)
    identifier = processing_runs.arm_export(video.video_id)
    video_store.update_video(video.video_id, status="processing", manual_target_tool="export")
    processing_runs.begin(video.video_id)
    video_store.update_video(video.video_id, status="paused")
    processing_runs.finish(video.video_id)
    monkeypatch.setattr(processing_runs, "_RUNS", {})
    monkeypatch.setattr(processing_runs, "_CHECKED", set())
    monkeypatch.setattr(processing_runs, "_ARMED_EXPORTS", {})
    monkeypatch.setattr(processing_runs, "_ARMED_EXPORT_STATES", {})
    video_store.update_video(video.video_id, status="cancelled")
    assert processing_runs.settle_export(video.video_id, "cancelled", identifier)
    restored = video_store.get_video(video.video_id)
    assert restored.status == "manual_ready" and restored.progress == 87
    assert not restored.manual_target_tool


def test_queued_cancel_without_worker_restores_state_but_not_a_replaced_source(video_factory):
    video = video_factory()
    video_store.update_video(video.video_id, status="manual_ready", manual_target_tool="")
    video = video_store.get_video(video.video_id)
    snapshot = processing_runs.manual_export_state(video)
    video_store.update_video(video.video_id, status="cancelled", manual_target_tool="export")
    assert processing_runs.restore_cancelled_manual_export(video.video_id, snapshot)
    assert video_store.get_video(video.video_id).status == "manual_ready"
    video_store.update_video(video.video_id, status="cancelled", created_at="changed-source")
    assert not processing_runs.restore_cancelled_manual_export(video.video_id, snapshot)
    assert video_store.get_video(video.video_id).status == "cancelled"


def test_auto_export_cancel_keeps_its_original_cancel_semantics(video_factory):
    video = video_factory("single")
    assert processing_runs.manual_export_state(video) is None
    identifier = processing_runs.arm_export(video.video_id)
    processing_runs.begin(video.video_id)
    video_store.update_video(video.video_id, status="cancelled")
    processing_runs.request_discard(video.video_id, identifier)
    processing_runs.finish(video.video_id)
    assert video_store.get_video(video.video_id).status == "cancelled"


def test_pause_and_resume_keep_progress_then_explicit_restart_removes_it(video_factory):
    video = video_factory()
    old = artifact(video, "tts_clip", "before", activate=False)
    processing_runs.begin(video.video_id)
    partial = artifact(video, "tts_clip", "during", activate=False)
    video_store.update_video(video.video_id, status="paused", resume_step="export")
    processing_runs.finish(video.video_id)
    assert Path(partial["resolved_outputs"]["data"]).exists()
    run_id = processing_runs._get(video.video_id)["id"]
    processing_runs.begin(video.video_id, resuming=True)
    assert processing_runs._get(video.video_id)["id"] == run_id
    video_store.update_video(video.video_id, status="paused")
    processing_runs.finish(video.video_id)
    processing_runs.begin(video.video_id, resuming=False)
    assert not Path(partial["resolved_outputs"]["data"]).exists()
    assert Path(old["resolved_outputs"]["data"]).exists()
    video_store.update_video(video.video_id, status="manual_ready")
    processing_runs.finish(video.video_id)


def test_auto_cancel_restores_mutable_old_files_and_drops_only_new_files(video_factory):
    video = video_factory("single")
    temporary = Path(video_store.get_video_dir(video.video_id)) / "temp"
    temporary.mkdir(exist_ok=True)
    old = temporary / "voice_final.wav"
    old.write_bytes(b"previous valid audio")
    scope_id = processing_runs.arm_export(video.video_id)
    processing_runs.begin(video.video_id)
    old.write_bytes(b"overwritten by current run")
    new = temporary / "new-render.mp4"
    new.write_bytes(b"partial")
    video_store.update_video(video.video_id, status="cancelled")
    processing_runs.request_discard(video.video_id, scope_id)
    processing_runs.finish(video.video_id)
    assert old.read_bytes() == b"previous valid audio" and not new.exists()
    assert not list(temporary.parent.glob(".processing-backup-*"))


def test_prior_cache_cannot_be_pruned_while_run_temporarily_replaces_active_reference(video_factory):
    video = video_factory()
    old = artifact(video, "export", "old")
    processing_runs.begin(video.video_id)
    artifact(video, "export", "new")
    manual_artifacts.prune(video.video_id, limit_bytes=0)
    assert Path(old["resolved_outputs"]["data"]).exists()
    video_store.update_video(video.video_id, status="cancelled")
    processing_runs.request_discard(video.video_id)
    processing_runs.finish(video.video_id)


def test_pending_cancel_retries_after_reader_unpins_new_artifact(video_factory):
    video = video_factory()
    artifact(video, "export", "old")
    identifier = processing_runs.arm_export(video.video_id)
    processing_runs.begin(video.video_id)
    current = artifact(video, "export", "new")
    manual_artifacts.pin(video.video_id, "export", "new", "test-reader")
    video_store.update_video(video.video_id, status="cancelled")
    processing_runs.request_discard(video.video_id, identifier)
    processing_runs.finish(video.video_id)
    assert Path(current["resolved_outputs"]["data"]).exists()
    assert processing_runs.discard_pending(video.video_id, identifier)
    manual_artifacts.unpin(video.video_id, "test-reader")
    assert processing_runs.settle_export(video.video_id, "cancelled", identifier)
    assert not Path(current["resolved_outputs"]["data"]).exists()


def test_old_export_completion_cannot_discard_a_later_run(video_factory):
    video = video_factory()
    identifier = processing_runs.arm_export(video.video_id)
    processing_runs.begin(video.video_id)
    video_store.update_video(video.video_id, status="done")
    processing_runs.finish(video.video_id)
    processing_runs.settle_export(video.video_id, "done", identifier)
    new_id = processing_runs.arm_export(video.video_id)
    processing_runs.begin(video.video_id)
    current = artifact(video, "export", "new")
    processing_runs.request_discard(video.video_id, identifier)
    assert processing_runs.settle_export(video.video_id, "cancelled", identifier)
    assert not processing_runs._get(video.video_id)["discard"]
    assert processing_runs._get(video.video_id)["id"] == new_id
    assert Path(current["resolved_outputs"]["data"]).exists()
    video_store.update_video(video.video_id, status="done")
    processing_runs.finish(video.video_id)
    processing_runs.settle_export(video.video_id, "done", new_id)


def test_switching_tools_after_pause_does_not_discard_completed_progress(video_factory):
    video = video_factory()
    video_store.update_video(video.video_id, manual_target_tool="voice")
    processing_runs.begin(video.video_id)
    partial = artifact(video, "tts_clip", "completed-before-pause", activate=False)
    video_store.update_video(video.video_id, status="paused", resume_step="voice")
    processing_runs.finish(video.video_id)
    video_store.update_video(video.video_id, manual_target_tool="image", resume_step="")
    processing_runs.begin(video.video_id, resuming=False)
    assert Path(partial["resolved_outputs"]["data"]).exists()
    video_store.update_video(video.video_id, status="manual_ready")
    processing_runs.finish(video.video_id)


def test_cancel_waiting_export_disarms_only_it_not_prior_paused_tool(video_factory):
    video = video_factory()
    processing_runs.begin(video.video_id)
    video_store.update_video(video.video_id, status="paused", resume_step="export")
    processing_runs.finish(video.video_id)
    old = processing_runs._get(video.video_id)
    waiting_id = processing_runs.arm_export(video.video_id)
    processing_runs.request_discard(video.video_id, waiting_id)
    assert video.video_id not in processing_runs._ARMED_EXPORTS
    assert processing_runs._get(video.video_id)["id"] == old["id"]
    assert not old["discard"]
    video_store.update_video(video.video_id, status="manual_ready")
    processing_runs.begin(video.video_id)
    processing_runs.finish(video.video_id)


def test_copy_of_previous_ready_render_does_not_keep_or_rollback_old_run_journal(video_factory):
    video = video_factory()
    processing_runs.arm_export(video.video_id)
    processing_runs.begin(video.video_id)
    current = artifact(video, "export", "ready-from-previous-session")
    video_store.update_video(video.video_id, status="done")
    processing_runs.finish(video.video_id)
    assert processing_runs._get(video.video_id)["state"] == "ready"
    processing_runs.commit_previous_ready(video.video_id)
    assert processing_runs._get(video.video_id) is None
    assert Path(current["resolved_outputs"]["data"]).exists()


def test_export_cancel_cleans_published_worker_results_before_queue_detaches(video_factory, monkeypatch):
    import threading
    from unittest.mock import Mock
    from PySide6.QtCore import QObject
    from PySide6.QtGui import QGuiApplication
    from hflow.desktop.processing_lifecycle_controller import ProcessingLifecycleController
    from hflow.desktop.video_export_controller import VideoExportController
    from hflow.pipeline.process_registry import check_cancellation, clean_video, start_video
    from hflow.services.processing_queue import SerialProcessingQueue

    app = QGuiApplication.instance() or QGuiApplication([])
    video = video_factory()
    old = artifact(video, "export", "before-run")
    started = threading.Event()
    release = threading.Event()
    state = {}
    host = QObject()
    host._settings_language = "vi"
    host._deleted_video_ids = set()
    host._initial_model_warmup_done = threading.Event()
    for name in ("exportStateChanged", "selectedVideoChanged", "processingChanged"):
        setattr(host, name, Mock())
    host.refreshVideos = Mock()
    lifecycle = ProcessingLifecycleController(host)
    task_queue = SerialProcessingQueue(lifecycle.execute_pipeline)
    host._processing_queue = task_queue
    exporter = VideoExportController(host)
    exporter.timer.stop()
    def pipeline(identifier, _tool):
        start_video(identifier)
        state["new"] = artifact(video_store.get_video(identifier), "audio_mix", "worker-new-result")
        started.set()
        try:
            release.wait(3)
            check_cancellation(identifier)
        except RuntimeError:
            video_store.update_video(identifier, status="cancelled", step="cancelled")
        finally:
            clean_video(identifier)
    monkeypatch.setattr("hflow.pipeline.manual_tools.run_manual_tool_sync", pipeline)
    identifier = processing_runs.arm_export(video.video_id)
    job = {"videoId": video.video_id, "status": "rendering", "progress": 10, "runScopeId": identifier}
    exporter.jobs = [job]
    try:
        assert task_queue.enqueue(video.video_id) and started.wait(2)
        exporter._capture_render_owner(job)
        exporter.cancel_all()
        release.set()
        assert task_queue.shutdown(timeout_seconds=3)
        exporter.poll()
        assert not Path(state["new"]["resolved_outputs"]["data"]).exists()
        assert Path(old["resolved_outputs"]["data"]).exists()
        assert not exporter.busy and job["runSettled"]
        assert video_store.get_video(video.video_id).active_artifacts == {"export": "before-run"}
    finally:
        release.set()
        task_queue.shutdown(timeout_seconds=3)
        exporter.shutdown()
        app.processEvents()

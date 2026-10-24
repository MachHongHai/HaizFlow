"""Fault injection at Batch settings/history/pause boundaries, without user data."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from haizflow.desktop.localization import QMessageBox
from haizflow.desktop.processing_lifecycle_controller import ProcessingLifecycleController
from haizflow.desktop.project_commands_controller import ProjectCommandsController
from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.pipeline import process_registry
from haizflow.schemas.video import VideoConfig
from haizflow.services import batch_settings, project_store, video_store


def make_video(identifier, **changes):
    config = VideoConfig(project_type="batch", speech_recognition_model="small-cpu")
    return SimpleNamespace(**{**config.model_dump(), "subtitle_style": config.subtitle_style,
        "video_id": identifier, "files": {},
        "original_filename": identifier + ".mp4", "status": "done", "progress": 100,
        "step": "done", "resume_step": "", "step_detail": "Completed", "error": None, **changes})


def test_batch_asset_undo_preflights_every_video_before_restoring_any(monkeypatch):
    records = {item.video_id: item for item in [make_video("first"), make_video("busy", status="processing")]}
    restored = []

    def restore(identifier, snapshot):
        if identifier == "busy":
            return False
        restored.append(identifier)
        return True

    host = SimpleNamespace(_selected_project_key="batch",
        _processing_queue=SimpleNamespace(contains=lambda key: key == "busy"),
        _restore_video_asset_snapshot=restore)
    monkeypatch.setattr(video_store, "get_video", records.get)
    assert not HaizFlowController._apply_batch_asset_snapshots(host, "batch", {"first": {}, "busy": {}}, {})
    assert restored == []


def test_batch_settings_failure_restores_result_status_as_well_as_configuration(monkeypatch):
    records = {item.video_id: item for item in [make_video("first"), make_video("second")]}
    original = deepcopy(records)
    baseline = batch_settings.values_for(records["first"])

    def update(identifier, **changes):
        records[identifier].__dict__.update(changes)
        return records[identifier]

    def restore(identifier, snapshot):
        for field in batch_settings.FIELDS.values():
            setattr(records[identifier], field, deepcopy(snapshot[field]))
        return True

    host = SimpleNamespace(_selected_project_key="batch", _batch_video_ids=list(records),
        _settings_processing_device="cpu", _processing_queue=SimpleNamespace(contains=lambda _: False),
        _capture_video_asset_snapshot=lambda video, **_: deepcopy(video.__dict__),
        _restore_video_asset_snapshot=restore, _show_app_alert=Mock(),
        _record_batch_asset_change=Mock(), refreshVideos=Mock(), batchChanged=Mock())
    commands = ProjectCommandsController(host)
    monkeypatch.setattr(commands, "batch_settings_values", lambda: deepcopy(baseline))
    monkeypatch.setattr(video_store, "get_video", records.get)
    monkeypatch.setattr(video_store, "update_video", update)
    monkeypatch.setattr(batch_settings, "stage_asset", lambda *_: "")
    monkeypatch.setattr(project_store, "save_batch_settings", Mock(side_effect=OSError("disk full")))
    assert not commands.apply_batch_settings_values("batch", {"originalVolume": 37})
    assert records == original
    host._record_batch_asset_change.assert_not_called()


@pytest.mark.parametrize("terminal", ["done", "failed", "cancelled", "awaiting_review"])
def test_batch_pause_does_not_relabel_a_video_that_finished_during_detach(monkeypatch, terminal):
    current = make_video("first", status="processing", step="rendering")

    def detach(_ids):
        current.status, current.step = terminal, terminal
        return current.video_id, []

    updates = Mock()
    host = SimpleNamespace(isBatchRunning=True, _batch_video_ids=[current.video_id],
        _processing_queue=SimpleNamespace(detach_pending=detach),
        _refresh_batch_model=Mock(), batchChanged=Mock())
    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(video_store, "get_video", lambda _: current)
    monkeypatch.setattr(video_store, "update_video", updates)
    monkeypatch.setattr(video_store, "log_to_video", Mock())
    pause = Mock()
    monkeypatch.setattr("haizflow.desktop.project_commands_controller.pause_video", pause)
    ProjectCommandsController(host).stop_batch()
    updates.assert_not_called()
    pause.assert_not_called()


@pytest.mark.parametrize("operation", ["pause", "cancel"])
def test_queue_started_does_not_revive_a_stopped_batch_video(monkeypatch, operation):
    current = make_video("handoff", status="pending", step="queued", resume_step="translating")
    process_registry.prepare_video_resume(current.video_id)

    def activate(_):
        getattr(process_registry, operation + "_video")(current.video_id)
        current.status = "paused" if operation == "pause" else "cancelled"
        current.step = current.status

    host = SimpleNamespace(_deleted_video_ids=set(), _activate_pending_device_for_next_video=activate,
                           _processing_queue=SimpleNamespace(pending_ids=lambda: []), _log_queue=Mock())
    monkeypatch.setattr(video_store, "get_video", lambda _: current)
    writes = Mock()
    monkeypatch.setattr(video_store, "update_video", writes)
    try:
        ProcessingLifecycleController(host).on_queue_video_started(current.video_id)
        writes.assert_not_called()
        assert current.resume_step == "translating"
    finally:
        process_registry.clean_video(current.video_id)


def test_batch_asset_history_rolls_back_partial_restore_failure(monkeypatch):
    records = {item.video_id: item for item in [make_video("first"), make_video("second")]}
    original = deepcopy(records)
    calls = []

    def restore(identifier, snapshot):
        calls.append(identifier)
        records[identifier].original_video_volume = snapshot["volume"]
        return len(calls) != 2

    host = SimpleNamespace(_selected_project_key="batch",
        _processing_queue=SimpleNamespace(contains=lambda _: False),
        _capture_video_asset_snapshot=lambda video, **_: {"volume": video.original_video_volume},
        _restore_video_asset_snapshot=restore)
    monkeypatch.setattr(video_store, "get_video", records.get)
    save = Mock()
    monkeypatch.setattr(project_store, "save_batch_settings", save)
    assert not HaizFlowController._apply_batch_asset_snapshots(
        host, "batch", {"first": {"volume": 12}, "second": {"volume": 12}}, {})
    assert records == original
    save.assert_not_called()


@pytest.mark.parametrize("operation", ["pause", "cancel"])
def test_queue_handoff_reconciles_stop_during_metadata_write(monkeypatch, operation):
    current = make_video("handoff-write", status="pending", step="queued", resume_step="translating")
    process_registry.prepare_video_resume(current.video_id)

    def update(identifier, **changes):
        current.__dict__.update(changes)
        if changes.get("status") == "processing":
            getattr(process_registry, operation + "_video")(identifier)
        return current

    host = SimpleNamespace(_deleted_video_ids=set(), _activate_pending_device_for_next_video=lambda _: None,
                           _processing_queue=SimpleNamespace(pending_ids=lambda: []), _log_queue=Mock())
    monkeypatch.setattr(video_store, "get_video", lambda _: current)
    monkeypatch.setattr(video_store, "update_video", update)
    monkeypatch.setattr(video_store, "log_to_video", Mock())
    try:
        ProcessingLifecycleController(host).on_queue_video_started(current.video_id)
        assert current.status == ("paused" if operation == "pause" else "cancelled")
        assert current.resume_step == "translating"
    finally:
        process_registry.clean_video(current.video_id)


@pytest.mark.parametrize("terminal", ["done", "failed", "awaiting_review"])
def test_batch_pause_preserves_completion_while_child_process_is_stopping(monkeypatch, terminal):
    current = make_video("finish-on-pause", status="processing", step="rendering")
    host = SimpleNamespace(isBatchRunning=True, _batch_video_ids=[current.video_id],
        _processing_queue=SimpleNamespace(detach_pending=lambda _: (current.video_id, [])),
        _refresh_batch_model=Mock(), batchChanged=Mock())

    def pause(_):
        current.status, current.step = terminal, terminal

    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(video_store, "get_video", lambda _: current)
    update = Mock()
    monkeypatch.setattr(video_store, "update_video", update)
    monkeypatch.setattr("haizflow.desktop.project_commands_controller.pause_video", pause)
    ProjectCommandsController(host).stop_batch()
    update.assert_not_called()

"""Delete confirmation stays cheap; media cleanup never owns the GUI thread."""

import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from haizflow.desktop.channel_import import ChannelImportCoordinator
from haizflow.desktop.localization import QMessageBox
from haizflow.desktop.project_commands_controller import ProjectCommandsController
from haizflow.services import project_store


def host():
    return SimpleNamespace(_background_events_timer=object(), _catalog_videos={},
        _selected_project_key="another-project", _deleted_video_ids=set(),
        _processing_queue=SimpleNamespace(detach_pending=Mock(return_value=(None, [])), active_video_id=""),
        _channel_importer=SimpleNamespace(cancel_project=Mock(return_value=True)), _channel_import_targets={},
        appAlertRequested=SimpleNamespace(emit=Mock()), refreshVideos=Mock(),
        projectDeletionDialogStateChanged=SimpleNamespace(emit=Mock()),
        videoDeleted=SimpleNamespace(emit=Mock()))


@pytest.mark.parametrize("answer", [QMessageBox.StandardButton.No, QMessageBox.StandardButton.Cancel,
                                    QMessageBox.StandardButton.Close])
def test_cancel_confirmation_does_not_enumerate_or_touch_project_files(answer):
    owner = host()
    commands = ProjectCommandsController(owner)
    project = {"key": "delete-me", "project_name": "Long project", "project_type": "manual", "videos": []}
    with (patch.object(QMessageBox, "question", return_value=answer),
          patch("haizflow.services.video_store.list_videos", side_effect=AssertionError("No disk catalog walk")),
          patch.object(project_store, "delete_project_by_key") as remove):
        assert not commands.delete_project_summary(project)
    remove.assert_not_called()
    assert not commands.is_deleting(project["key"])
    assert [call.args[0] for call in owner.projectDeletionDialogStateChanged.emit.call_args_list] == [
        "confirming", "finished"]


def test_yes_returns_immediately_and_disk_work_runs_only_in_background():
    owner = host()
    commands = ProjectCommandsController(owner)
    project = {"key": "delete-me", "project_name": "Long project", "project_type": "manual", "videos": []}
    entered, release = threading.Event(), threading.Event()
    gui_thread = threading.get_ident()

    def slow_remove(*_args, **_kwargs):
        assert threading.get_ident() != gui_thread
        entered.set()
        assert release.wait(3)

    with (patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes) as question,
          patch.object(commands, "_delete_project_files", side_effect=slow_remove),
          patch("haizflow.services.video_store.list_videos", side_effect=AssertionError("Use row snapshot"))):
        start = time.perf_counter()
        try:
            assert commands.delete_project_summary(project)
            assert time.perf_counter() - start < .2
            assert entered.wait(1)
            assert commands.is_deleting(project["key"])
            assert not commands.delete_project_summary(project)  # No duplicate dialog/worker.
            question.assert_called_once()
            owner.refreshVideos.assert_not_called()  # No worker-side Qt mutations.
            owner.projectDeletionDialogStateChanged.emit.assert_called_once_with("confirming")
            owner.appAlertRequested.emit.assert_not_called()
        finally:
            release.set()
            commands._deletions[project["key"]].join(3)
        commands.drain_deletion_events()
    assert not commands.is_deleting(project["key"])
    assert owner.projectDeletionDialogStateChanged.emit.call_args.args == ("finished",)


def test_long_project_deletes_owned_root_once_not_each_video(tmp_path):
    owner = host()
    commands = ProjectCommandsController(owner)
    videos = [SimpleNamespace(video_id=str(index)) for index in range(1000)]
    project = {"key": "project", "project_name": "Batch", "project_type": "batch"}
    directory = tmp_path / "batch"
    directory.mkdir()
    with (patch.object(project_store, "get_project", return_value={"project_root": str(directory)}),
          patch("haizflow.services.video_store.get_video_dir", side_effect=lambda key: str(directory / key)),
          patch("haizflow.services.video_store.delete_video") as child_delete,
          patch.object(project_store, "validate_project_deletion_by_key") as deep_preflight,
          patch.object(project_store, "delete_project_by_key") as root_delete):
        commands._delete_project_files(project, videos, background=True)
    child_delete.assert_not_called()
    deep_preflight.assert_not_called()
    assert root_delete.call_count == 1


def test_windows_preview_handle_retry_runs_outside_ui_slot(tmp_path):
    owner = host()
    commands = ProjectCommandsController(owner)
    project = {"key": "project", "project_name": "Project", "project_type": "manual"}
    attempts = []

    def remove(key, *, on_detached):
        attempts.append(key)
        if len(attempts) < 3:
            raise PermissionError("preview closing")
        on_detached()
        return True

    with (patch.object(project_store, "get_project", return_value={"project_root": str(tmp_path)}),
          patch.object(project_store, "delete_project_by_key", side_effect=remove),
          patch("haizflow.desktop.project_commands_controller.time.sleep") as sleep):
        commands._delete_project_files(project, [], background=True)
    assert len(attempts) == 3
    assert [call.args[0] for call in sleep.call_args_list] == [.1, .2]
    assert commands._deletion_events.get_nowait()[0] == "detached"


def test_failed_preflight_restores_deletion_guards_and_keeps_other_project_selected():
    owner = host()
    commands = ProjectCommandsController(owner)
    video = SimpleNamespace(video_id="a")
    project = {"key": "pending", "project_name": "Pending", "project_type": "manual"}
    with patch.object(commands, "_delete_project_files", side_effect=ValueError("ownership")):
        assert commands._queue_project_delete(project, [video])
        commands._deletions[project["key"]].join(3)
    assert "a" in owner._deleted_video_ids
    commands.drain_deletion_events()
    assert "a" not in owner._deleted_video_ids
    assert owner._selected_project_key == "another-project"
    assert not commands.is_deleting(project["key"])
    owner.refreshVideos.assert_not_called()
    owner.projectDeletionDialogStateChanged.emit.assert_called_once_with("finished")


def test_detached_event_finishes_on_ui_thread_without_closing_newly_selected_project():
    owner = host()
    commands = ProjectCommandsController(owner)
    project = {"key": "old-project", "project_name": "Old"}
    commands._deletions[project["key"]] = Mock()
    commands._deletion_events.put(("detached", project, [], ""))
    commands.drain_deletion_events()
    owner.projectDeletionDialogStateChanged.emit.assert_not_called()
    assert commands.is_deleting(project["key"])
    commands._deletion_events.put(("done", project, [], ""))
    commands.drain_deletion_events()
    owner.refreshVideos.assert_called_once()
    owner.videoDeleted.emit.assert_not_called()
    assert owner._selected_project_key == "another-project"
    owner.projectDeletionDialogStateChanged.emit.assert_called_once_with("finished")


def test_preparation_refusal_closes_busy_confirmation_without_starting_worker():
    owner = host()
    commands = ProjectCommandsController(owner)
    project = {"key": "project", "project_name": "Project", "videos": []}
    with (patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes),
          patch.object(commands, "_stop_project_processing", return_value=False),
          patch.object(commands, "_queue_project_delete") as queue):
        assert not commands.delete_project_summary(project)
    queue.assert_not_called()
    assert [call.args[0] for call in owner.projectDeletionDialogStateChanged.emit.call_args_list] == [
        "confirming", "finished"]


def test_worker_start_failure_does_not_leave_project_permanently_busy():
    owner = host()
    commands = ProjectCommandsController(owner)
    project = {"key": "pending", "project_name": "Pending"}
    with (patch("haizflow.desktop.project_commands_controller.threading.Thread") as worker,
          pytest.raises(RuntimeError, match="no threads")):
        worker.return_value.start.side_effect = RuntimeError("no threads")
        commands._queue_project_delete(project, [SimpleNamespace(video_id="a")])
    assert not commands.is_deleting("pending")
    assert "a" not in owner._deleted_video_ids


def test_project_cancel_never_waits_ten_seconds_on_delete_button():
    runner = SimpleNamespace(is_alive=Mock(return_value=True), join=Mock())
    token = threading.Event()
    coordinator = SimpleNamespace(_prune_finished_runners=lambda: None,
        _sessions={"session": SimpleNamespace(project_key="project")},
        _cancel_events={"session": token}, _runner_threads={"session": runner},
        _candidate_maps={}, _session_metrics={}, _project_sessions={"project": "session"},
        _active_project_key="other")
    assert not ChannelImportCoordinator.cancel_project(coordinator, "project", timeout_seconds=0)
    assert token.is_set()
    runner.join.assert_not_called()
    assert "session" in coordinator._sessions  # Do not delete live worker files.
    runner.is_alive.return_value = False
    assert ChannelImportCoordinator.cancel_project(coordinator, "project", timeout_seconds=0)
    assert not coordinator._sessions

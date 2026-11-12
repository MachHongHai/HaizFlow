from types import SimpleNamespace
from unittest.mock import Mock

from haizflow.desktop.project_failure_notice import ProjectFailureNotice
from haizflow.desktop.project_workspace_controller import ProjectWorkspaceController
from haizflow.services import project_store, video_store


def video(name="one", status="failed"):
    return SimpleNamespace(video_id=name, status=status)


def test_opening_persisted_failure_never_replays_even_after_async_rows_or_reopen():
    notice = ProjectFailureNotice()
    notice.observe(video())
    for _ in range(10):
        notice.observe(video())
        assert not notice.claim("one")
    notice.observe(video("other", "done"))
    notice.observe(video())
    assert not notice.claim("one")
    fresh_session = ProjectFailureNotice()
    fresh_session.observe(video())
    assert not fresh_session.claim("one")


def test_new_failure_notifies_once_and_same_error_after_fast_retry_is_new_event():
    notice = ProjectFailureNotice()
    notice.observe(video(status="processing"))
    notice.observe(video())
    first = notice.revision
    assert notice.claim("one")
    assert not notice.claim("one")
    notice.started("one")
    notice.observe(video())
    assert notice.revision > first
    assert notice.claim("one")
    notice.observe(video())
    assert not notice.claim("one")


def test_notices_cannot_leak_to_another_project_or_erase_failure_status():
    notice = ProjectFailureNotice()
    notice.observe(video(status="processing"))
    failed = video()
    notice.observe(failed)
    assert not notice.claim("other")
    assert notice.claim("one")
    assert failed.status == "failed"
    notice.observe(video("other"))
    notice.started("one")
    assert not notice.claim("other")


def test_new_failure_uses_current_metadata_not_an_older_async_tool_row():
    from haizflow.desktop.qml_controller import HaizFlowController

    notice = ProjectFailureNotice()
    notice.observe(video(status="processing"))
    current = video()
    current.error = "CUDA out of memory"
    notice.observe(current)
    present = Mock()
    host = SimpleNamespace(_project_failure_notice=notice, _selected_video_id="one",
                           _selected_video=lambda: current, presentUserError=present)
    HaizFlowController.presentSelectedProjectFailure(host, "Failure", "Old network error", "log")
    present.assert_called_once_with("Failure", current.error, "log")
    HaizFlowController.presentSelectedProjectFailure(host, "Failure", "Old network error", "log")
    present.assert_called_once()


def test_reading_unchanged_project_roots_does_not_rewrite_registry(monkeypatch, tmp_path):
    root = str(tmp_path.resolve())
    monkeypatch.setattr(project_store, "_read_json", lambda _: [root])
    write = Mock()
    monkeypatch.setattr(project_store, "_write_json_atomic", write)
    for _ in range(50):
        project_store._remember_project_directories([{"project_directory": root}])
    write.assert_not_called()
    project_store._remember_project_directories([{"project_directory": str(tmp_path / "new")}])
    write.assert_called_once()


def test_catalog_enumeration_uses_one_validated_index_snapshot(monkeypatch, tmp_path):
    records = [{"key": str(i), "project_directory": str(tmp_path), "project_root": str(tmp_path / str(i))}
               for i in range(100)]
    for record in records:
        (tmp_path / record["key"] / "videos").mkdir(parents=True)
    read = Mock(return_value=records)
    monkeypatch.setattr(project_store, "list_projects", read)
    by_key = Mock(side_effect=AssertionError("Each project must not reread the entire index"))
    monkeypatch.setattr(project_store, "project_videos_dir_for_key", by_key)
    assert video_store._project_video_ids() == []
    read.assert_called_once()
    assert video_store._project_video_ids(records) == []
    read.assert_called_once()


def test_workspace_catalog_reuses_records_for_video_and_social_reads(monkeypatch):
    records = [{"key": "one", "project_type": "publish", "project_directory": "D:/fixtures", "project_root": "D:/fixtures/one"}]
    monkeypatch.setattr(project_store, "list_projects", Mock(return_value=records))
    videos = Mock(return_value=[])
    monkeypatch.setattr(video_store, "list_videos", videos)
    monkeypatch.setattr(project_store, "project_root_for_key", Mock(side_effect=AssertionError("Repeated index read")))
    monkeypatch.setattr("haizflow.desktop.project_workspace_controller.tiktok_publish.summarize", lambda _: {
        "item_count": 0, "status": "ready", "progress": 0, "thumbnail_path": ""})
    host = SimpleNamespace(_build_project_summaries=lambda *_: [{"key": "one", "project_type": "publish"}],
                           _missing_thumbnail_ids=lambda _: [])
    result = ProjectWorkspaceController(host)._collect_catalog()
    videos.assert_called_once_with(projects=records)
    project_store.list_projects.assert_called_once()
    assert result[2][0]["status"] == "ready"


def test_initial_catalog_has_disk_priority_but_error_still_starts_recovery(monkeypatch):
    from haizflow.desktop.qml_controller import HaizFlowController

    thread = Mock()
    monkeypatch.setattr("haizflow.desktop.qml_controller.threading.Thread", thread)
    host = SimpleNamespace(_shutdown_started=False, _startup_maintenance_thread=None,
                           _project_catalog_state="loading", _run_startup_maintenance=Mock())
    HaizFlowController._start_startup_maintenance(host)
    thread.assert_not_called()
    host._project_catalog_state = "error"
    HaizFlowController._start_startup_maintenance(host)
    thread.return_value.start.assert_called_once()
    HaizFlowController._start_startup_maintenance(host)
    thread.return_value.start.assert_called_once()

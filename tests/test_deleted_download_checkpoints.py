"""Late GUI checkpoints must never resurrect a detached download project."""
from pathlib import Path
import json
import threading

import pytest
from PySide6.QtGui import QGuiApplication

from haizflow.desktop.channel_import import ChannelImportCoordinator
from haizflow.desktop.media_download_controller import MediaDownloadController
from haizflow.schemas.channel_import import ChannelImportRequest
from haizflow.services import project_store
from haizflow.services.channel_import import new_session, save_session


_APP = None


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    global _APP
    _APP = QGuiApplication.instance() or QGuiApplication([])
    monkeypatch.setattr(project_store, "PROJECT_INDEX_PATH", str(tmp_path / "index/projects.json"))
    project = project_store.create_project("Downloads", str(tmp_path / "projects"), "download")
    controller = MediaDownloadController()
    controller.attach_project(project["key"], project["project_root"])
    controller.saveWorkspaceState({"videoUrl": "https://example.com/video"})
    controller.flush_checkpoint()
    try:
        yield project, controller
    finally:
        controller.shutdown()


def test_detaching_after_delete_does_not_recreate_workspace_json(workspace):
    project, controller = workspace
    root = Path(project["project_root"])
    assert (root / "downloads/workspace.json").is_file()
    assert project_store.delete_project_by_key(project["key"])
    controller.attach_project("", "")
    _APP.processEvents()
    assert not root.exists()


def test_checkpoint_timer_and_shutdown_after_delete_do_not_recreate_root(workspace):
    project, controller = workspace
    root = Path(project["project_root"])
    assert project_store.delete_project_by_key(project["key"])
    controller._on_preview_changed()
    controller.flush_checkpoint()
    controller.shutdown()
    assert not root.exists()


def test_checkpoint_after_detach_commit_cannot_leave_sibling_ghost(workspace):
    project, controller = workspace
    root = Path(project["project_root"])
    assert project_store.delete_project_by_key(project["key"], on_detached=controller.flush_checkpoint)
    assert not root.exists()
    assert not list(root.parent.glob(".haizflow-project-delete-*"))


def test_late_channel_save_does_not_recreate_deleted_project(workspace):
    project, _controller = workspace
    root = Path(project["project_root"])
    session = new_session(project["key"], str(root), ChannelImportRequest(
        url="https://www.youtube.com/@creator", platform="youtube"))
    save_session(session)
    assert project_store.delete_project_by_key(project["key"])
    ChannelImportCoordinator._save_session(session)
    assert not root.exists()


def test_checkpoint_does_not_overwrite_another_owner(workspace):
    project, controller = workspace
    root = Path(project["project_root"])
    marker = root / project_store.PROJECT_MANIFEST_NAME
    before = (root / "downloads/workspace.json").read_bytes()
    data = json.loads(marker.read_text("utf-8"))
    data["key"] = "project:another-owner"
    marker.write_text(json.dumps(data), encoding="utf-8")
    controller.saveWorkspaceState({"videoUrl": "stale value"})
    controller.flush_checkpoint()
    assert (root / "downloads/workspace.json").read_bytes() == before


def test_checkpoint_rejects_redirected_child_directory(workspace, monkeypatch):
    from haizflow.core import storage_ownership

    project, controller = workspace
    root = Path(project["project_root"])
    before = (root / "downloads/workspace.json").read_bytes()
    actual = storage_ownership.is_reparse
    monkeypatch.setattr(storage_ownership, "is_reparse",
                        lambda path: path == root / "downloads" or actual(path))
    controller.saveWorkspaceState({"videoUrl": "stale value"})
    controller.flush_checkpoint()
    assert (root / "downloads/workspace.json").read_bytes() == before


def test_checkpoint_write_and_project_detach_are_serialized(workspace):
    project, _controller = workspace
    root = Path(project["project_root"])
    path = root / "downloads/workspace.json"
    entered, release, removed = threading.Event(), threading.Event(), threading.Event()
    errors = []

    def write():
        try:
            with project_store.project_state_write_guard(project["key"], str(root), path) as writable:
                assert writable
                entered.set()
                assert release.wait(3)
                project_store._write_json_atomic(str(path), {"checkpoint": "complete"})
        except Exception as exc:
            errors.append(exc)

    def remove():
        try:
            assert project_store.delete_project_by_key(project["key"])
            removed.set()
        except Exception as exc:
            errors.append(exc)

    writer, deleter = threading.Thread(target=write), threading.Thread(target=remove)
    writer.start()
    try:
        assert entered.wait(2)
        deleter.start()
        assert not removed.wait(.05)
    finally:
        release.set()
        writer.join(5)
        if deleter.ident is not None:
            deleter.join(5)
    assert not writer.is_alive() and not deleter.is_alive()
    assert not errors and removed.is_set() and not root.exists()


def test_channel_restore_uses_current_owner_not_stale_saved_root(workspace, tmp_path):
    project, controller = workspace
    root = Path(project["project_root"])
    session = new_session(project["key"], str(root), ChannelImportRequest(
        url="https://www.youtube.com/@creator", platform="youtube"))
    save_session(session)
    checkpoint = root / "imports/channel" / session.session_id / "session.json"
    data = json.loads(checkpoint.read_text("utf-8"))
    stale = tmp_path / "old-project-location"
    data.update(project_root=str(stale), project_key="old-project-key")
    checkpoint.write_text(json.dumps(data), encoding="utf-8")
    controller._channel_importer.attach_project(project["key"], str(root), set())
    restored = controller._channel_importer._active_session()
    assert restored.project_root == str(root) and restored.project_key == project["key"]
    assert not stale.exists()


def test_deletion_keeps_files_outside_project_storage(workspace, tmp_path):
    project, controller = workspace
    external = tmp_path / "user-selected-output.mp4"
    external.write_bytes(b"User file outside managed project")
    assert project_store.delete_project_by_key(project["key"])
    controller.attach_project("", "")
    assert external.read_bytes() == b"User file outside managed project"

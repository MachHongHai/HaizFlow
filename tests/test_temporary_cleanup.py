"""Locked temporary files are retried without deleting replacement/user data."""

import ctypes
import os
from pathlib import Path

import pytest

from hflow.services.temporary_cleanup import TemporaryCleanupManager


def manager_at(root, monkeypatch):
    manager = TemporaryCleanupManager(root / "cleanup.json")
    monkeypatch.setattr(manager, "start", lambda: None)
    return manager


def test_locked_download_tree_is_journalled_and_cleaned_after_restart(tmp_path, monkeypatch):
    manager = manager_at(tmp_path, monkeypatch)
    workspace = tmp_path / "downloads" / "video--test"
    workspace.mkdir(parents=True)
    (workspace / "unfinished.mp4").write_bytes(b"partial")
    import shutil
    remove = shutil.rmtree
    def locked(path, *args, **kwargs):
        if Path(path) == workspace:
            raise PermissionError(13, "WinError 32: locked fixture")
        return remove(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr("hflow.services.temporary_cleanup.shutil.rmtree", locked)
        manager.discard(workspace, tree=True)
    assert workspace.exists() and manager.journal.exists()
    reopened = TemporaryCleanupManager(manager.journal)
    reopened.retry()
    assert not workspace.exists() and not reopened._pending


def test_locked_export_file_retries_but_completed_output_survives(tmp_path, monkeypatch):
    manager = manager_at(tmp_path, monkeypatch)
    partial = tmp_path / ".hflow-export-test.partial.mp4"
    partial.write_bytes(b"partial")
    final = tmp_path / "final.mp4"
    final.write_bytes(b"completed")
    unlink = Path.unlink
    with monkeypatch.context() as patch:
        def locked(path, *args, **kwargs):
            if path == partial:
                raise PermissionError(13, "WinError 32")
            return unlink(path, *args, **kwargs)
        patch.setattr(Path, "unlink", locked)
        manager.discard(partial, tree=False)
    manager.retry()
    assert not partial.exists() and final.read_bytes() == b"completed"


def test_replaced_file_is_not_removed_by_old_cleanup_record(tmp_path, monkeypatch):
    manager = manager_at(tmp_path, monkeypatch)
    partial = tmp_path / ".hflow-export-test.partial.mp4"
    partial.write_bytes(b"old")
    monkeypatch.setattr(manager, "_remove", lambda _entry: False)
    manager.discard(partial, tree=False)
    partial.write_bytes(b"new unrelated content")
    reopened = TemporaryCleanupManager(manager.journal)
    reopened.retry()
    assert partial.read_bytes() == b"new unrelated content"
    assert not reopened._pending


@pytest.mark.parametrize("name,tree", [("final.mp4", False), ("projects", True), ("downloads", True)])
def test_ordinary_files_and_broad_roots_are_never_cleanup_targets(tmp_path, monkeypatch, name, tree):
    manager = manager_at(tmp_path, monkeypatch)
    target = tmp_path / name
    if tree:
        target.mkdir()
        (target / "user.txt").write_text("keep", encoding="utf-8")
    else:
        target.write_bytes(b"keep")
    manager.discard(target, tree=tree)
    assert target.exists() and not manager._pending


def test_nested_project_blocks_recursive_temporary_cleanup(tmp_path, monkeypatch):
    manager = manager_at(tmp_path, monkeypatch)
    workspace = tmp_path / "downloads" / "video"
    project = workspace / "nested"
    project.mkdir(parents=True)
    (project / ".hflow-project.json").write_text("{}", encoding="utf-8")
    manager.discard(workspace, tree=True)
    assert project.exists() and not manager._pending


def test_owned_srt_revision_cleanup_and_locked_retry(tmp_path, monkeypatch):
    manager = manager_at(tmp_path, monkeypatch)
    revision = tmp_path / "input" / "subtitles" / ("a" * 32)
    revision.mkdir(parents=True)
    (revision / "segments.json").write_text("[]", encoding="utf-8")
    import shutil
    remove = shutil.rmtree
    with monkeypatch.context() as patch:
        def locked(path, *args, **kwargs):
            if Path(path) == revision:
                raise PermissionError("WinError 32")
            return remove(path, *args, **kwargs)
        patch.setattr("hflow.services.temporary_cleanup.shutil.rmtree", locked)
        manager.discard(revision, tree=True)
    assert revision.exists() and manager._pending
    reopened = TemporaryCleanupManager(manager.journal)
    reopened.retry()
    assert not revision.exists()
    assert revision.parent.exists() and revision.parent.parent.exists()


@pytest.mark.parametrize("name", ["subtitles", "video.mp4", "not-owned"])
def test_srt_cleanup_refuses_broad_or_non_revision_targets(tmp_path, monkeypatch, name):
    manager = manager_at(tmp_path, monkeypatch)
    target = tmp_path / "input" / "subtitles" / name
    target.mkdir(parents=True)
    (target / "keep.txt").write_text("keep", encoding="utf-8")
    manager.discard(target, tree=True)
    assert target.exists() and not manager._pending


@pytest.mark.skipif(os.name != "nt", reason="Real Windows file-sharing lock")
def test_actual_windows_locked_file_can_be_removed_after_handle_closes(tmp_path, monkeypatch):
    from ctypes import wintypes

    manager = manager_at(tmp_path, monkeypatch)
    partial = tmp_path / ".hflow-export-win-lock.partial.mp4"
    partial.write_bytes(b"partial")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(partial), 0x80000000, 0, None, 3, 0x80, None)
    assert handle not in (None, wintypes.HANDLE(-1).value), ctypes.get_last_error()
    try:
        manager.discard(partial, tree=False)
        assert partial.exists() and str(partial) in manager._pending
    finally:
        kernel.CloseHandle(handle)
    manager.retry()
    assert not partial.exists() and not manager._pending

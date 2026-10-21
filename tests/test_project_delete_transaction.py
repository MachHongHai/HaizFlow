"""Owned-root detach/purge is responsive, fail-closed and crash recoverable."""

import json
import stat
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from haizflow.core.storage_ownership import managed_storage_guard, safe_tree
from haizflow.services import project_store


@pytest.fixture
def projects(tmp_path, monkeypatch):
    monkeypatch.setattr(project_store, "PROJECT_INDEX_PATH", str(tmp_path / "data/projects.json"))
    parent = tmp_path / "projects"
    parent.mkdir()
    removed = project_store.ensure_project("Remove", str(parent), "manual")
    keep = project_store.ensure_project("Keep", str(parent), "manual")
    target = Path(removed["project_root"]) / "cache" / "audio.wav"
    target.parent.mkdir()
    target.write_bytes(b"voice data")
    return removed, keep, target


def test_recursive_purge_holds_neither_catalog_nor_shared_pin_lock(projects):
    removed, keep, target = projects
    actual = project_store._remove_project_root
    results = []

    def purge(path):
        assert not Path(removed["project_root"]).exists()
        def query():
            results.append([row["key"] for row in project_store.list_projects()])
            with managed_storage_guard:
                results.append("pin lock available")
        reader = threading.Thread(target=query)
        reader.start()
        reader.join(1)
        assert not reader.is_alive(), "Purge cannot freeze another project's GUI reads/pins"
        actual(path)

    with patch.object(project_store, "_remove_project_root", side_effect=purge):
        assert project_store.delete_project_by_key(removed["key"])
    assert results == [[keep["key"]], "pin lock available"]
    assert not target.exists()
    assert not list(project_store._deletion_journal_dir().glob("*.json"))


def test_unsafe_nested_project_rolls_back_without_deleting_any_data(projects):
    removed, _, target = projects
    nested = target.parent / "nested"
    nested.mkdir()
    marker = nested / project_store.PROJECT_MANIFEST_NAME
    marker.write_text("{}")
    with pytest.raises(ValueError, match="nested"):
        project_store.delete_project_by_key(removed["key"])
    assert target.read_bytes() == b"voice data"
    assert marker.read_text() == "{}"
    assert project_store.get_project(removed["key"])
    assert not list(project_store._deletion_journal_dir().glob("*.json"))


def test_commit_failure_restores_original_root_and_index(projects):
    removed, _, target = projects
    with (patch.object(project_store, "_save_index", side_effect=OSError("disk full")),
          pytest.raises(OSError, match="disk full")):
        project_store.delete_project_by_key(removed["key"])
    assert target.read_bytes() == b"voice data"
    assert project_store.get_project(removed["key"])


def test_crash_before_commit_is_restored_not_purged_on_restart(projects):
    removed, _, target = projects
    with (patch.object(project_store, "_save_index", side_effect=SystemExit("power loss")),
          pytest.raises(SystemExit)):
        project_store.delete_project_by_key(removed["key"])
    assert not target.exists()
    assert list(project_store._deletion_journal_dir().glob("*.json"))
    project_store.recover_project_deletions()
    assert target.read_bytes() == b"voice data"
    assert project_store.get_project(removed["key"])
    assert not list(project_store._deletion_journal_dir().glob("*.json"))


def test_locked_purge_is_journalled_and_finishes_on_restart(projects):
    removed, keep, _ = projects
    with (patch.object(project_store, "_remove_project_root", side_effect=OSError("locked")),
          pytest.raises(OSError, match="locked")):
        project_store.delete_project_by_key(removed["key"])
    assert not project_store.get_project(removed["key"])
    journal = next(project_store._deletion_journal_dir().glob("*.json"))
    receipt = json.loads(journal.read_text())
    assert Path(receipt["retired_root"]).is_dir()
    project_store.recover_project_deletions()
    assert not Path(receipt["retired_root"]).exists()
    assert not journal.exists()
    assert project_store.get_project(keep["key"])


def test_replaced_cleanup_target_is_never_deleted(projects):
    removed, _, _ = projects
    with (patch.object(project_store, "_remove_project_root", side_effect=OSError("locked")),
          pytest.raises(OSError)):
        project_store.delete_project_by_key(removed["key"])
    journal = next(project_store._deletion_journal_dir().glob("*.json"))
    receipt = json.loads(journal.read_text())
    target = Path(receipt["retired_root"])
    saved = target.with_name("saved-original")
    target.rename(saved)
    target.mkdir()
    (target / "keep").write_bytes(b"unrelated replacement")
    project_store.recover_project_deletions()
    assert (target / "keep").read_bytes() == b"unrelated replacement"
    assert journal.exists() and saved.is_dir()


def test_safe_tree_checks_ancestors_per_directory_not_once_for_every_file(tmp_path):
    folder = tmp_path / "cache/a/b/c"
    folder.mkdir(parents=True)
    for index in range(100):
        (folder / f"voice-{index}.wav").write_bytes(b"voice")
    from haizflow.core import storage_ownership
    with patch.object(storage_ownership, "owned_path", wraps=storage_ownership.owned_path) as ownership:
        safe_tree(tmp_path)
    assert ownership.call_count == 5  # Root/cache/a/b/c, independent of file count.


def test_safe_tree_never_follows_child_symlink(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep").write_bytes(b"keep")
    root = tmp_path / "owned"
    root.mkdir()
    try:
        (root / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Windows symlink privilege unavailable")
    with pytest.raises(ValueError, match="reparse|symlink"):
        safe_tree(root)
    assert (outside / "keep").read_bytes() == b"keep"


def test_safe_tree_blocks_windows_reparse_attribute_without_following_it(tmp_path):
    entry = SimpleNamespace(name="junction", path=str(tmp_path / "junction"),
        stat=lambda **_kwargs: SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=1024))
    iterator = MagicMock()
    iterator.__enter__.return_value = [entry]
    with (patch("haizflow.core.storage_ownership.os.scandir", return_value=iterator),
          pytest.raises(ValueError, match="reparse")):
        safe_tree(tmp_path)

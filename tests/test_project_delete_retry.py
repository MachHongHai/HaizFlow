from unittest.mock import patch

import pytest

from haizflow.services.project_store import _force_remove_readonly, _remove_project_root


def test_locked_project_folder_is_not_silently_treated_as_deleted(tmp_path):
    root = tmp_path / "owned-project"
    root.mkdir()
    with patch("haizflow.services.project_store.shutil.rmtree"), pytest.raises(RuntimeError):
        _remove_project_root(str(root), attempts=1, delay_seconds=0)
    assert root.exists()


def test_readonly_retry_propagates_windows_lock(tmp_path):
    file = tmp_path / "locked"
    file.write_bytes(b"keep")
    def remove(_path):
        raise PermissionError("locked")
    with pytest.raises(PermissionError):
        _force_remove_readonly(remove, str(file), None)

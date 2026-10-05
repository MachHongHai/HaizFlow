import errno
import json
import os
import threading
from unittest.mock import patch

import pytest

from haizflow.utils import atomic_file
from haizflow.services import video_store


def test_metadata_publish_retries_reader_lock_without_exposing_partial_json(tmp_path):
    target = tmp_path / "video.json"
    target.write_text('{"old": true}', encoding="utf-8")
    original = os.replace
    failures = []

    def replace(source, destination):
        if len(failures) < 2:
            failures.append(True)
            assert json.loads(target.read_text()) == {"old": True}
            raise PermissionError(5, "Access is denied")
        original(source, destination)

    with patch.object(atomic_file.os, "replace", side_effect=replace), patch.object(atomic_file.time, "sleep"):
        video_store._write_json_atomic(str(target), {"new": "Tiếng Việt"})
    assert json.loads(target.read_text(encoding="utf-8")) == {"new": "Tiếng Việt"}
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("error, attempts", [(PermissionError(5, "Denied"), 8), (OSError(errno.ENOSPC, "Full"), 1)])
def test_permanent_failure_preserves_old_file_and_cleans_staging(tmp_path, error, attempts):
    target = tmp_path / "video.json"
    target.write_text('{"old": true}')
    with patch.object(atomic_file.os, "replace", side_effect=error) as replace, \
         patch.object(atomic_file.time, "sleep"):
        with pytest.raises(OSError):
            atomic_file.atomic_json(target, {"new": True})
    assert replace.call_count == attempts
    assert json.loads(target.read_text()) == {"old": True}
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.skipif(os.name != "nt", reason="Windows sharing-mode regression")
def test_native_windows_open_reader_without_delete_sharing(tmp_path):
    import ctypes
    from ctypes import wintypes

    target = tmp_path / "video.json"
    target.write_text('{"old": true}')
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                  wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(target), 0x80000000, 3, None, 3, 0x80, None)
    assert handle != wintypes.HANDLE(-1).value
    release = threading.Timer(0.15, lambda: kernel.CloseHandle(handle))
    release.start()
    try:
        atomic_file.atomic_json(target, {"new": True})
    finally:
        release.join()
    assert json.loads(target.read_text()) == {"new": True}

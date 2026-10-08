"""Windows IPC sharing conflicts must not corrupt update state."""
import os
import threading
from unittest.mock import patch

import pytest

from haizflow.update.filesystem import UpdateError, atomic_json, read_json


def windows_error(code):
    error = PermissionError("Windows file lock")
    error.winerror = code
    return error


@pytest.mark.parametrize("code", [5, 32, 33])
def test_temporary_windows_lock_retries_same_file_and_preserves_state(tmp_path, code):
    import os
    path = tmp_path / "attempt.status.json"
    atomic_json(path, {"state": "downloading"})
    real_replace = os.replace
    calls = []

    def replace(source, target):
        calls.append(source)
        assert read_json(path) == {"state": "downloading"}
        if len(calls) < 3:
            raise windows_error(code)
        real_replace(source, target)

    with (patch("haizflow.update.filesystem.os.replace", side_effect=replace),
          patch("haizflow.update.filesystem.time.sleep") as sleep):
        atomic_json(path, {"state": "ready"})
        assert sleep.call_count == 2
    assert len(set(calls)) == 1
    assert read_json(path) == {"state": "ready"}
    assert not list(tmp_path.glob("*.tmp"))


def test_persistent_windows_lock_is_bounded_and_leaves_old_state(tmp_path):
    path = tmp_path / "attempt.status.json"
    atomic_json(path, {"state": "downloading"})
    with (patch("haizflow.update.filesystem.os.replace", side_effect=windows_error(5)) as replace,
          patch("haizflow.update.filesystem.time.sleep") as sleep):
        with pytest.raises(UpdateError, match="Windows"):
            atomic_json(path, {"state": "ready"})
        assert replace.call_count == 7
        assert sleep.call_count == 6
    assert read_json(path) == {"state": "downloading"}
    assert not list(tmp_path.glob("*.tmp"))


def test_other_write_errors_are_not_retried(tmp_path):
    with (patch("haizflow.update.filesystem.os.replace", side_effect=OSError("Disk full")) as replace,
          patch("haizflow.update.filesystem.time.sleep") as sleep):
        with pytest.raises(OSError, match="Disk full"):
            atomic_json(tmp_path / "status.json", {})
        replace.assert_called_once()
        sleep.assert_not_called()
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.skipif(os.name != "nt", reason="Windows file sharing semantics")
def test_actual_windows_reader_lock_recovers_after_reader_closes(tmp_path):
    import ctypes
    from ctypes import wintypes

    path = tmp_path / "attempt.status.json"
    atomic_json(path, {"state": "downloading"})
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    # Share read/write, but deliberately not DELETE: replacement must fail
    # while a reader owns this handle, exactly like Windows IPC polling.
    handle = kernel.CreateFileW(str(path), 0x80000000, 3, None, 3, 0x80, None)
    assert handle != ctypes.c_void_p(-1).value
    closed = threading.Event()
    timer = None
    errors = []
    real_replace = os.replace

    def close_reader():
        kernel.CloseHandle(handle)
        closed.set()

    def replace(source, destination):
        nonlocal timer
        try:
            return real_replace(source, destination)
        except OSError as exc:
            errors.append(exc.winerror)
            if timer is None:
                timer = threading.Timer(0.08, close_reader)
                timer.start()
            raise

    try:
        with patch("haizflow.update.filesystem.os.replace", side_effect=replace):
            atomic_json(path, {"state": "ready"})
        assert errors and set(errors) <= {5, 32, 33}
        assert read_json(path) == {"state": "ready"}
        assert not list(tmp_path.glob("*.tmp"))
    finally:
        if timer is not None:
            timer.join(timeout=2)
        if not closed.is_set():
            close_reader()

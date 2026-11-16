"""The isolated picker must render natively at high monitor scaling."""
import ctypes
import json
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from haizflow.desktop import native_file_picker
from haizflow.desktop import windows_file_dialog as dialog


def test_dpi_context_precedes_com_and_covers_all_picker_modes():
    events = []

    @contextmanager
    def dpi():
        events.append("dpi-on")
        try:
            yield
        finally:
            events.append("dpi-restored")

    def show(request):
        assert events[-1] == "dpi-on"
        events.append(request["kind"])
        return {"paths": [], "selected_filter": "", "error": ""}

    with patch.object(dialog, "_per_monitor_dpi", dpi), patch.object(dialog, "_show_dialog", side_effect=show):
        for kind in ("open", "multiple", "folder", "save"):
            assert dialog.show({"kind": kind})["paths"] == []
    assert events == [value for kind in ("open", "multiple", "folder", "save")
                      for value in ("dpi-on", kind, "dpi-restored")]


@pytest.mark.parametrize("manifest_set", [False, True])
@pytest.mark.parametrize("failure", [False, True])
def test_frozen_manifest_is_respected_and_thread_context_is_restored(manifest_set, failure):
    api = Mock()
    api.SetProcessDpiAwarenessContext.return_value = not manifest_set
    api.SetThreadDpiAwarenessContext.return_value = 1234
    with patch.object(ctypes, "WinDLL", return_value=api, create=True), \
            patch.object(ctypes, "get_last_error", return_value=5, create=True):
        try:
            with dialog._per_monitor_dpi():
                assert api.SetProcessDpiAwarenessContext.call_args.args[0].value == ctypes.c_void_p(-4).value
                if failure:
                    raise RuntimeError("picker failed")
        except RuntimeError:
            assert failure
    assert api.SetThreadDpiAwarenessContext.call_args_list[0].args[0].value == ctypes.c_void_p(-4).value
    assert api.SetThreadDpiAwarenessContext.call_args_list[1].args == (1234,)


@pytest.mark.skipif(os.name != "nt", reason="Windows DPI API")
def test_actual_isolated_python_helper_becomes_per_monitor_v2_before_ui():
    # Same interpreter/startup flags and real Shell profile as production.
    argv = native_file_picker.command(Path("unused.json"))
    source_root = str(Path(native_file_picker.__file__).resolve().parents[2])
    probe = f"""
import sys, ctypes, json
sys.path.insert(0, {source_root!r})
from haizflow.desktop.windows_file_dialog import _per_monitor_dpi
u = ctypes.WinDLL('user32', use_last_error=True)
u.GetThreadDpiAwarenessContext.restype = ctypes.c_void_p
u.GetAwarenessFromDpiAwarenessContext.argtypes = [ctypes.c_void_p]
u.AreDpiAwarenessContextsEqual.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
with _per_monitor_dpi():
    current = u.GetThreadDpiAwarenessContext()
    print(json.dumps({{'awareness': u.GetAwarenessFromDpiAwarenessContext(current),
        'v2': bool(u.AreDpiAwarenessContextsEqual(current, ctypes.c_void_p(-4))),
        'site_loaded': 'site' in sys.modules}}))
"""
    process = subprocess.run([*argv[:3], "-c", probe], env=native_file_picker.shell_environment(),
                             capture_output=True, text=True, timeout=15, check=True)
    assert json.loads(process.stdout) == {"awareness": 2, "v2": True, "site_loaded": False}

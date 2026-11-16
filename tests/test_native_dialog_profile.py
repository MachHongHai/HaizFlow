"""All pages use fresh Windows pickers without host profile races."""
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from haizflow.desktop import localization, native_file_picker


@pytest.mark.parametrize("method,kind,result,expected", [
    ("getOpenFileName", "open", (["a.mp4"], "MP4"), ("a.mp4", "MP4")),
    ("getOpenFileNames", "multiple", (["a.mp4", "b.mp4"], "MP4"), (["a.mp4", "b.mp4"], "MP4")),
    ("getSaveFileName", "save", (["out.mp4"], "MP4"), ("out.mp4", "MP4")),
    ("getExistingDirectory", "folder", (["folder"], ""), "folder"),
])
def test_every_picker_uses_isolated_service_without_mutating_environment(method, kind, result, expected):
    before = dict(os.environ)
    with patch.object(native_file_picker, "pick", return_value=result) as picker:
        assert getattr(localization.QFileDialog, method)(None, "Media", "C:/Users/Example") == expected
    assert picker.call_args.args[0] == kind
    assert dict(os.environ) == before


@pytest.mark.parametrize("method,empty", [("getOpenFileName", ("", "")),
    ("getOpenFileNames", ([], "")), ("getSaveFileName", ("", "")), ("getExistingDirectory", "")])
def test_cancellation_never_opens_second_picker(method, empty):
    with patch.object(native_file_picker, "pick", return_value=([], "")) as picker, \
            patch.object(localization.QtFileDialog, method) as fallback:
        assert getattr(localization.QFileDialog, method)(None, "Choose", "") == empty
        picker.assert_called_once()
        fallback.assert_not_called()


def test_helper_failure_reports_error_not_polluted_fallback(tmp_path):
    before = dict(os.environ)
    with patch.object(native_file_picker, "pick", side_effect=OSError("Shell failed")), \
            patch.object(localization.QMessageBox, "warning") as warning, \
            patch.object(localization.QtFileDialog, "getExistingDirectory") as fallback:
        assert localization.QFileDialog.getExistingDirectory(None, "Export", "") == ""
        warning.assert_called_once()
        fallback.assert_not_called()
    assert dict(os.environ) == before
    # FailedToStart may be emitted inside start(), before the nested loop.
    with patch("PySide6.QtCore.QProcess") as process_type, \
            patch("PySide6.QtCore.QEventLoop") as loop_type, \
            patch("PySide6.QtGui.QGuiApplication.instance", return_value=None), \
            patch.object(native_file_picker, "shell_environment", return_value={"USERPROFILE":str(tmp_path)}):
        process_type.NotRunning = 0
        process_type.NormalExit = 0
        process_type.nullDevice.return_value = os.devnull
        process = process_type.return_value
        process.state.return_value = 0
        process.exitStatus.return_value = 0
        process.exitCode.return_value = 1
        process.errorString.return_value = "missing executable"
        process.readAllStandardError.return_value = b"fixture error"
        process.start.side_effect = loop_type.return_value.quit
        with pytest.raises(OSError, match="could not start"):
            native_file_picker.pick("folder", "Choose", tmp_path)
        loop_type.return_value.exec.assert_not_called()


@pytest.mark.skipif(os.name != "nt", reason="Windows user token API")
def test_token_profile_ignores_every_portable_environment_variable(tmp_path):
    native = native_file_picker.shell_environment()
    portable = {key: str(tmp_path / key) for key in (*native_file_picker.PROFILE_KEYS, "HOME")}
    with patch.dict(os.environ, portable):
        clean = native_file_picker.shell_environment()
        for key in native_file_picker.PROFILE_KEYS:
            assert clean[key] == native[key]
        assert clean["HOME"] == native["USERPROFILE"]
        assert all(os.environ[key] == value for key, value in portable.items())


def test_frozen_picker_reuses_core_not_launcher(monkeypatch, tmp_path):
    monkeypatch.setattr(native_file_picker.sys, "frozen", True, raising=False)
    monkeypatch.setattr(native_file_picker.sys, "executable", "D:/App/versions/1.0.5/HaizFlowCore.exe")
    assert native_file_picker.command(tmp_path / "request.json") == [
        "D:/App/versions/1.0.5/HaizFlowCore.exe", "--native-file-dialog", str(tmp_path / "request.json")]


def test_dev_picker_skips_profile_redirecting_python_startup(monkeypatch, tmp_path):
    monkeypatch.setattr(native_file_picker.sys, "frozen", False, raising=False)
    request = tmp_path / "request.json"
    argv = native_file_picker.command(request)
    assert argv[1:3] == ["-I", "-S"]
    assert Path(argv[3]) == Path(native_file_picker.__file__).resolve()
    assert argv[4] == str(request)
    startup = tmp_path / "startup"
    startup.mkdir()
    (startup / "sitecustomize.py").write_text(
        "import os\nos.environ['APPDATA']='wrong-portable-profile'\n", encoding="utf-8")
    environment = dict(os.environ, APPDATA="real-shell-profile", PYTHONPATH=str(startup))
    probe = "import os, json, sys; print(json.dumps([os.environ['APPDATA'], 'site' in sys.modules]))"
    standard = subprocess.run([sys.executable, "-c", probe], env=environment,
                              capture_output=True, text=True, timeout=15, check=True)
    assert json.loads(standard.stdout) == ["wrong-portable-profile", True]
    isolated = subprocess.run([*argv[:3], "-c", probe], env=environment,
                              capture_output=True, text=True, timeout=15, check=True)
    assert json.loads(isolated.stdout) == ["real-shell-profile", False]


def test_isolated_script_dispatch_needs_no_qt_or_editable_site_hook(tmp_path):
    request, response = tmp_path / "request.json", tmp_path / "response.json"
    request.write_text(json.dumps(dict(kind="unsupported", result=str(response))), encoding="utf-8")
    result = subprocess.run(native_file_picker.command(request), capture_output=True,
                            text=True, timeout=15, check=True)
    assert not result.stderr
    assert json.loads(response.read_text("utf-8"))["error"] == "Unsupported native picker operation"


def test_helper_dispatch_precedes_profile_and_splash():
    entry = (Path(__file__).parents[1] / "haizflow_desktop.py").read_text("utf-8")
    assert entry.index('sys.argv[1] == "--native-file-dialog"') < entry.index("import haizflow.config")
    source = inspect.getsource(native_file_picker.main)
    assert "windows_file_dialog import show" in source
    assert "QWidget" not in source and "QApplication" not in source
    from haizflow.desktop import windows_file_dialog
    native = inspect.getsource(windows_file_dialog._show_dialog)
    assert "CoCreateInstance" in native and "SHGetKnownFolderPath" in native
    assert "_call(dialog, 21," not in native  # No application-specific places group.
    assert "_call(dialog, 24," not in native  # Keep ordinary Windows dialog state.

"""All pages use fresh Windows pickers without host profile races."""
import inspect
import os
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


def test_helper_dispatch_precedes_profile_and_splash():
    entry = (Path(__file__).parents[1] / "haizflow_desktop.py").read_text("utf-8")
    assert entry.index('sys.argv[1] == "--native-file-dialog"') < entry.index("import haizflow.config")
    source = inspect.getsource(native_file_picker.main)
    assert "QFileDialog.getExistingDirectory" in source
    assert "QFileDialog.getOpenFileNames" in source
    assert "QFileDialog.getSaveFileName" in source
    assert "AddPlace" not in source
    assert "DontUseNativeDialog" in source

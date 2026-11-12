"""Use Explorer's standard navigation without application-specific places."""

import ast
import inspect
import os
from unittest.mock import patch

import pytest

from haizflow.desktop import localization


@pytest.mark.parametrize("method,qt_method,args,result", [
    ("getOpenFileName", "getOpenFileName", ("MP4 (*.mp4)",), ("video.mp4", "")),
    ("getOpenFileNames", "getOpenFileNames", ("MP4 (*.mp4)",), (["a.mp4", "b.mp4"], "")),
    ("getSaveFileName", "getSaveFileName", ("MP4 (*.mp4)",), ("export.mp4", "")),
    ("getExistingDirectory", "getExistingDirectory", (), "folder"),
])
def test_every_picker_exposes_real_profile_and_restores_portable_profile(tmp_path, method, qt_method, args, result):
    portable = tmp_path / "portable"
    native = tmp_path / "user"
    portable.mkdir()
    native.mkdir()
    before = dict(USERPROFILE=str(portable), HOMEDRIVE="Z:", HOMEPATH="\\portable")

    def pick(*_args):
        assert os.environ["USERPROFILE"] == str(native)
        return result

    with (
        patch.dict(os.environ, before),
        patch.object(localization, "NATIVE_WINDOWS_USERPROFILE", str(native)),
        patch.object(localization, "_native_windows_folder_dialog", return_value=(False, "")),
        patch.object(localization.QtFileDialog, qt_method, side_effect=pick) as picker,
    ):
        assert getattr(localization.QFileDialog, method)(None, "Media", str(tmp_path), *args) == result
        assert {key: os.environ[key] for key in before} == before
        picker.assert_called_once()


@pytest.mark.parametrize("result", ["", "selected"])
def test_native_success_and_cancel_do_not_open_second_dialog_and_restore_profile(tmp_path, result):
    native = tmp_path / "user"
    native.mkdir()
    before = dict(USERPROFILE="portable", HOMEDRIVE="Z:", HOMEPATH="\\portable")

    def pick(*_args):
        assert os.environ["USERPROFILE"] == str(native)
        return True, result

    with (
        patch.dict(os.environ, before),
        patch.object(localization, "NATIVE_WINDOWS_USERPROFILE", str(native)),
        patch.object(localization, "_native_windows_folder_dialog", side_effect=pick),
        patch.object(localization.QtFileDialog, "getExistingDirectory") as fallback,
    ):
        assert localization.QFileDialog.getExistingDirectory(None, "Export", str(tmp_path)) == result
        assert {key: os.environ[key] for key in before} == before
        fallback.assert_not_called()


def test_profile_is_restored_even_when_picker_raises(tmp_path):
    native = tmp_path / "user"
    native.mkdir()
    before = dict(USERPROFILE="portable", HOMEDRIVE="Z:", HOMEPATH="\\portable")
    with (
        patch.dict(os.environ, before),
        patch.object(localization, "NATIVE_WINDOWS_USERPROFILE", str(native)),
        patch.object(localization, "_native_windows_folder_dialog", side_effect=RuntimeError("Shell failed")),
    ):
        with pytest.raises(RuntimeError, match="Shell failed"):
            localization.QFileDialog.getExistingDirectory(None, "Export", str(tmp_path))
        assert {key: os.environ[key] for key in before} == before


def test_native_dialog_never_adds_application_specific_places():
    # IFileDialog::AddPlace is vtable slot 21. Adding shortcuts creates a
    # separate application group ("Python" when running the development app).
    tree = ast.parse(inspect.getsource(localization._native_windows_folder_dialog))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "com_method":
            assert not (len(node.args) > 1 and isinstance(node.args[1], ast.Constant) and node.args[1].value == 21)

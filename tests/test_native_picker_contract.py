"""Serialize every picker mode to one Windows Common Item Dialog backend."""
import json
from unittest.mock import patch

import pytest

from haizflow.desktop import native_file_picker, windows_file_dialog


@pytest.mark.parametrize("kind,paths", [
    ("folder", ["D:/Dữ liệu/한국어/日本語"]),
    ("open", ["D:/日本語.mp4"]),
    ("multiple", ["D:/한국어.mp4", "D:/日本語.mp4"]),
    ("save", ["//server/share/Video tiếng Việt.mp4"]),
])
def test_helper_preserves_unicode_unc_paths_filters_and_owner(tmp_path, kind, paths):
    request, result = tmp_path / "request.json", tmp_path / "result.json"
    payload = dict(kind=kind, caption="Kiểm thử", directory="D:/Nguồn/tệp.mp4", name_filter="Video (*.mp4)",
                   selected_filter="Video (*.mp4)", options=4, owner=1234, result=str(result))
    request.write_text(json.dumps(payload), encoding="utf-8")
    response = dict(paths=paths, selected_filter="Video (*.mp4)", error="")
    with patch.object(windows_file_dialog, "show", return_value=response) as dialog:
        assert native_file_picker.main(str(request)) == 0
    assert dialog.call_args.args[0] == payload
    assert json.loads(result.read_text("utf-8")) == response


@pytest.mark.parametrize("kind", ["open", "multiple", "save", "folder"])
def test_cancel_and_error_are_results_not_window_shutdowns(tmp_path, kind):
    request, result = tmp_path / "request.json", tmp_path / "result.json"
    request.write_text(json.dumps(dict(kind=kind, result=str(result))), encoding="utf-8")
    with patch.object(windows_file_dialog, "show", return_value=dict(paths=[], selected_filter="", error="")):
        assert native_file_picker.main(str(request)) == 0
    assert json.loads(result.read_text("utf-8"))["paths"] == []
    with patch.object(windows_file_dialog, "show", side_effect=OSError("native failure")):
        assert native_file_picker.main(str(request)) == 0
    assert json.loads(result.read_text("utf-8"))["error"] == "native failure"


def test_standard_options_preserve_overwrite_and_folder_multi_modes():
    assert windows_file_dialog.dialog_options("folder") & 0x20
    assert windows_file_dialog.dialog_options("multiple") & 0x200
    assert windows_file_dialog.dialog_options("open") & 0x1000
    assert windows_file_dialog.dialog_options("save") & 2
    assert not windows_file_dialog.dialog_options("save", 4) & 2
    for kind in ("open", "multiple", "save", "folder"):
        assert windows_file_dialog.dialog_options(kind) & 0x40


def test_file_filters_support_unicode_and_multiple_extensions():
    assert windows_file_dialog.name_filters("Video Việt (*.mp4 *.mkv);;Tất cả (*)") == [
        ("Video Việt (*.mp4 *.mkv)", "Video Việt", "*.mp4;*.mkv"), ("Tất cả (*)", "Tất cả", "*")]

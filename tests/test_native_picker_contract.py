"""Exercise the helper's real serialization and Qt API/options for every mode."""
import json
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog

from haizflow.desktop import native_file_picker

_APP = None


@pytest.mark.parametrize("kind,method,answer", [
    ("folder", "getExistingDirectory", "D:/Dữ liệu/한국어/日本語"),
    ("open", "getOpenFileName", ("D:/日本語.mp4", "Video (*.mp4)")),
    ("multiple", "getOpenFileNames", (["D:/한국어.mp4", "D:/日本語.mp4"], "Video (*.mp4)")),
    ("save", "getSaveFileName", ("//server/share/Video tiếng Việt.mp4", "Video (*.mp4)")),
])
def test_helper_preserves_unicode_unc_paths_filters_and_native_options(tmp_path, kind, method, answer):
    global _APP
    _APP = QApplication.instance() or QApplication([])
    request, result = tmp_path / "request.json", tmp_path / "result.json"
    options = QFileDialog.Option.DontUseNativeDialog | QFileDialog.Option.DontConfirmOverwrite
    request.write_text(json.dumps(dict(kind=kind, caption="Kiểm thử", directory="D:/Nguồn/tệp.mp4",
        name_filter="Video (*.mp4)", selected_filter="Video (*.mp4)", options=options.value,
        owner=0, result=str(result))), encoding="utf-8")
    with patch.object(QFileDialog, method, return_value=answer) as dialog:
        assert native_file_picker.main(str(request)) == 0
    assert dialog.call_args.args[2] == "D:/Nguồn/tệp.mp4"
    assert not (dialog.call_args.args[-1] & QFileDialog.Option.DontUseNativeDialog)
    assert dialog.call_args.args[-1] & QFileDialog.Option.DontConfirmOverwrite
    payload = json.loads(result.read_text("utf-8"))
    assert not payload["error"]
    paths = answer if kind == "folder" else answer[0]
    assert payload["paths"] == (paths if isinstance(paths, list) else [paths])

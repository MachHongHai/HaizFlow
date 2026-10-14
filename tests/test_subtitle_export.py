from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import srt

from hflow.desktop.project_commands_controller import ProjectCommandsController
from hflow.schemas.editor import EditorClip, EditorDocument, EditorTrack
from hflow.services import subtitle_export


def document():
    return EditorDocument(video_id="srt-project", tracks=[
        EditorTrack(track_id="subtitles", kind="subtitle", name="Phụ đề"),
        EditorTrack(track_id="voice", kind="voice", name="Giọng đọc"),
    ], clips=[
        EditorClip(clip_id="late", track_id="subtitles", kind="subtitle", segment_id="s2",
                   name="Tiếng Việt và 中文\nDòng thứ hai", start_ms=1801234, duration_ms=2345),
        EditorClip(clip_id="early", track_id="subtitles", kind="subtitle", segment_id="s1",
                   name="Hello", start_ms=11500, duration_ms=1750),
        EditorClip(clip_id="voice", track_id="voice", kind="voice", name="Not a caption",
                   start_ms=0, duration_ms=200),
    ])


@pytest.fixture
def external_storage():
    with patch.object(subtitle_export.project_store, "list_projects", return_value=[]):
        yield


def test_export_preserves_edited_timeline_unicode_and_multiline_without_voice_probing():
    doc = document()
    before = doc.model_dump()
    cues = list(srt.parse(subtitle_export.compose_document_srt(doc)))
    assert [cue.index for cue in cues] == [1, 2]
    assert cues[0].start.total_seconds() == 11.5
    assert cues[0].end.total_seconds() == 13.25
    assert cues[1].start.total_seconds() == 1801.234
    assert cues[1].content == "Tiếng Việt và 中文\nDòng thứ hai"
    assert doc.model_dump() == before


@pytest.mark.parametrize("missing", ["none", "empty", "disabled", "hidden", "zero", "blank"])
def test_no_usable_subtitles_returns_empty(missing):
    doc = document()
    doc.clips = [doc.clips[0]]
    if missing == "none":
        doc = None
    elif missing == "empty":
        doc.clips.clear()
    elif missing == "disabled":
        doc.clips[0].enabled = False
    elif missing == "hidden":
        doc.tracks[0].visible = False
    elif missing == "zero":
        doc.clips[0].duration_ms = 0
    elif missing == "blank":
        doc.clips[0].name = " \n "
    assert subtitle_export.compose_document_srt(doc) == ""


def test_atomic_export_appends_extension_and_round_trips_utf8(tmp_path, external_storage):
    content = subtitle_export.compose_document_srt(document())
    output = subtitle_export.save_srt(content, tmp_path / "result")
    assert output == tmp_path / "result.srt"
    assert len(list(srt.parse(output.read_text(encoding="utf-8")))) == 2
    assert b"\r\n" in output.read_bytes()
    assert list(tmp_path.iterdir()) == [output]


def test_failed_write_preserves_existing_srt_and_cleans_temporary(tmp_path, external_storage):
    target = tmp_path / "result.srt"
    target.write_bytes(b"previous result")
    with patch.object(subtitle_export, "replace_with_retry", side_effect=PermissionError("locked")):
        with pytest.raises(PermissionError):
            subtitle_export.save_srt(subtitle_export.compose_document_srt(document()), target)
    assert target.read_bytes() == b"previous result"
    assert list(tmp_path.iterdir()) == [target]


def test_empty_export_never_creates_a_file(tmp_path, external_storage):
    with pytest.raises(ValueError, match="No subtitles"):
        subtitle_export.save_srt("", tmp_path / "empty.srt")
    assert not list(tmp_path.iterdir())


def test_project_cache_destination_is_rejected(tmp_path):
    with (patch.object(subtitle_export.project_store, "list_projects", return_value=[{"key": "p"}]),
          patch.object(subtitle_export.project_store, "project_root_for_key", return_value=str(tmp_path))):
        with pytest.raises(ValueError, match="outside managed"):
            subtitle_export.save_srt("valid content", tmp_path / "subtitles.srt")
    assert not list(tmp_path.iterdir())


def host_for(doc):
    return SimpleNamespace(_settings_language="vi", _selected_video=lambda: SimpleNamespace(
        video_id="srt-project", project_name="Dự án", project_key="", original_filename="clip.mp4"),
        _manual_editor_document=SimpleNamespace(video_id="srt-project", document_object=doc),
        _manual_subtitles=SimpleNamespace(video_id="srt-project", segments=[], _states={}),
        appAlertRequested=SimpleNamespace(emit=Mock()))


def test_empty_workspace_is_blocked_with_warning_before_save_picker():
    host = host_for(None)
    with patch("hflow.desktop.project_commands_controller.QFileDialog.getSaveFileName") as picker:
        assert not ProjectCommandsController(host).export_selected_srt()
        picker.assert_not_called()
    assert host.appAlertRequested.emit.call_args.args[0] == "Chưa có phụ đề để xuất"
    assert host.appAlertRequested.emit.call_args.args[2] == "warning"


@pytest.mark.parametrize("busy_field", ["isProcessing", "videoExportBusy", "mediaImportBusy", "queue"])
def test_busy_export_is_blocked_before_reading_document_or_opening_picker(busy_field):
    host = host_for(document())
    if busy_field == "queue":
        host._processing_queue = SimpleNamespace(has_work=True)
    else:
        setattr(host, busy_field, True)
    host._selected_video = Mock(side_effect=AssertionError("Do not read a busy editor"))
    with patch("hflow.desktop.project_commands_controller.QFileDialog.getSaveFileName") as picker:
        assert not ProjectCommandsController(host).export_selected_srt()
    picker.assert_not_called()
    assert host.appAlertRequested.emit.call_args.args[0] == "Đang xử lý"


def test_export_uses_pending_text_and_current_timing_without_project_mutation(tmp_path, external_storage):
    doc = document()
    before = deepcopy(doc.model_dump())
    host = host_for(doc)
    host._manual_subtitles.segments = [{"segment_id": "s1", "text": "Edited now"}]
    host._manual_subtitles._states = {"s1": "saving"}
    target = tmp_path / "result.srt"
    with (patch("hflow.desktop.project_commands_controller.QFileDialog.getSaveFileName",
                return_value=(str(target), "")),
          patch("hflow.services.desktop_settings.load_settings", return_value={})):
        assert ProjectCommandsController(host).export_selected_srt()
    cue = next(srt.parse(target.read_text(encoding="utf-8")))
    assert cue.content == "Edited now"
    assert cue.start.total_seconds() == 11.5
    assert doc.model_dump() == before
    assert host.appAlertRequested.emit.call_args.args[0] == "Đã xuất SRT"


def test_picker_cancel_does_not_write_or_show_success():
    host = host_for(document())
    with (patch("hflow.desktop.project_commands_controller.QFileDialog.getSaveFileName", return_value=("", "")),
          patch.object(subtitle_export, "save_srt") as save,
          patch("hflow.services.desktop_settings.load_settings", return_value={})):
        assert not ProjectCommandsController(host).export_selected_srt()
        save.assert_not_called()
    host.appAlertRequested.emit.assert_not_called()


def test_rejecting_overwrite_preserves_destination(tmp_path, external_storage):
    host = host_for(document())
    target = tmp_path / "result.srt"
    target.write_bytes(b"previous result")
    with (patch("hflow.desktop.project_commands_controller.QFileDialog.getSaveFileName", return_value=(str(target), "")),
          patch("hflow.desktop.project_commands_controller.QMessageBox.question", return_value=65536),
          patch("hflow.services.desktop_settings.load_settings", return_value={})):
        assert not ProjectCommandsController(host).export_selected_srt()
    assert target.read_bytes() == b"previous result"


def test_two_srt_outputs_keep_original_and_result_separate(tmp_path, external_storage):
    source = subtitle_export.compose_document_srt(document(), {"s1": "Original source"})
    result = subtitle_export.compose_document_srt(document(), {"s1": "Bản dịch"})
    paths = subtitle_export.save_srt_pair(source, result, tmp_path / "movie.srt")
    assert [path.name for path in paths] == ["movie.source.srt", "movie.result.srt"]
    assert next(srt.parse(paths[0].read_text(encoding="utf-8"))).content == "Original source"
    assert next(srt.parse(paths[1].read_text(encoding="utf-8"))).content == "Bản dịch"
    assert sorted(tmp_path.iterdir()) == sorted(paths)


@pytest.mark.parametrize("existing", [True, False])
def test_pair_second_publication_failure_rolls_back_first_and_leaves_no_temps(tmp_path, external_storage, monkeypatch, existing):
    source = tmp_path / "movie.source.srt"
    result = tmp_path / "movie.result.srt"
    if existing:
        source.write_bytes(b"old source")
        result.write_bytes(b"old result")
    replace = subtitle_export.replace_with_retry
    calls = 0

    def fail_second(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise PermissionError("locked target")
        return replace(*args)

    monkeypatch.setattr(subtitle_export, "replace_with_retry", fail_second)
    with pytest.raises(PermissionError):
        subtitle_export.save_srt_pair("source captions", "result captions", tmp_path / "movie.srt")
    if existing:
        assert source.read_bytes() == b"old source"
        assert result.read_bytes() == b"old result"
        assert sorted(tmp_path.iterdir()) == sorted([source, result])
    else:
        assert not list(tmp_path.iterdir())


def test_original_export_no_captions_blocks_before_picker():
    host = host_for(document())
    with patch("hflow.desktop.project_commands_controller.QFileDialog.getSaveFileName") as picker:
        assert not ProjectCommandsController(host).export_selected_srt("source")
        picker.assert_not_called()


def test_export_pair_checks_overwrite_on_both_output_names(tmp_path, external_storage):
    host = host_for(document())
    target = tmp_path / "movie.srt"
    source = tmp_path / "movie.source.srt"
    source.write_bytes(b"keep source")
    with (patch("hflow.desktop.project_commands_controller.QFileDialog.getSaveFileName", return_value=(str(target), "")),
          patch.object(subtitle_export, "compose_source_srt", return_value="Original"),
          patch("hflow.desktop.project_commands_controller.QMessageBox.question", return_value=65536),
          patch("hflow.services.desktop_settings.load_settings", return_value={})):
        assert not ProjectCommandsController(host).export_selected_srt("both")
    assert source.read_bytes() == b"keep source"
    assert not (tmp_path / "movie.result.srt").exists()


def test_export_rechecks_busy_after_native_picker(tmp_path, external_storage):
    host = host_for(document())

    def pick(*_args):
        host.isProcessing = True
        return str(tmp_path / "movie.srt"), ""

    with (patch("hflow.desktop.project_commands_controller.QFileDialog.getSaveFileName", side_effect=pick),
          patch("hflow.services.desktop_settings.load_settings", return_value={})):
        assert not ProjectCommandsController(host).export_selected_srt()
    assert not list(tmp_path.iterdir())


def test_workspace_action_is_directly_below_audio_and_does_not_start_a_pipeline_stage():
    workspace = (Path(__file__).parents[1] / "src/hflow/desktop/qml/ManualWorkspace.qml").read_text(encoding="utf-8")
    assert workspace.index('root.toolModel[5], {stageIndex: 5}') < workspace.index('qsTr("Nhập SRT")') < workspace.index('qsTr("Xuất SRT")')
    assert 'srtExportLoader.invoke("openForSelection");\n                return;' in workspace

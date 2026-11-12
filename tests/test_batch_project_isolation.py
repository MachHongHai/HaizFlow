"""Batch scope, cancellation and late preview delivery use captured owners."""

import threading
import time
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QEvent, QObject, QUrl
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest

from haizflow.desktop.project_commands_controller import ProjectCommandsController
from haizflow.desktop.qml_controller import HaizFlowController  # noqa: F401 - register QML facade before Qt engines
from haizflow.desktop.subtitle_overlay_renderer import SubtitleOverlayRenderer
from haizflow.desktop.video_export_controller import VideoExportController
from haizflow.schemas.video import VideoConfig
from haizflow.services import batch_settings, processing_runs, video_store

_APP = None

@pytest.fixture
def app():
    global _APP
    _APP = QGuiApplication.instance() or QGuiApplication([])
    for filename in ("SegUIVar.ttf", "segoeui.ttf", "segmdl2.ttf"):
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + filename)
    return _APP


def export_host():
    host = QObject()
    host._settings_language = "vi"
    host.exportStateChanged = Mock()
    host.batchChanged = Mock()
    host.selectedVideoChanged = Mock()
    host.processingChanged = Mock()
    host.refreshVideos = Mock()
    host.appAlertRequested = Mock()
    host._selected_project_key = "batch"
    host._batch_video_ids = ["first", "second"]
    host._enqueue_videos = Mock(return_value=True)
    host._processing_queue = SimpleNamespace(contains=lambda _: False, token_for=lambda _: None)
    return host


def test_dialog_model_filters_jobs_without_dropping_other_project_work(app):
    host = export_host()
    exporter = VideoExportController(host)
    exporter.timer.stop()
    exporter.jobs = [dict(videoId="first", path="batch.mp4", status="paused", progress=15),
                     dict(videoId="w3", path="w3.mp4", status="rendering", progress=46)]
    try:
        exporter.set_dialog_scope(["w3"])
        exporter.changed()
        assert exporter.dialog_job_model.rowCount() == 1
        assert exporter.dialog_job_model._rows[0]["videoId"] == "w3"
        exporter.jobs[1]["progress"] = 72
        exporter.changed()
        assert exporter.dialog_job_model._rows[0]["progress"] == 72
        assert exporter.jobs[0]["status"] == "paused"
        exporter.set_dialog_scope(["first", "second"])
        assert exporter.dialog_job_model._rows[0]["videoId"] == "first"
    finally:
        exporter.shutdown()


def test_cancel_scope_never_cancels_other_copy_or_render(app):
    host = export_host()
    host._processing_queue.detach_owned = Mock(return_value=(None, []))
    exporter = VideoExportController(host)
    exporter.timer.stop()
    exporter.jobs = [dict(videoId=key, path=key + ".mp4", status="exporting", progress=5)
                     for key in ("first", "w3")]
    exporter._copy_cancels = {key: threading.Event() for key in ("first", "w3")}
    try:
        exporter.cancel_all({"w3"})
        assert not exporter.cancel.is_set()
        assert not exporter._copy_cancels["first"].is_set()
        assert exporter._copy_cancels["w3"].is_set()
        assert not exporter.jobs[0].get("cancelRequested")
    finally:
        exporter.shutdown()


def test_caption_owner_rejects_old_workspace_timer_and_late_raster(app, monkeypatch):
    host = QObject()
    host._selected_video_id = "w3"
    renderer = SubtitleOverlayRenderer(host)
    monkeypatch.setattr(renderer, "configure", Mock())
    try:
        renderer.configureForVideo("w3", "[]", "{}", True, False)
        renderer._frame = {"text": "Only belongs to w3"}
        generation = renderer._generation
        host._selected_video_id = "w4"
        renderer.configureForVideo("w4", "[]", "{}", True, False)
        assert renderer.videoId == "w4" and renderer.frame == {}
        renderer.configure.reset_mock()
        renderer.configureForVideo("w3", '[{"text":"old"}]', "{}", True, False)
        renderer.configure.assert_not_called()
        renderer._accept(("events", generation, "old header", [{"body": "old"}]))
        assert renderer._events == [] and renderer.frame == {}
    finally:
        renderer.close()


def test_batch_preparation_is_async_subset_and_keeps_owner_after_navigation(app, tmp_path, monkeypatch):
    host = export_host()
    video = SimpleNamespace(video_id="second", project_key="batch", project_type="batch",
                            original_filename="second.mp4", status="paused", step="starting", progress=0)
    entered, release = threading.Event(), threading.Event()
    monkeypatch.setattr(video_store, "get_video", lambda key: video if key == "second" else None)
    monkeypatch.setattr(video_store, "validate_video_restart", Mock())
    def restart(key):
        entered.set()
        assert release.wait(3)
    restart_mock = Mock(side_effect=restart)
    monkeypatch.setattr(video_store, "prepare_video_restart", restart_mock)
    monkeypatch.setattr(video_store, "update_video", Mock())
    monkeypatch.setattr(ProjectCommandsController, "_resources_ready_for_videos", lambda *_: True)
    monkeypatch.setattr(processing_runs, "arm_export", lambda _: "run")
    monkeypatch.setattr("haizflow.pipeline.process_registry.prepare_video_resume", Mock())
    exporter = VideoExportController(host)
    exporter.timer.stop()
    try:
        started = time.perf_counter()
        assert exporter.start_batch_to("batch", ["second"], "source", str(tmp_path), background=True)
        assert time.perf_counter() - started < .3
        assert entered.wait(1)
        assert exporter.jobs[0]["status"] == "preparing"
        host._enqueue_videos.assert_not_called()
        host._selected_project_key = "other"
        host._batch_video_ids = ["other-video"]
        release.set()
        exporter._preparation_worker.join(3)
        host._processing_queue.contains = lambda key: key == "second"
        exporter.poll()
        restart_mock.assert_called_once_with("second")
        host._enqueue_videos.assert_called_once_with(["second"])
    finally:
        release.set()
        exporter.shutdown()


def test_batch_scope_defaults_to_unfinished_and_can_select_arbitrary_video(app):
    from pathlib import Path
    qml = Path(__file__).resolve().parents[1] / "src/haizflow/desktop/qml"
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(f'''import QtQuick
import QtQuick.Controls.Basic
import "{qml.as_uri()}"
ApplicationWindow {{ width: 900; height: 700; visible: true
    BatchVideoScope {{ objectName: "scope"; width: 600 }}
}}'''.encode(), QUrl())
    assert component.isReady(), [error.toString() for error in component.errors()]
    window = component.create()
    item = window.findChild(QObject, "scope")
    try:
        item.setProperty("videos", [dict(videoId="done", name="A", status="done"),
                                    dict(videoId="paused", name="B", status="paused")])
        assert item.property("targetIds").toVariant() == ["paused"]
        item.setProperty("scope", "all")
        assert item.property("targetIds").toVariant() == ["done", "paused"]
        item.setProperty("selectedIds", ["done"])
        item.setProperty("scope", "selection")
        assert item.property("targetIds") == ["done"]
    finally:
        window.close()
        window.deleteLater()
        component.deleteLater()
        engine.deleteLater()
        app.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()


def test_apply_all_resynchronizes_selected_editor_before_autosave(monkeypatch):
    config = VideoConfig(project_type="batch", speech_recognition_model="small-cpu", tts_provider="vieneu")
    records = {key: SimpleNamespace(**config.model_dump(), video_id=key, files={}, status="done",
                                   progress=100, step="done", resume_step="", error=None) for key in ("a", "b")}
    for video in records.values():
        video.subtitle_style = config.subtitle_style
    records["b"].watermark_text = "old per-video value"
    records["b"].tts_provider = "omnivoice"
    baseline = batch_settings.values_for(records["a"])
    host = SimpleNamespace(_selected_project_key="batch", _selected_video_id="b", _batch_video_ids=list(records),
        _settings_processing_device="cpu", _settings_owner_video_id="b",
        _processing_queue=SimpleNamespace(contains=lambda _: False),
        _capture_video_asset_snapshot=lambda video, **_: deepcopy(video.__dict__),
        _record_batch_asset_change=Mock(), _show_app_alert=Mock(), refreshVideos=Mock(), batchChanged=Mock())
    host._project_workspace = SimpleNamespace(select_video=Mock())
    commands = ProjectCommandsController(host)
    monkeypatch.setattr(commands, "batch_settings_values", lambda: deepcopy(baseline))
    monkeypatch.setattr(video_store, "get_video", records.get)
    def update(key, **values):
        records[key].__dict__.update(values)
        return records[key]
    monkeypatch.setattr(video_store, "update_video", update)
    monkeypatch.setattr(batch_settings, "stage_asset", lambda *_: "")
    monkeypatch.setattr("haizflow.services.project_store.save_batch_settings", Mock())
    assert commands.apply_batch_settings_values("batch", {"watermarkText": "new",
        "translationModel": "gemini-3.5-flash-lite", "ttsProvider": "vieneu",
        "ttsVoice": "vieneu:Trúc Ly", "speakerMode": "multiple"}, True)
    assert all(video.watermark_text == "new" for video in records.values())
    assert all(video.translation_model == "gemini-3.5-flash-lite" for video in records.values())
    assert all(video.tts_provider == "vieneu" and video.tts_voice == "vieneu:Trúc Ly"
               and video.speaker_mode == "multiple" for video in records.values())
    assert host._settings_owner_video_id is None
    host._project_workspace.select_video.assert_called_once_with(records["b"])


def test_reentrant_selection_signal_cannot_read_previous_project_caption_cache(app):
    from haizflow.desktop.manual_editor_document_model import ManualEditorDocumentModel
    from haizflow.schemas.editor import EditorDocument, EditorClip
    model = ManualEditorDocumentModel()
    old = EditorDocument(video_id="w3", clips=[EditorClip(clip_id="old", segment_id="old", track_id="subtitles",
        kind="subtitle", name="Caption from w3", duration_ms=1000)])
    try:
        model.set_document(old)
        assert model.subtitleSegments[0]["text"] == "Caption from w3"
        model._selected_clip_ids = ["old"]
        observed = []
        model.selectionChanged.connect(lambda: observed.append((model.videoId, model.subtitleSegments)))
        model.set_document(EditorDocument(video_id="w4"))
        assert observed == [("w4", [])]
        assert model.subtitleSegments == []
    finally:
        model.close()


def test_cancel_during_batch_preparation_does_not_enqueue_or_touch_unselected(app, tmp_path, monkeypatch):
    host = export_host()
    host._processing_queue.detach_owned = Mock(return_value=(None, []))
    video = SimpleNamespace(video_id="second", project_key="batch", project_type="batch",
                            original_filename="second.mp4", status="paused")
    entered, release = threading.Event(), threading.Event()
    def validate(key):
        entered.set()
        assert release.wait(3)
    monkeypatch.setattr(video_store, "get_video", lambda key: video if key == "second" else None)
    monkeypatch.setattr(video_store, "validate_video_restart", validate)
    restart = Mock()
    monkeypatch.setattr(video_store, "prepare_video_restart", restart)
    monkeypatch.setattr(ProjectCommandsController, "_resources_ready_for_videos", lambda *_: True)
    exporter = VideoExportController(host)
    exporter.timer.stop()
    try:
        assert exporter.start_batch_to("batch", ["second"], "source", str(tmp_path), background=True)
        assert entered.wait(1)
        exporter.cancel_all({"second"})
        release.set()
        exporter._preparation_worker.join(3)
        exporter.poll()
        restart.assert_not_called()
        host._enqueue_videos.assert_not_called()
        assert exporter.jobs[0]["status"] == "cancelled"
    finally:
        release.set()
        exporter.shutdown()


def test_delete_batch_member_is_async_and_completion_cannot_clear_new_selection(app, monkeypatch):
    video = SimpleNamespace(video_id="a", project_type="batch", project_key="batch", status="paused")
    host = SimpleNamespace(_selected_project_key="batch", _batch_video_ids=["a", "b"],
        _selected_video_id="a", _deleted_video_ids=set(), _settings_owner_video_id="a",
        _processing_queue=SimpleNamespace(contains=lambda _: False),
        selectedVideoChanged=Mock(), refreshVideos=Mock(), _refresh_batch_model=Mock(),
        batchChanged=Mock(), appAlertRequested=Mock())
    commands = ProjectCommandsController(host)
    monkeypatch.setattr(video_store, "get_video", lambda _: video)
    monkeypatch.setattr(video_store, "validate_video_restart", Mock())
    monkeypatch.setattr(processing_runs, "forget_restarted", Mock())
    entered, release = threading.Event(), threading.Event()
    def remove(key):
        assert key == "a"
        entered.set()
        assert release.wait(3)
    deleted = Mock(side_effect=remove)
    monkeypatch.setattr(video_store, "delete_video", deleted)
    try:
        assert not commands.remove_batch_video("wrong", "a")
        assert commands.remove_batch_video("batch", "a")
        assert entered.wait(1)
        assert "a" in commands._video_deletions
        host._selected_project_key, host._selected_video_id = "other", "other-video"
        release.set()
        deadline = time.monotonic() + 3
        while commands._video_deletion_events.empty() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.005)
        commands.drain_deletion_events()
        assert "a" not in commands._video_deletions
        assert host._selected_video_id == "other-video"
        host.selectedVideoChanged.emit.assert_not_called()
        deleted.assert_called_once_with("a")
    finally:
        release.set()


def test_batch_process_dialog_layout_and_scope_in_real_qml_window(app):
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(f'''import QtQuick
import QtQuick.Controls.Basic
import "{(root / 'src/haizflow/desktop/qml').as_uri()}"
ApplicationWindow {{ width: 1050; height: 780; visible: true; color: Theme.window
    QtObject {{ id: backend
        property bool videoExportBusy: false
        property var videoExportJobs: []
        property bool isSelectedVideoProcessing: false
        property bool isSelectedVideoQueued: false
        function batchExportSettings() {{ return {{projectKey: "work", preset: "source", ready: true,
            videoIds: ["a", "b", "c"], count: 3,
            presets: [{{value: "source", label: "Theo nguồn"}}],
            videos: [{{videoId: "a", name: "Phần 1 — Video đã hoàn tất.mp4", status: "done"}},
                {{videoId: "b", name: "Phần 2 — Video tạm dừng.mp4", status: "paused"}},
                {{videoId: "c", name: "Phần 3 — Video cần xử lý lại.mp4", status: "failed"}}]}}; }}
    }}
    VideoExportDialog {{ id: dialog; objectName: "dialog"; controller: backend
        Component.onCompleted: {{ openForBatch(true); destination = "E:/hongnguyenky"; }}
    }}
}}'''.encode(), QUrl())
    assert component.isReady(), [error.toString() for error in component.errors()]
    window = component.create()
    try:
        assert isinstance(window, QQuickWindow)
        dialog = window.findChild(QObject, "dialog")
        scope = window.findChild(QObject, "batchScope")
        assert scope.property("targetIds").toVariant() == ["b", "c"]
        scope.setProperty("scope", "selection")
        scope.setProperty("selectedIds", ["b"])
        QTest.qWait(180)
        button = window.findChild(QObject, "confirmVideoExport")
        assert isinstance(button, QQuickItem)
        assert button.isEnabled()
        assert dialog.property("height") <= 732
        # The list must shrink, not push its footer outside the dialog.
        point = button.mapToItem(window.contentItem(), button.boundingRect().bottomRight())
        assert 0 < point.y() < window.height()
        artifact = root / "build/batch-scope-ui-20261112.png"
        assert window.grabWindow().save(str(artifact))
    finally:
        window.close()
        window.deleteLater()
        component.deleteLater()
        engine.deleteLater()
        app.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()

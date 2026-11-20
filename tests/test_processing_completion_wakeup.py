"""Worker completion wakes Qt without changing log polling or project ownership."""
import queue
import re
import threading
from pathlib import Path
from string import Template
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtCore import Property, QObject, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtTest import QSignalSpy, QTest

from haizflow.desktop.processing_lifecycle_controller import ProcessingLifecycleController
from haizflow.desktop.qml_controller import HaizFlowController

_APP = None


class Host(QObject):
    _processingEventsReady = Signal()
    manualToolPreviewReady = Signal(str)
    selectedVideoChanged = Signal()
    processingChanged = Signal()
    batchChanged = Signal()

    def __init__(self):
        super().__init__()
        self._shutdown_started = False
        self._selected_video_id = "a"
        self._log_queue = queue.Queue()
        self._processing_queue = SimpleNamespace(pending_ids=lambda: [], has_work=False)
        self._manual_editor_document = SimpleNamespace(set_document=Mock())
        self._manual_subtitles = SimpleNamespace(load=Mock(), segments=[{"text": "Current"}], _states={})
        self._manual_editing_segment_id = ""
        self.reviewSegments = []
        self.refreshVideos = Mock()
        self._refresh_selected_video_snapshot = Mock()
        self._refresh_batch_model = Mock()
        self.ui_threads = []
        self.preview_requests = []
        self._processing_lifecycle = ProcessingLifecycleController(self)
        self._processingEventsReady.connect(self.wake, Qt.ConnectionType.QueuedConnection)

    @Slot()
    def wake(self):
        self.ui_threads.append(threading.get_ident())
        HaizFlowController._drain_processing_events(self)

    def _drain_log_queue(self):
        self._processing_lifecycle.drain_log_queue()

    @Property(str, notify=selectedVideoChanged)
    def selectedVideoId(self):
        return self._selected_video_id

    @Property(str, constant=True)
    def projectType(self):
        return "manual"

    @Slot(str, float)
    def requestEditorPreview(self, segments, position):
        self.preview_requests.append((segments, position))


@pytest.fixture
def session(tmp_path, monkeypatch):
    global _APP
    _APP = QGuiApplication.instance() or QGuiApplication([])
    host = Host()
    video = SimpleNamespace(video_id="a", project_key="project:a", project_type="manual",
                            status="manual_ready", manual_target_tool="", subtitle_language="")
    prefix = "haizflow.desktop.processing_lifecycle_controller."
    monkeypatch.setattr(prefix + "video_store.get_video", lambda _id: video)
    monkeypatch.setattr(prefix + "video_store.get_video_logs_path", lambda _id: str(tmp_path / "missing.log"))
    monkeypatch.setattr(prefix + "video_store.log_to_video", Mock())
    monkeypatch.setattr(prefix + "project_store.touch_project_by_key", Mock())
    sync = Mock(return_value="current-document")
    monkeypatch.setattr("haizflow.services.editor_documents.sync_subtitle_clips", sync)
    monkeypatch.setattr("haizflow.services.editor_documents.ensure", Mock(return_value="draft-safe-document"))
    yield host, video, sync
    host.deleteLater()
    _APP.processEvents()


def test_worker_finish_and_idle_are_coalesced_and_delivered_on_qt_thread(session):
    host, _video, sync = session
    wakes = QSignalSpy(host._processingEventsReady)
    ready = QSignalSpy(host.manualToolPreviewReady)
    worker = threading.Thread(target=lambda: (
        host._processing_lifecycle.on_queue_video_finished("a"),
        host._processing_lifecycle.on_processing_queue_idle(),
    ))
    worker.start()
    worker.join(timeout=2)
    assert not worker.is_alive() and wakes.count() == 1
    host.refreshVideos.assert_not_called()  # A worker must never call Qt presentation directly.
    for _ in range(20):
        if ready.count():
            break
        QTest.qWait(5)
    assert ready.count() == 1 and ready.at(0) == ["a"]
    assert host.ui_threads == [threading.get_ident()]
    sync.assert_called_once()
    host._manual_editor_document.set_document.assert_called_once_with("current-document")
    assert host._log_queue.empty()
    assert host.refreshVideos.call_count == 2  # Finish + idle, no duplicate timer delivery.
    host._drain_log_queue()
    assert ready.count() == 1


def test_translation_replaces_selected_old_caption_before_queue_cleanup(session):
    host, video, sync = session
    video.step = "manual_translation"
    video.files = {"transcript_json": "openrouter/segments.json", "ocr_output": "existing-ocr.json"}
    host._manual_editing_segment_id = "cue-6"
    fresh = [{"segment_id": "cue-6", "text": "New translation"}]
    host.reviewSegments = fresh
    host._manual_subtitles.load.side_effect = lambda _id, rows: setattr(host._manual_subtitles, "segments", rows)
    ready = QSignalSpy(host.manualToolPreviewReady)
    worker = threading.Thread(target=host._processing_lifecycle.on_translation_published, args=("a",))
    worker.start()
    worker.join(timeout=2)
    assert not worker.is_alive()
    host._manual_subtitles.load.assert_not_called()
    QTest.qWait(20)

    host._manual_subtitles.load.assert_called_once_with("a", fresh)
    sync.assert_called_once_with(video, fresh)
    host._manual_editor_document.set_document.assert_called_once_with("current-document")
    assert host.ui_threads == [threading.get_ident()]
    assert video.files["ocr_output"] == "existing-ocr.json"
    assert ready.count() == 0  # Media stays on the queue's normal completion path.

    host._processing_lifecycle.on_queue_video_finished("a")
    QTest.qWait(20)
    sync.assert_called_once()
    assert ready.count() == 1 and ready.at(0) == ["a"]


@pytest.mark.parametrize("guard", ["other-project", "saving", "error", "paused"])
def test_translation_publication_respects_project_ownership_and_pending_writes(session, guard):
    host, video, sync = session
    video.step = "manual_translation"
    video.files = {"transcript_json": "openrouter/segments.json"}
    if guard == "other-project":
        host._selected_video_id = "b"
    elif guard == "paused":
        video.status = "paused"
    else:
        host._manual_subtitles._states["cue-6"] = guard
    ready = QSignalSpy(host.manualToolPreviewReady)
    host._processing_lifecycle.on_translation_published("a")
    host._processing_lifecycle.on_queue_video_finished("a")
    QTest.qWait(20)

    host._manual_subtitles.load.assert_not_called()
    host._manual_editor_document.set_document.assert_not_called()
    sync.assert_not_called()
    assert ready.count() == 0


def test_translation_finish_retries_if_an_earlier_save_delayed_publication(session):
    host, video, sync = session
    video.step = "manual_translation"
    video.files = {"transcript_json": "openrouter/segments.json"}
    host._manual_editing_segment_id = "cue-6"
    host._manual_subtitles._states["cue-6"] = "saving"
    host._processing_lifecycle.on_translation_published("a")
    QTest.qWait(20)
    sync.assert_not_called()

    host._manual_subtitles._states.clear()
    host._processing_lifecycle.on_queue_video_finished("a")
    QTest.qWait(20)
    sync.assert_called_once()


@pytest.mark.parametrize("switch_during_refresh", [False, True])
def test_other_project_completion_never_reconciles_or_requests_selected_preview(session, switch_during_refresh):
    host, _video, sync = session
    ready = QSignalSpy(host.manualToolPreviewReady)
    selected = QSignalSpy(host.selectedVideoChanged)
    if switch_during_refresh:
        host.refreshVideos.side_effect = lambda: setattr(host, "_selected_video_id", "b")
    else:
        host._selected_video_id = "b"
    host._processing_lifecycle.on_queue_video_finished("a")
    QTest.qWait(20)
    sync.assert_not_called()
    host._manual_editor_document.set_document.assert_not_called()
    assert ready.count() == selected.count() == 0


@pytest.mark.parametrize("status", ["failed", "paused", "cancelled", "processing"])
def test_non_completed_tool_does_not_get_fast_preview_signal(session, status):
    host, video, sync = session
    video.status = status
    ready = QSignalSpy(host.manualToolPreviewReady)
    host._processing_lifecycle.on_queue_video_finished("a")
    QTest.qWait(20)
    assert ready.count() == 0
    sync.assert_not_called()


def test_reconciliation_failure_does_not_announce_preview_ready(session):
    host, _video, sync = session
    sync.side_effect = RuntimeError("fixture failure")
    ready = QSignalSpy(host.manualToolPreviewReady)
    host._processing_lifecycle.on_queue_video_finished("a")
    QTest.qWait(20)
    assert ready.count() == 0


def test_log_lines_do_not_trigger_extra_wakeups_and_shutdown_ignores_delivery(session):
    host, _video, _sync = session
    wakes = QSignalSpy(host._processingEventsReady)
    for index in range(100):
        host._processing_lifecycle.on_video_log("a", str(index))
    assert wakes.count() == 0
    host._shutdown_started = True
    host._processing_lifecycle.on_queue_video_finished("a")
    assert wakes.count() == 0
    host._processingEventsReady.emit()
    QTest.qWait(10)
    host.refreshVideos.assert_not_called()


def test_completion_signals_remain_explicitly_queued_and_debounce_stays_for_edits():
    root = Path(__file__).resolve().parents[1] / "src/haizflow/desktop"
    controller = (root / "qml_controller.py").read_text("utf-8")
    assert (
        "self._processingEventsReady.connect(self._drain_processing_events, Qt.ConnectionType.QueuedConnection)"
        in controller
    )
    assert "self._log_timer.start(500)" in controller
    workspace = (root / "qml/ManualWorkspace.qml").read_text("utf-8")
    assert "function onManualToolPreviewReady(videoId)" in workspace
    assert "Qt.callLater(root.refreshCompletedPreview, videoId)" in workspace
    assert "interval: root.initialMediaLoad ? 200 : 100" in workspace


@pytest.fixture
def preview_qml(session):
    """Execute the production completion handler and timer in a minimal QML host."""
    host, _video, _sync = session
    source = (Path(__file__).resolve().parents[1]
              / "src/haizflow/desktop/qml/ManualWorkspace.qml").read_text("utf-8")

    def function(name):
        start = source.index(f"    function {name}(")
        return source[start:source.index("\n    function ", start + 4)]

    timer = re.search(r"    Timer \{\s+id: previewTimer\b.*?\n    \}", source, re.DOTALL).group()
    handler = re.search(r"        function onManualToolPreviewReady\(videoId\).*", source).group()
    qml = Template("""
import QtQuick
Item {
    id: root
    property bool sourceReplacementPending: false
    property bool subtitleOwnerMatches: true
    property bool initialMediaLoad: false
    property string previewVideoId: "a"
    property QtObject editorModel: QtObject { property string videoId: "a" }
    property var segments: [{segment_id: "current", text: "Current project"}]
    QtObject { id: comparePreview; property real positionSeconds: 4.2 }
    $schedule
    $refresh
    $timer
    Connections {
        target: AppController
        function onSelectedVideoChanged() { root.schedulePreview(); }
        $handler
    }
}
""").substitute(schedule=function("schedulePreview"), refresh=function("refreshCompletedPreview"),
                  timer=timer, handler=handler)
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("AppController", host)
    component = QQmlComponent(engine)
    component.setData(qml.encode(), QUrl())
    root = component.create()
    assert root is not None, [error.toString() for error in component.errors()]
    yield host, root
    root.deleteLater()
    _APP.processEvents()
    engine.deleteLater()
    _APP.processEvents()


def test_qml_completion_bypasses_debounce_once_after_bindings_settle(preview_qml):
    host, root = preview_qml
    root.schedulePreview()
    host.manualToolPreviewReady.emit("a")
    assert not host.preview_requests  # Qt.callLater, not a reentrant preview request.
    QTest.qWait(20)
    assert len(host.preview_requests) == 1
    assert '"segment_id":"current"' in host.preview_requests[0][0]
    assert host.preview_requests[0][1] == 4.2
    QTest.qWait(140)
    assert len(host.preview_requests) == 1  # Original timer was cancelled, not duplicated.


def test_worker_completion_reaches_qml_without_poll_timer(preview_qml):
    host, _root = preview_qml
    worker = threading.Thread(target=lambda: (
        host._processing_lifecycle.on_queue_video_finished("a"),
        host._processing_lifecycle.on_processing_queue_idle(),
    ))
    worker.start()
    worker.join(timeout=2)
    assert not worker.is_alive() and not host.preview_requests
    QTest.qWait(30)
    assert len(host.preview_requests) == 1
    QTest.qWait(140)
    assert len(host.preview_requests) == 1


@pytest.mark.parametrize("guard", ["hidden", "replacement", "subtitles", "document", "selected", "event", "preview"])
def test_qml_deferred_completion_rechecks_current_project_and_visibility(preview_qml, guard):
    host, root = preview_qml
    host.manualToolPreviewReady.emit("b" if guard == "event" else "a")
    if guard == "hidden":
        root.setProperty("visible", False)
    elif guard == "replacement":
        root.setProperty("sourceReplacementPending", True)
    elif guard == "subtitles":
        root.setProperty("subtitleOwnerMatches", False)
    elif guard == "document":
        root.property("editorModel").setProperty("videoId", "b")
    elif guard == "selected":
        host._selected_video_id = "b"
    elif guard == "preview":
        root.setProperty("previewVideoId", "b")
    QTest.qWait(30)
    assert not host.preview_requests


def test_qml_ordinary_edits_still_use_debounce(preview_qml):
    host, root = preview_qml
    root.schedulePreview()
    QTest.qWait(20)
    assert not host.preview_requests
    root.schedulePreview()
    QTest.qWait(20)
    assert not host.preview_requests
    QTest.qWait(140)
    assert len(host.preview_requests) == 1

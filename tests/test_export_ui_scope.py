"""A batch export must not impersonate the video currently open in Manual."""

from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QObject, Property, QEvent, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtTest import QTest

from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.desktop.video_export_controller import VideoExportController

QML_DIR = Path(__file__).parents[1] / "src/haizflow/desktop/qml"
_APP = None


class ScopeController(QObject):
    exportStateChanged = Signal()
    exportScopeChanged = Signal()
    selectedVideoChanged = Signal()
    batchChanged = Signal()

    def __init__(self):
        super().__init__()
        self._selected_video_id = "manual-d"
        self._project_type = "manual"
        self._batch_video_ids = []
        self._processing_queue = Mock()
        self._processing_queue.token_for.return_value = None
        self._video_exports = VideoExportController(self)
        self._video_exports.timer.stop()
        self.selectedVideoChanged.connect(self.exportScopeChanged.emit)
        self.batchChanged.connect(self.exportScopeChanged.emit)
        self.exportStateChanged.connect(self.exportScopeChanged.emit)

    videoExportBusy = Property(bool, lambda self: self._video_exports.busy, notify=exportStateChanged)
    videoExportJobs = Property("QVariantList", lambda self: self._video_exports.jobs, notify=exportStateChanged)
    videoExportSummary = Property("QVariantMap", lambda self: self._video_exports.summary, notify=exportStateChanged)
    videoExportDialogModel = Property(QObject, lambda self: self._video_exports.dialog_job_model, constant=True)
    videoExportScope = Property("QVariantList", HaizFlowController.videoExportScope.fget, notify=exportScopeChanged)
    videoExportScopeSummary = Property("QVariantMap", HaizFlowController.videoExportScopeSummary.fget,
                                      notify=exportScopeChanged)
    selectedVideoExportActive = Property(bool, HaizFlowController.selectedVideoExportActive.fget,
                                        notify=exportScopeChanged)

    @Slot("QVariantList")
    def setVideoExportDialogScope(self, ids):
        self._video_exports.set_dialog_scope(ids)


@pytest.fixture
def controller():
    global _APP
    _APP = QGuiApplication.instance() or QGuiApplication([])
    host = ScopeController()
    try:
        yield host
    finally:
        host._video_exports.shutdown()
        host.deleteLater()
        _APP.sendPostedEvents(None, QEvent.DeferredDelete)
        _APP.processEvents()


@pytest.mark.parametrize("status", ["preparing", "pending", "rendering", "exporting", "done", "failed", "cancelled"])
def test_other_batch_never_activates_selected_export_or_opens_empty_progress(controller, status):
    exporter = controller._video_exports
    exporter.jobs = [dict(videoId="batch-a", path="a.mp4", status=status, progress=36)]
    exporter.changed()
    assert not controller.selectedVideoExportActive
    assert controller.videoExportScopeSummary["count"] == 0
    assert controller.videoExportScopeSummary["activeJob"] == {}
    controller.videoExportProgressRequested = Mock()
    HaizFlowController.requestVideoExportProgress(controller)
    controller.videoExportProgressRequested.emit.assert_not_called()


def test_scope_follows_navigation_and_batch_membership_without_rewriting_jobs(controller):
    exporter = controller._video_exports
    exporter.jobs = [dict(videoId="batch-a", path="a.mp4", status="rendering", progress=36),
                     dict(videoId="manual-d", path="d.mp4", status="exporting", progress=95)]
    exporter.changed()
    assert controller.selectedVideoExportActive
    assert controller.videoExportScopeSummary["activeJob"]["videoId"] == "manual-d"
    controller._selected_video_id = "manual-e"
    controller.selectedVideoChanged.emit()
    assert not controller.selectedVideoExportActive
    assert not controller.videoExportScopeSummary["activeJob"]
    controller._project_type = "batch"
    controller._batch_video_ids = ["batch-a", "batch-b"]
    controller.batchChanged.emit()
    assert controller.videoExportScopeSummary["activeJob"]["videoId"] == "batch-a"
    assert len(exporter.jobs) == 2
    # Empty/no project scope must not fall back to all projects.
    controller._project_type = "manual"
    controller._selected_video_id = ""
    controller.selectedVideoChanged.emit()
    assert not controller.videoExportScopeSummary["activeJob"]


def test_selected_export_includes_preparation_and_clears_at_completion(controller):
    exporter = controller._video_exports
    job = dict(videoId="manual-d", path="d.mp4", status="preparing", progress=0)
    exporter.jobs = [job]
    controller.videoExportProgressRequested = Mock()
    for status in ("preparing", "pending", "rendering", "exporting"):
        job["status"] = status
        exporter.changed()
        assert controller.selectedVideoExportActive
        HaizFlowController.requestVideoExportProgress(controller)
    assert controller.videoExportProgressRequested.emit.call_count == 4
    for status in ("done", "failed", "cancelled", "paused", "awaiting_review"):
        job["status"] = status
        exporter.changed()
        assert not controller.selectedVideoExportActive


@pytest.mark.parametrize("status", ["paused", "awaiting_review", "done", "failed", "cancelled"])
def test_inactive_selected_job_stays_inactive_while_another_batch_renders(controller, status):
    controller._video_exports.jobs = [
        dict(videoId="manual-d", path="d.mp4", status=status, progress=50),
        dict(videoId="batch-a", path="a.mp4", status="rendering", progress=40),
    ]
    controller._video_exports.changed()
    assert controller.videoExportBusy
    assert not controller.selectedVideoExportActive
    assert not controller.videoExportScopeSummary["activeJob"]


def test_real_qml_toolbar_and_strip_bindings_switch_scope_live(controller):
    workspace = (QML_DIR / "ManualWorkspace.qml").read_text(encoding="utf-8")
    assert "exportBusy: AppController.selectedVideoExportActive" in workspace
    main = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
    bindings = main.split("    readonly property var activeExportJob:", 1)[1].split("    // qmllint", 1)[0]
    bindings = "readonly property var activeExportJob:" + bindings.replace("AppController", "scopeController")
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("scopeController", controller)
    component = QQmlComponent(engine)
    component.setData(f'''import QtQuick
import QtQuick.Controls.Basic
import "{QML_DIR.as_uri()}"
ApplicationWindow {{
    id: root
    width: 1100; height: 750; visible: true
    property bool projectWorkspaceVisible: true
    {bindings}
    ManualEditorToolbar {{
        objectName: "toolbar"; width: parent.width; hasVideo: true
        exportEnabled: !scopeController.videoExportBusy
        exportBusy: scopeController.selectedVideoExportActive
    }}
    VideoExportJobsDialog {{ objectName: "dialog"; controller: scopeController }}
}}'''.encode(), QUrl())
    assert component.isReady(), [e.toString() for e in component.errors()]
    window = component.create()
    assert window is not None
    try:
        exporter = controller._video_exports
        job = dict(videoId="batch-a", name="a.mp4", path="a.mp4", status="rendering", progress=36)
        exporter.jobs = [job]
        exporter.changed()
        QTest.qWait(30)
        button = window.findChild(QObject, "manualExportButton")
        assert button.property("text") == "Xuất"
        assert not window.property("exportWorking")
        dialog = window.findChild(QObject, "dialog")
        dialog.openForVideos(["manual-d"])
        assert not dialog.property("visible")
        # Home retains the genuine global meter; project pages are scoped.
        window.setProperty("projectWorkspaceVisible", False)
        assert window.property("exportWorking")
        window.setProperty("projectWorkspaceVisible", True)
        controller._selected_video_id = "batch-a"
        controller.selectedVideoChanged.emit()
        QTest.qWait(30)
        assert button.property("text") == "Đang xuất"
        assert window.property("exportWorking")
        dialog.openForVideos(["batch-a"])
        assert dialog.property("visible")
        assert exporter.dialog_job_model.rowCount() == 1
        dialog.close()
        job["status"] = "done"
        exporter.changed()
        QTest.qWait(30)
        assert button.property("text") == "Xuất"
        assert not window.property("exportWorking")
    finally:
        window.close()
        window.deleteLater()
        component.deleteLater()
        engine.deleteLater()
        _APP.sendPostedEvents(None, QEvent.DeferredDelete)
        _APP.processEvents()


def test_real_facade_notifies_scope_on_both_navigation_and_export_updates():
    source = (QML_DIR.parent / "qml_controller.py").read_text(encoding="utf-8")
    for signal in ("selectedVideoChanged", "batchChanged", "exportStateChanged"):
        assert f"self.{signal}.connect(self.exportScopeChanged.emit)" in source

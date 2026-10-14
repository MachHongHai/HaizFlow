"""Rendering progress is measured in both export dialog and activity strip."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlPropertyMap
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from hflow.desktop.video_export_controller import VideoExportController

QML_DIR = Path(__file__).parents[1] / "src/hflow/desktop/qml"


@pytest.mark.parametrize("step,measured", [("manual_export", True), ("rendering", True),
    ("manual_export_preparing", True), ("starting", False), ("transcribing", False)])
def test_job_receives_pipeline_progress_even_while_queue_owns_video(monkeypatch, step, measured):
    host = QObject()
    host.exportStateChanged = Mock()
    host._processing_queue = SimpleNamespace(contains=lambda _key: True)
    exporter = VideoExportController(host)
    exporter.timer.stop()
    exporter.jobs = [{"videoId": "video-a", "status": "rendering", "progress": 0}]
    video = SimpleNamespace(step=step, progress=61, status="processing")
    monkeypatch.setattr("hflow.desktop.video_export_controller.video_store.get_video", lambda _key: video)
    try:
        exporter.poll()
        assert exporter.jobs[0]["progress"] == 55
        assert exporter.jobs[0]["progressMeasured"] is measured
        video.progress = 79
        exporter.poll()
        assert exporter.jobs[0]["progress"] == 71
    finally:
        exporter.shutdown()


def test_progress_reserves_publication_phase_and_reaches_100_only_on_success():
    job = {"renderRequired": True}
    values = [VideoExportController.job_progress(job, "rendering", raw) for raw in (0, 50, 99, 100)]
    values += [VideoExportController.job_progress(job, "exporting", raw) for raw in (0, 30, 95, 99, 100)]
    assert values == sorted(values)
    assert values[3] == 90
    assert max(values) == 99
    assert VideoExportController.job_progress(job, "done", 100) == 100
    # Cached/range-only exports use the full meter but retain the same gate.
    assert VideoExportController.job_progress({}, "exporting", 100) == 99


def test_render_to_copy_transition_does_not_reset_or_finish_early(monkeypatch):
    host = QObject()
    host.exportStateChanged = Mock()
    host.videoExportCompleted = Mock()
    host._processing_queue = SimpleNamespace(contains=lambda _key: True)
    exporter = VideoExportController(host)
    exporter.timer.stop()
    job = {"videoId": "video-a", "path": "out.mp4", "status": "rendering", "progress": 0, "renderRequired": True}
    exporter.jobs = [job]
    video = SimpleNamespace(step="manual_export", progress=100, status="processing")
    monkeypatch.setattr("hflow.desktop.video_export_controller.video_store.get_video", lambda _key: video)
    try:
        exporter.poll()
        assert job["progress"] == 90
        for raw in (0, 95, 99, 100):
            exporter.events.put(("video-a", "exporting", raw, ""))
            exporter.poll()
            assert 90 <= job["progress"] <= 99
        host.videoExportCompleted.emit.assert_not_called()
        exporter.events.put(("video-a", "done", 100, ""))
        exporter.poll()
        assert job["progress"] == 100 and job["status"] == "done"
        host.videoExportCompleted.emit.assert_called_once_with("video-a", "out.mp4")
    finally:
        exporter.shutdown()


def test_activity_strip_reads_same_export_meter_in_render_and_save_phases():
    source = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
    assert 'job.status === "rendering" || job.status === "exporting"' in source
    assert 'Number(root.activeExportJob.progress || 0) / 100' in source


def test_real_dialog_updates_and_reopens_without_sweeping_measured_progress():
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    controller = QQmlPropertyMap()
    controller.insert("videoExportBusy", True)
    def update(status, progress, measured):
        controller.insert("videoExportJobs", [{"videoId": "a", "name": "fff.mp4", "path": "fff.mp4",
            "status": status, "progress": progress, "progressMeasured": measured, "error": ""}])
        app.processEvents()
    update("rendering", 61, True)
    engine.rootContext().setContextProperty("progressController", controller)
    component = QQmlComponent(engine)
    component.setData(f'''import QtQuick
import QtQuick.Controls.Basic
import "{QML_DIR.as_uri()}"
ApplicationWindow {{
    width: 1100; height: 750; visible: true
    VideoExportJobsDialog {{ objectName: "dialog"; controller: progressController }}
}}'''.encode(), QUrl())
    assert component.isReady(), [e.toString() for e in component.errors()]
    window = component.create()
    assert isinstance(window, QQuickWindow)
    try:
        dialog = window.findChild(QObject, "dialog")
        dialog.open()
        QTest.qWait(280)
        def find_bar():
            def visit(item):
                if item.objectName() == "exportJobProgress":
                    return item
                for child in item.childItems():
                    found = visit(child)
                    if found is not None:
                        return found
                return None
            return visit(window.contentItem())
        bar = find_bar()
        assert bar is not None and bar.property("value") == 61
        assert not bar.property("indeterminate")
        update("rendering", 79, True)
        QTest.qWait(30)
        bar = find_bar()
        assert bar.property("value") == 79 and not bar.property("indeterminate")
        dialog.close()
        QTest.qWait(220)
        update("rendering", 85, True)
        dialog.open()
        QTest.qWait(220)
        bar = find_bar()
        assert bar.property("value") == 85 and not bar.property("indeterminate")
        update("rendering", 0, False)
        QTest.qWait(30)
        assert find_bar().property("indeterminate")
        update("exporting", 90, False)
        QTest.qWait(30)
        assert not find_bar().property("indeterminate")
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()
        app.processEvents()

"""Export cannot interrupt a running/queued editor stage, including UI races."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QObject, QPointF, QUrl, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QSignalSpy, QTest

from hflow.desktop.qml_controller import HFlowController

QML_DIR = Path(__file__).parents[1] / "src/hflow/desktop/qml"


@pytest.mark.parametrize("has_video,processing,queued,exporting,expected", [
    (True, False, False, False, True),
    (True, True, True, False, False),
    (True, True, False, False, False),
    (True, False, True, False, False),
    (True, False, False, True, False),
    (False, False, False, False, False),
])
def test_backend_does_not_open_export_dialog_during_processing(has_video, processing, queued, exporting, expected):
    signal = Mock()
    host = SimpleNamespace(hasSelectedVideo=has_video, videoExportBusy=exporting,
                           isSelectedVideoProcessing=processing, isSelectedVideoQueued=queued,
                           videoExportRequested=signal)
    HFlowController.requestVideoExport(host)
    assert signal.emit.call_count == int(expected)


def test_export_button_tracks_busy_state_and_reenables_without_changing_toolbar():
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(f'''import QtQuick
import QtQuick.Controls.Basic
import "{QML_DIR.as_uri()}"
ApplicationWindow {{
    id: hostWindow
    width: 1100; height: 60; visible: true
    property bool processing: false
    property bool queued: false
    property bool exporting: false
    ManualEditorToolbar {{
        objectName: "toolbar"; width: parent.width; hasVideo: true
        exportEnabled: !hostWindow.processing && !hostWindow.queued && !hostWindow.exporting
        exportBusy: hostWindow.exporting
    }}
}}'''.encode(), QUrl())
    assert component.isReady(), [error.toString() for error in component.errors()]
    window = component.create()
    try:
        QTest.qWait(40)
        toolbar = window.findChild(QObject, "toolbar")
        button = window.findChild(QQuickItem, "manualExportButton")
        spy = QSignalSpy(toolbar.exportRequested)
        progress_spy = QSignalSpy(toolbar.exportProgressRequested)
        geometry = button.mapToScene(QPointF(button.width() / 2, button.height() / 2)).toPoint()
        assert button.isEnabled()
        for busy in ("processing", "queued"):
            window.setProperty(busy, True)
            app.processEvents()
            assert not button.isEnabled()
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, geometry)
            assert spy.count() == 0
            window.setProperty(busy, False)
            app.processEvents()
            assert button.isEnabled()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, geometry)
        assert spy.count() == 1
        window.setProperty("exporting", True)
        window.setProperty("processing", True)
        QTest.qWait(30)
        assert button.isEnabled() and button.property("text") == "Đang xuất"
        geometry = button.mapToScene(QPointF(button.width() / 2, button.height() / 2)).toPoint()
        for _ in range(2):
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, geometry)
        assert progress_spy.count() == 2 and spy.count() == 1
        window.setProperty("exporting", False)
        app.processEvents()
        assert not button.isEnabled() and button.property("text") == "Xuất"
        window.setProperty("processing", False)
        app.processEvents()
        assert button.isEnabled()
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()
        app.processEvents()


def test_export_opens_dialog_without_replacing_the_current_editor_panel():
    source = (QML_DIR / "ManualWorkspace.qml").read_text(encoding="utf-8")
    handler = source.split("onExportRequested: {", 1)[1].split("onProjectFolderRequested:", 1)[0]
    assert "stageInspector.saveNow();" in handler
    assert "AppController.requestVideoExport();" in handler
    assert "selectedStageIndex =" not in handler and "activatePanel(" not in handler
    restore = source.split("function restoreEditorView()", 1)[1].split("function ", 1)[0]
    assert "Number(view.stage || 0) === 6 ? 0" in restore


@pytest.mark.parametrize("busy", [False, True])
def test_progress_request_only_opens_existing_export_without_starting_another(busy):
    host = SimpleNamespace(videoExportBusy=busy, videoExportProgressRequested=Mock(),
                           videoExportRequested=Mock(), videoExportStarted=Mock())
    HFlowController.requestVideoExportProgress(host)
    assert host.videoExportProgressRequested.emit.call_count == int(busy)
    host.videoExportRequested.emit.assert_not_called()
    host.videoExportStarted.emit.assert_not_called()

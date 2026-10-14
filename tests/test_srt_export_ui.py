"""Exercise the actual SRT dialog with an isolated controller and Qt window."""
import os
import subprocess
import sys
from pathlib import Path


def check_dialog():
    from PySide6.QtCore import QCoreApplication, QEvent, QMetaObject, QObject, QPointF, Qt, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtQuick import QQuickWindow
    from PySide6.QtTest import QTest

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    qml_dir = Path(__file__).parents[1] / "src/hflow/desktop/qml"
    component = QQmlComponent(engine)
    component.setData(f'''import QtQuick
import QtQuick.Controls.Basic
import "{qml_dir.as_uri()}"
ApplicationWindow {{
    width: 800; height: 600; visible: true; color: Theme.window
    QtObject {{
        id: controller
        property bool isProcessing: false
        property bool videoExportBusy: false
        property bool mediaImportBusy: false
        property bool original: true
        property bool result: true
        property bool succeeds: false
        property int calls: 0
        property string lastKind: ""
        property string lastVideo: ""
        function srtExportSettings() {{ return {{videoId: "source-project", source: original, result: result}}; }}
        function exportSelectedSrt(kind, videoId) {{ calls++; lastKind = kind; lastVideo = videoId; return succeeds; }}
    }}
    SrtExportDialog {{ objectName: "srtDialog"; controller: controller }}
}}'''.encode(), QUrl())
    assert component.isReady(), [error.toString() for error in component.errors()]
    window = component.create()
    assert isinstance(window, QQuickWindow)
    try:
        dialog = window.findChild(QObject, "srtDialog")
        assert QMetaObject.invokeMethod(dialog, "openForSelection", Qt.DirectConnection)
        QTest.qWait(220)
        assert dialog.property("opened")
        control = dialog.property("controller")
        combo = dialog.findChild(QObject, "srtExportKind")
        confirm = dialog.findChild(QObject, "confirmSrtExport")
        assert combo.property("count") == 3 and control.property("calls") == 0
        assert combo.property("currentValue") == "result"
        combo.setProperty("currentIndex", 2)
        QTest.qWait(15)
        assert confirm.property("enabled")
        QMetaObject.invokeMethod(confirm, "clicked", Qt.DirectConnection)
        assert control.property("lastKind") == "both" and control.property("lastVideo") == "source-project"
        assert dialog.property("visible")  # Cancelled picker/failed write keeps selection available.
        control.setProperty("isProcessing", True)
        QTest.qWait(15)
        assert not confirm.property("enabled")
        control.setProperty("isProcessing", False)
        control.setProperty("succeeds", True)
        QMetaObject.invokeMethod(confirm, "clicked", Qt.DirectConnection)
        QTest.qWait(220)
        assert not dialog.property("visible")
        control.setProperty("result", False)
        QMetaObject.invokeMethod(dialog, "openForSelection", Qt.DirectConnection)
        QTest.qWait(220)
        assert combo.property("currentValue") == "source"
        combo.setProperty("currentIndex", 2)
        QTest.qWait(15)
        assert not confirm.property("enabled")
        capture_dir = os.environ.get("HFLOW_UI_PREVIEWS")
        if capture_dir:
            control.setProperty("result", True)
            QMetaObject.invokeMethod(dialog, "openForSelection", Qt.DirectConnection)
            combo.setProperty("currentIndex", 2)
            position = combo.mapToScene(QPointF(combo.width() / 2, combo.height() / 2)).toPoint()
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, position)
            QTest.qWait(220)
            assert window.grabWindow().save(str(Path(capture_dir) / "srt-export.png"))
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def test_srt_dialog_options_guard_processing_and_keep_project_identity():
    completed = subprocess.run([sys.executable, str(Path(__file__).resolve())], capture_output=True,
        text=True, timeout=30)
    assert completed.returncode == 0, completed.stdout + completed.stderr


if __name__ == "__main__":
    check_dialog()

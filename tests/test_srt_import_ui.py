"""Exercise SRT import in a real Qt window with an isolated controller."""
import subprocess
import sys
from pathlib import Path


def check_dialog():
    from PySide6.QtCore import QCoreApplication, QEvent, QMetaObject, QObject, Qt, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtQuick import QQuickWindow
    from PySide6.QtTest import QTest

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    directory = Path(__file__).parents[1] / "src/hflow/desktop/qml"
    component = QQmlComponent(engine)
    component.setData(f'''import QtQuick
import QtQuick.Controls.Basic
import "{directory.as_uri()}"
ApplicationWindow {{
    width: 800; height: 600; visible: true
    QtObject {{
        id: stub
        property string selectedVideoId: "project-a"
        property string pickedVideo: "project-a"
        property bool isProcessing: false
        property bool videoExportBusy: false
        property bool mediaImportBusy: false
        property bool succeeds: false
        property int calls: 0
        property string importedLanguage: ""
        property string importedVideo: ""
        function chooseSrtImportFile() {{ return {{videoId: pickedVideo, path: "chosen.srt", filename: "chosen.srt", language: "vi"}}; }}
        function importSelectedSrt(path, language, videoId) {{
            calls++; importedLanguage = language; importedVideo = videoId; return succeeds;
        }}
    }}
    SrtImportDialog {{ objectName: "importDialog"; controller: stub }}
}}'''.encode(), QUrl())
    assert component.isReady(), [error.toString() for error in component.errors()]
    window = component.create()
    assert isinstance(window, QQuickWindow)
    try:
        dialog = window.findChild(QObject, "importDialog")
        QMetaObject.invokeMethod(dialog, "openForSelection", Qt.DirectConnection)
        QTest.qWait(200)
        controller = dialog.property("controller")
        picker = dialog.findChild(QObject, "chooseSrtImport")
        language = dialog.findChild(QObject, "srtImportLanguage")
        confirm = dialog.findChild(QObject, "confirmSrtImport")
        assert not confirm.property("enabled")
        controller.setProperty("pickedVideo", "another-project")
        QMetaObject.invokeMethod(picker, "clicked", Qt.DirectConnection)
        QTest.qWait(10)
        assert not confirm.property("enabled")
        controller.setProperty("pickedVideo", "project-a")
        QMetaObject.invokeMethod(picker, "clicked", Qt.DirectConnection)
        QTest.qWait(10)
        assert confirm.property("enabled") and language.property("currentValue") == "vi"
        controller.setProperty("isProcessing", True)
        QTest.qWait(10)
        assert not confirm.property("enabled")
        controller.setProperty("isProcessing", False)
        QTest.qWait(10)
        QMetaObject.invokeMethod(confirm, "clicked", Qt.DirectConnection)
        QTest.qWait(90)
        assert controller.property("calls") == 1
        assert controller.property("importedLanguage") == "vi" and controller.property("importedVideo") == "project-a"
        assert dialog.property("visible")
        controller.setProperty("succeeds", True)
        QMetaObject.invokeMethod(confirm, "clicked", Qt.DirectConnection)
        QTest.qWait(230)
        assert not dialog.property("visible")
        QMetaObject.invokeMethod(dialog, "openForSelection", Qt.DirectConnection)
        QTest.qWait(200)
        assert not confirm.property("enabled")
        assert language.property("currentValue") == "und"
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def test_srt_import_dialog_guards_busy_and_stale_selection():
    result = subprocess.run([sys.executable, str(Path(__file__).resolve())],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


if __name__ == "__main__":
    check_dialog()

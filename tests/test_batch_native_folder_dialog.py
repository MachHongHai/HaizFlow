"""Batch's real QML button must not bypass the native-profile media picker."""

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import QObject, Property, QEvent, QMetaObject, QUrl, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtTest import QTest

from haizflow.desktop import localization
from haizflow.desktop.video_export_controller import VideoExportController

QML_DIR = Path(__file__).parents[1] / "src/haizflow/desktop/qml"
_APP = None


class Backend(QObject):
    def __init__(self):
        super().__init__()
        self.project = "batch-1"
        self.collision = False
        self.folder_calls = 0
        self.exporter = SimpleNamespace(
            text=lambda vi, en: vi,
            # Selection alone must not enumerate or validate batch videos.
            _batch_video_ids=Mock(side_effect=AssertionError("No batch scan in picker")),
        )

    videoExportJobs = Property("QVariantList", lambda self: [], constant=True)
    videoExportBusy = Property(bool, lambda self: False, constant=True)
    isSelectedVideoProcessing = Property(bool, lambda self: False, constant=True)
    isSelectedVideoQueued = Property(bool, lambda self: False, constant=True)

    @Slot(result="QVariantMap")
    def batchExportSettings(self):
        return dict(projectKey=self.project, videos=[dict(videoId="a", name="a.mp4", status="pending")],
                    presets=[dict(value="source", label="Original")], preset="source")

    @Slot(result="QVariantMap")
    def manualExportSettings(self):
        return dict(videoId="manual", filename="manual.mp4", presets=[], segments=[])

    @Slot(result=str)
    def chooseBatchExportFolder(self):
        self.folder_calls += 1
        return VideoExportController.choose_batch_folder(self.exporter)

    @Slot(str, result=bool)
    def batchExportDestinationExists(self, _directory):
        return self.collision

    @Slot(str, result=str)
    def chooseVideoExportDestination(self, _video_id):
        return localization.QFileDialog.getSaveFileName(None, "Export", "manual.mp4", "MP4 (*.mp4)")[0]

    @Slot(str, result=bool)
    def exportDestinationExists(self, _path):
        return False


def test_batch_picker_then_manual_picker_share_native_profile_and_restore_after_each_call(tmp_path):
    global _APP
    _APP = QGuiApplication.instance() or QGuiApplication([])
    native = tmp_path / "real-user"
    downloads = native / "Downloads"
    downloads.mkdir(parents=True)
    portable = tmp_path / "portable"
    portable.mkdir()
    output = str(tmp_path / "export")
    selected = [output, "", output]
    before = dict(USERPROFILE=str(portable), HOMEDRIVE="Z:", HOMEPATH="\\portable")
    backend = Backend()
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("AppController", backend)
    engine.rootContext().setContextProperty("pickerBackend", backend)
    component = QQmlComponent(engine)
    component.setData(f'''import QtQuick
import QtQuick.Controls.Basic
import "{QML_DIR.as_uri()}"
ApplicationWindow {{ width: 1000; height: 800; visible: true
    VideoExportDialog {{ objectName: "exportDialog"; controller: pickerBackend }}
}}'''.encode(), QUrl())
    assert component.isReady(), [error.toString() for error in component.errors()]
    window = component.create()
    assert window is not None
    dialog = window.findChild(QObject, "exportDialog")
    button = window.findChild(QObject, "chooseExportDestination")

    def folder_picker(_caption, directory):
        assert os.environ["USERPROFILE"] == str(native)
        assert Path(directory) == downloads.resolve()
        return True, selected.pop(0)

    def save_picker(*_args):
        assert os.environ["USERPROFILE"] == str(native)
        return str(tmp_path / "manual.mp4"), ""

    def unchanged():
        assert {key: os.environ[key] for key in before} == before

    try:
        with (
            patch.dict(os.environ, before),
            patch.object(localization, "NATIVE_WINDOWS_USERPROFILE", str(native)),
            patch.object(localization, "_native_windows_folder_dialog", side_effect=folder_picker) as native_picker,
            patch.object(localization.QtFileDialog, "getSaveFileName", side_effect=save_picker),
            patch("haizflow.desktop.video_export_controller.desktop_settings.load_settings", return_value={}),
            patch("haizflow.desktop.video_export_controller.validate_export_destination",
                  side_effect=AssertionError("Picker must not scan batch destinations")),
        ):
            dialog.openForBatch(True)
            QTest.qWait(30)
            assert QMetaObject.invokeMethod(button, "clicked")
            assert dialog.property("destination") == output
            unchanged()
            # Cancel from a second project must keep its destination untouched.
            backend.project = "batch-2"
            dialog.openForBatch(True)
            assert QMetaObject.invokeMethod(button, "clicked")
            assert dialog.property("destination") == ""
            unchanged()
            # Existing files retain the QML confirmation, not a second native dialog.
            backend.collision = True
            assert QMetaObject.invokeMethod(button, "clicked")
            assert dialog.property("pendingFolder") == output
            assert dialog.property("destination") == ""
            confirm = window.findChild(QObject, "replaceBatchExportFiles")
            assert confirm.property("visible")
            confirm.close()
            unchanged()
            dialog.openForSelection(False)
            assert QMetaObject.invokeMethod(button, "clicked")
            assert dialog.property("destination") == str(tmp_path / "manual.mp4")
            unchanged()
            assert native_picker.call_count == backend.folder_calls == 3
    finally:
        window.close()
        window.deleteLater()
        component.deleteLater()
        engine.deleteLater()
        _APP.sendPostedEvents(None, QEvent.DeferredDelete)
        _APP.processEvents()


def test_no_qml_picker_can_bypass_the_localized_native_profile_wrapper():
    for path in QML_DIR.glob("*.qml"):
        source = path.read_text(encoding="utf-8")
        assert "import QtQuick.Dialogs" not in source, path
        assert "FolderDialog {" not in source, path
        assert "FileDialog {" not in source, path

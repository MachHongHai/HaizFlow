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
        self.conflict_checks = []
        self.starts = []
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
        return dict(projectKey=self.project, videos=[dict(videoId="a", name="a.mp4", status="failed"),
                                                   dict(videoId="b", name="b.mp4", status="done")],
                    presets=[dict(value="source", label="Original")], preset="source")

    @Slot(result="QVariantMap")
    def manualExportSettings(self):
        return dict(videoId="manual", filename="manual.mp4", presets=[], segments=[])

    @Slot(result=str)
    def chooseBatchExportFolder(self):
        self.folder_calls += 1
        return VideoExportController.choose_batch_folder(self.exporter)

    @Slot(str, "QVariantList", str, result="QVariantMap")
    def batchExportConflicts(self, project, videos, directory):
        self.conflict_checks.append((project, videos, directory))
        return {"b": "existing-identity"} if "b" in videos else {}

    @Slot(str, "QVariantList", str, str, bool, bool, "QVariantMap", result=bool)
    def processBatchTo(self, project, videos, _preset, directory, overwrite, _process, conflicts):
        self.starts.append((project, videos, directory, overwrite, conflicts))
        return True

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

    def folder_picker(kind, _caption, directory, *_args):
        assert kind == "folder"
        assert os.environ["USERPROFILE"] == str(portable)
        assert Path(directory) == downloads.resolve()
        path = selected.pop(0)
        return ([path] if path else []), ""

    def pick(kind, *args):
        if kind == "folder":
            return folder_picker(kind, *args)
        assert kind == "save"
        assert os.environ["USERPROFILE"] == str(portable)
        return [str(tmp_path / "manual.mp4")], ""

    def unchanged():
        assert {key: os.environ[key] for key in before} == before

    try:
        with (
            patch.dict(os.environ, before),
            patch.object(localization, "NATIVE_WINDOWS_USERPROFILE", str(native)),
            patch("haizflow.desktop.native_file_picker.shell_environment", return_value={"USERPROFILE":str(native)}),
            patch("haizflow.desktop.native_file_picker.pick", side_effect=pick) as native_picker,
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
            assert QMetaObject.invokeMethod(button, "clicked")
            assert dialog.property("destination") == output
            assert backend.conflict_checks == []
            assert not window.findChild(QObject, "replaceBatchExportFiles").property("visible")
            unchanged()
            dialog.openForSelection(False)
            assert QMetaObject.invokeMethod(button, "clicked")
            assert dialog.property("destination") == str(tmp_path / "manual.mp4")
            unchanged()
            assert native_picker.call_count == 4 and backend.folder_calls == 3
    finally:
        window.close()
        window.deleteLater()
        component.deleteLater()
        engine.deleteLater()
        _APP.sendPostedEvents(None, QEvent.DeferredDelete)
        _APP.processEvents()


def test_batch_retry_only_prompts_for_current_selected_destination_conflicts():
    global _APP
    _APP = QGuiApplication.instance() or QGuiApplication([])
    backend = Backend()
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("AppController", backend)
    engine.rootContext().setContextProperty("pickerBackend", backend)
    component = QQmlComponent(engine)
    component.setData(f'''import QtQuick
import QtQuick.Controls.Basic
import "{QML_DIR.as_uri()}"
ApplicationWindow {{ width: 970; height: 780; visible: true
    VideoExportDialog {{ objectName: "exportDialog"; controller: pickerBackend }}
}}'''.encode(), QUrl())
    assert component.isReady(), [error.toString() for error in component.errors()]
    window = component.create()
    dialog = window.findChild(QObject, "exportDialog")
    scope = window.findChild(QObject, "batchScope")
    start = window.findChild(QObject, "confirmVideoExport")
    replace = window.findChild(QObject, "replaceBatchExportFiles")
    accept_replace = window.findChild(QObject, "confirmBatchOverwrite")
    folder = "E:/output"

    def open_retry():
        dialog.openForBatch(True)
        dialog.setProperty("destination", folder)
        QTest.qWait(160)

    def click_start():
        assert QMetaObject.invokeMethod(start, "clicked")
        QTest.qWait(75)

    try:
        open_retry()
        click_start()
        assert backend.starts == [("batch-1", ["a"], folder, False, {})]
        assert not replace.property("visible")

        open_retry()
        scope.setProperty("scope", "all")
        click_start()
        assert backend.conflict_checks[-1] == ("batch-1", ["a", "b"], folder)
        assert replace.property("visible")
        assert len(backend.starts) == 1
        replace.close()
        QTest.qWait(160)
        scope.setProperty("scope", "selection")
        scope.setProperty("selectedIds", ["a"])
        click_start()
        assert backend.starts[-1] == ("batch-1", ["a"], folder, False, {})
        assert not replace.property("visible")

        open_retry()
        scope.setProperty("scope", "all")
        click_start()
        assert replace.property("visible")
        assert QMetaObject.invokeMethod(accept_replace, "clicked")
        assert backend.starts[-1] == ("batch-1", ["a", "b"], folder, True, {"b": "existing-identity"})
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

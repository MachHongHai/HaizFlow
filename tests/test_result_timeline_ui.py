"""Actual Qt UI for export ranges and the non-destructive result track."""
import os
from pathlib import Path

from PySide6.QtCore import QObject, Property, QMetaObject, Qt, QUrl, Slot, Q_ARG
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

QML_DIR = Path(__file__).parents[1] / "src/haizflow/desktop/qml"


class Backend(QObject):
    def __init__(self):
        super().__init__()
        self.calls = []

    @Property(bool, constant=True)
    def videoExportBusy(self):
        return False

    @Property("QVariantMap", constant=True)
    def manualEditorDocumentModel(self):
        return {"selectedTrackId": "result"}

    @Slot(result="QVariantMap")
    def manualExportSettings(self):
        return {"videoId": "video", "filename": "result.mp4", "preset": "source", "ready": True,
                "presets": [{"value": "source", "label": "Theo nguồn"}],
                "segments": [{"id": "first", "startMs": 0, "endMs": 2000},
                             {"id": "second", "startMs": 2000, "endMs": 4000}]}

    @Slot(str, str, str, bool, str, result=bool)
    def exportVideoSegmentTo(self, video_id, preset, destination, overwrite, segment):
        self.calls.append((video_id, preset, destination, overwrite, segment))
        return True


def test_result_track_and_export_range_selector(tmp_path):
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    backend = Backend()
    engine.rootContext().setContextProperty("testBackend", backend)
    engine.rootContext().setContextProperty("AppController", backend)
    component = QQmlComponent(engine)
    component.setData(f'''import QtQuick
import QtQuick.Controls.Basic
import "{QML_DIR.as_uri()}"
ApplicationWindow {{
    width: 1100; height: 740; visible: true; color: Theme.surface
    ManualEditorToolbar {{ width: parent.width; hasVideo: true; resultSelected: true; projectTitle: "Video dài" }}
    SubtitleTimeline {{
        y: 54; width: parent.width; height: 310; duration: 4; position: 2
        editorTracks: [{{track_id: "result", kind: "result", name: "Kết quả", visible: true}},
                       {{track_id: "source-video", kind: "source_video", name: "Video nguồn", visible: true}}]
        editorClips: [{{clip_id: "first", track_id: "result", kind: "result", enabled: true, start_ms: 0, duration_ms: 2000}},
                      {{clip_id: "second", track_id: "result", kind: "result", enabled: true, start_ms: 2000, duration_ms: 2000}}]
    }}
    VideoExportDialog {{ objectName: "exportDialog"; controller: testBackend }}
}}'''.encode(), QUrl())
    assert component.isReady(), [error.toString() for error in component.errors()]
    window = component.create()
    assert window is not None
    try:
        QTest.qWait(100)
        def visual_child(item, name):
            if item.objectName() == name:
                return item
            for child in item.childItems():
                if found := visual_child(child, name):
                    return found
            return None

        result_track = visual_child(window.contentItem(), "timelineTrack-result")
        source_header = visual_child(window.contentItem(), "timelineSourceHeader")
        assert result_track is not None and source_header is not None
        assert result_track.y() + result_track.height() <= source_header.y()
        dialog = window.findChild(QObject, "exportDialog")
        assert QMetaObject.invokeMethod(dialog, "openForSelection", Qt.DirectConnection, Q_ARG("QVariant", False))
        QTest.qWait(150)
        selector = window.findChild(QQuickItem, "exportRange")
        assert selector.property("count") == 3
        assert selector.property("currentIndex") == 0
        assert selector.property("currentValue") == ""
        selector.setProperty("currentIndex", 2)
        assert selector.property("currentValue") == "second"
        dialog.setProperty("destination", str(tmp_path / "out.mp4"))
        button = window.findChild(QObject, "confirmVideoExport")
        assert QMetaObject.invokeMethod(button, "clicked", Qt.DirectConnection)
        assert backend.calls[-1][-1] == "second"
        assert QMetaObject.invokeMethod(dialog, "openForSelection", Qt.DirectConnection, Q_ARG("QVariant", False))
        QTest.qWait(100)
        assert selector.property("currentIndex") == 0  # Default is always the entire video.
        if directory := os.getenv("HAIZFLOW_UI_CAPTURE_DIR"):
            Path(directory).mkdir(parents=True, exist_ok=True)
            assert window.grabWindow().save(str(Path(directory) / "result-export-dialog.png"))
            assert QMetaObject.invokeMethod(dialog, "close", Qt.DirectConnection)
            QTest.qWait(150)
            assert window.grabWindow().save(str(Path(directory) / "result-timeline.png"))
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()
        app.processEvents()

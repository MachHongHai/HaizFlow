"""Editor seek controls share the transport signal, without starting a job."""
import os
from pathlib import Path

from PySide6.QtCore import QMetaObject, QObject, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QSignalSpy, QTest


def test_four_seek_buttons_emit_offsets_and_fit_editor_toolbar():
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    qml_dir = Path(__file__).parents[1] / "src/haizflow/desktop/qml"
    component = QQmlComponent(engine)
    component.setData(f'''import QtQuick
import QtQuick.Controls.Basic
import "{qml_dir.as_uri()}"
ApplicationWindow {{
    width: 1100; height: 60; visible: true; color: Theme.surface
    ManualEditorToolbar {{
        objectName: "toolbar"; width: parent.width
        hasVideo: true; hasProject: true; projectTitle: "Video dài"
    }}
}}'''.encode(), QUrl())
    assert component.isReady(), [error.toString() for error in component.errors()]
    window = component.create()
    try:
        QTest.qWait(80)
        toolbar = window.findChild(QQuickItem, "toolbar")
        spy = QSignalSpy(toolbar.seekRequested)

        def visual_children(item):
            for child in item.childItems():
                yield child
                yield from visual_children(child)

        controls = {item.objectName(): item for item in visual_children(toolbar)}
        for index, offset in enumerate([-30, -15, 15, 30]):
            button = controls.get(f"manualSeek{offset}")
            assert button and button.property("visible") and button.property("enabled")
            assert button.property("offsetSeconds") == offset
            assert not button.property("showToolTip")
            assert button.property("toolTipText")  # Retain the accessible name.
            assert button.width() >= 40 and button.height() >= 40
            assert QMetaObject.invokeMethod(button, "clicked", Qt.DirectConnection)
            assert spy.at(index) == [offset]
        group = window.findChild(QObject, "manualHistoryGroup")
        export = window.findChild(QObject, "manualExportButton")
        group_end = group.mapToItem(window.contentItem(), group.width(), 0).x()
        export_start = export.mapToItem(window.contentItem(), 0, 0).x()
        assert group_end < export_start
        if directory := os.getenv("HAIZFLOW_UI_CAPTURE_DIR"):
            Path(directory).mkdir(parents=True, exist_ok=True)
            assert window.grabWindow().save(str(Path(directory) / "editor-seek-toolbar.png"))
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()
        app.processEvents()

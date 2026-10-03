"""Pointer selection and repeated-save regressions using the production QML."""

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlPropertyMap
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest


QML_DIR = Path(__file__).resolve().parents[1] / "src" / "haizflow" / "desktop" / "qml"


class SubtitleEditingUiTests(unittest.TestCase):
    __test__ = False  # Isolate Qt registration and engine lifetimes from other suites.

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlEngine()
        self.component = None
        self.window = None

    def tearDown(self):
        if self.window:
            self.window.close()
            self.window.deleteLater()
        self.engine.deleteLater()
        self.app.processEvents()

    def create_window(self, content):
        component = QQmlComponent(self.engine)
        self.component = component
        component.setData((f'''import QtQuick
import QtQuick.Controls.Basic
import "{QML_DIR.as_uri()}"
ApplicationWindow {{ id: root; width: 1120; height: 720; visible: true
{content}
}}''').encode("utf-8"), QUrl())
        self.assertTrue(component.isReady(), "\n".join(error.toString() for error in component.errors()))
        self.window = component.create()
        self.assertIsNotNone(self.window, "\n".join(error.toString() for error in component.errors()))
        QQmlEngine.setObjectOwnership(self.window, QQmlEngine.CppOwnership)
        QTest.qWait(80)
        return self.window

    def test_dialog_save_stays_open_and_footer_does_not_move_across_segments(self):
        window = self.create_window('''
QtObject {
    id: fakeController
    signal manualSubtitleSaved(string id, int revision, string requestId)
    signal manualSubtitleSaveFailed(string id, string requestId, string message)
}
ManualSubtitleEditorDialog {
    id: dialog
    controller: fakeController
    segment: ({segment_id: "first", text: "Đoạn đầu", revision: 1, start: 1, end: 2})
    segmentCount: 2
    selectedIndex: 0
    onCommitRequested: function(id, text, revision, request) {
        segment = Object.assign({}, segment, {text: text, revision: revision + 1});
        fakeController.manualSubtitleSaved(id, revision + 1, request);
    }
    Component.onCompleted: openForSelection()
}
''')
        dialog = window.findChild(QObject, "manualSubtitleEditorDialog")
        editor = window.findChild(QQuickItem, "manualSubtitleTextInput")
        save = window.findChild(QQuickItem, "manualSubtitleSaveButton")
        self.assertGreater(save.width(), 0)
        original_x = save.mapToScene(QPointF()).x()
        self.assertGreater(original_x, dialog.property("x") + dialog.property("width") * 0.7)
        for index, text in enumerate(("Nội dung mới tiếng Việt", "Chỉnh thêm lần nữa", "Phụ đề thứ hai")):
            if index == 2:
                dialog.setProperty("segment", {"segment_id": "second", "text": "Đoạn sau",
                                                "revision": 1, "start": 3, "end": 5})
                dialog.setProperty("selectedIndex", 1)
                QTest.qWait(40)
            editor.setProperty("text", text)
            QTest.qWait(40)
            self.assertAlmostEqual(save.mapToScene(QPointF()).x(), original_x, delta=1)
            save.clicked.emit()
            QTest.qWait(60)
            self.assertTrue(dialog.property("visible"))
            self.assertEqual(dialog.property("segment").toVariant()["text"], text)
            self.assertEqual(editor.property("text"), text)
            self.assertAlmostEqual(save.mapToScene(QPointF()).x(), original_x, delta=1)
        save.clicked.emit()  # Saving unchanged text must also stay open.
        QTest.qWait(40)
        self.assertTrue(dialog.property("visible"))

    def test_timeline_mouse_selection_updates_inspector_and_clip_selection_uses_stable_id(self):
        source = (QML_DIR / "ManualWorkspace.qml").read_text(encoding="utf-8")
        functions = []
        for name in ("selectSubtitle", "selectEditorClip", "selectSubtitleInDialog"):
            match = re.search(r"    function " + name + r"\([^)]*\) \{.*?\n    \}", source, re.S)
            self.assertIsNotNone(match)
            functions.append(match.group().replace("AppController", "fakeController"))
        selection_handler = re.search(r"    onSelectedEditorClipChanged: \{.*?\n    \}", source, re.S)
        self.assertIsNotNone(selection_handler)
        functions.append(selection_handler.group())
        model = QQmlPropertyMap()
        model.insert("selectedTrackId", "subtitles")
        controller = QQmlPropertyMap()
        controller.insert("manualEditorDocumentModel", model)
        self.engine.rootContext().setContextProperty("AppController", controller)
        window = self.create_window('''
property var segments: [
    {segment_id: "first", text: "Đoạn đầu", start: 0, end: 2},
    {segment_id: "second", text: "Đoạn sau", start: 3, end: 5}]
property int selectedSubtitleIndex: -1
property int selectedStageIndex: 0
property int subtitleToolIndex: 2
property bool watermarkTransformActive: false
property bool subtitleTransformActive: false
readonly property var selectedEditorClip: fakeController.manualEditorDocumentModel.selectedClip
readonly property string inspectorText: selectedSubtitleIndex >= 0 ? segments[selectedSubtitleIndex].text : ""
function activatePanel(panel, side) {}
QtObject { id: stageInspector; function dismissTextEditor() {} }
QtObject { id: comparePreview; function seekTo(seconds) {} }
QtObject {
    id: fakeController
    property string editingId: ""
    property QtObject manualEditorDocumentModel: QtObject {
        property var selectedClipIds: []
        property var selectedClip: ({})
        function selectClip(id, additive) {
            selectedClipIds = [id];
            selectedClip = {track_id: "subtitles", segment_id: id.slice(9)};
        }
    }
    function beginManualSubtitleEdit(id) { editingId = id; }
}
function selectSecondClip() { root.selectEditorClip("subtitle-second"); }
function selectFirstDirectly() { fakeController.manualEditorDocumentModel.selectClip("subtitle-first", false); }
SubtitleTimeline {
    id: timeline
    anchors.fill: parent
    segments: root.segments
    selectedIndex: root.selectedSubtitleIndex
    duration: 6
    onSegmentSelected: function(index) { root.selectSubtitle(index, true); }
    onSegmentFocused: function(index) { root.selectSubtitle(index, true); }
}
''' + "\n".join(functions))
        for index, expected in ((1, "Đoạn sau"), (0, "Đoạn đầu"), (1, "Đoạn sau")):
            def find_visual(item, name):
                if item.objectName() == name:
                    return item
                for child in item.childItems():
                    found = find_visual(child, name)
                    if found is not None:
                        return found
                return None

            clip = find_visual(window.contentItem(), f"subtitleTimelineClip-{index}")
            self.assertIsNotNone(clip)
            point = clip.mapToScene(QPointF(clip.width() / 2, clip.height() / 2)).toPoint()
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
            QTest.qWait(40)
            self.assertEqual(window.property("selectedSubtitleIndex"), index)
            self.assertEqual(window.property("inspectorText"), expected)
        window.setProperty("selectedSubtitleIndex", 0)
        window.selectSecondClip()
        self.assertEqual(window.property("selectedSubtitleIndex"), 1)
        self.assertEqual(window.property("inspectorText"), "Đoạn sau")
        window.selectFirstDirectly()
        self.assertEqual(window.property("selectedSubtitleIndex"), 0)
        self.assertEqual(window.property("inspectorText"), "Đoạn đầu")


def test_subtitle_editing_in_isolated_qt_process():
    completed = subprocess.run([sys.executable, str(Path(__file__).resolve())],
                               capture_output=True, text=True, timeout=45)
    assert completed.returncode == 0, completed.stdout + completed.stderr


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

"""Exercise the docked caption editor with real QML and async save signals."""

import os
import subprocess
import sys
import unittest
from pathlib import Path

from PySide6.QtCore import Property, QObject, QPointF, Qt, QTranslator, QUrl, Signal, Slot
from PySide6.QtGui import QFontDatabase, QGuiApplication, QInputMethodEvent
from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

QML_DIR = Path(__file__).resolve().parents[1] / "src/haizflow/desktop/qml"


class CaptionController(QObject):
    manualSubtitleSaved = Signal(str, int, str)
    manualSubtitleSaveFailed = Signal(str, str, str)

    def __init__(self):
        super().__init__()
        self.requests = []
        self.style_calls = []
        self.reset_calls = []
        self.actions = []
        self.replacements = []

    @Property("QVariantMap", constant=True)
    def manualEditorDocumentModel(self):
        return {"defaultSubtitleStyle": {}, "subtitleSegments": [
            {"segment_id": "first", "revision": 1, "start": 0, "end": 2, "text": "Cảm ơn mẹ."},
            {"segment_id": "second", "revision": 1, "start": 2, "end": 4, "text": "Chúc ngủ ngon."},
        ]}

    @Slot(str, str, bool, bool, str, result=int)
    def replaceSubtitleText(self, query, replacement, case_sensitive, replace_all, segment):
        self.replacements.append((query, replacement, case_sensitive, replace_all, segment))
        return 2 if replace_all else 1

    @Slot(str, str, int, str, result=bool)
    def saveManualSubtitleText(self, segment, text, revision, request):
        self.requests.append((segment, text, revision, request))
        return True

    @Slot("QVariantList", "QVariantMap", str, result=bool)
    def applyTextStyle(self, targets, patch, scope):
        self.style_calls.append((targets, patch, scope))
        return True

    @Slot("QVariantList", result=bool)
    def resetTextStyleOverrides(self, targets):
        self.reset_calls.append(targets)
        return True

    @Slot(str, int, result=str)
    def splitSubtitleSegment(self, segment, position):
        self.actions.append(("split", segment, position))
        return "new-cue"

    @Slot(str, result=bool)
    def mergeSubtitleWithNext(self, segment):
        self.actions.append(("merge", segment))
        return True

    @Slot(str, result=bool)
    def deleteSubtitleSegment(self, segment):
        self.actions.append(("delete", segment))
        return True


class SubtitleCueEditorUiTests(unittest.TestCase):
    __test__ = False

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QGuiApplication.instance() or QGuiApplication([])
        if os.environ.get("HAIZFLOW_UI_PREVIEWS"):
            for name in ("SegUIVar.ttf", "SegoeIcons.ttf"):
                QFontDatabase.addApplicationFont(str(Path("C:/Windows/Fonts") / name))

    def setUp(self):
        self.engine = QQmlEngine()
        self.controller = CaptionController()
        self.engine.rootContext().setContextProperty("AppController", self.controller)
        self.messages = []
        self.engine.warnings.connect(lambda errors: self.messages.extend(e.toString() for e in errors))
        self.window = None

    def tearDown(self):
        if self.window:
            self.window.close()
            self.window.deleteLater()
        self.engine.deleteLater()
        self.app.processEvents()
        self.assertEqual(self.messages, [])

    def create_window(self, content, width=420, height=600):
        self.component = QQmlComponent(self.engine)
        self.component.setData((f'''import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "{QML_DIR.as_uri()}"
ApplicationWindow {{ id: window; width: {width}; height: {height}; visible: true; color: Theme.window
{content}
}}''').encode(), QUrl())
        self.assertTrue(self.component.isReady(), "\n".join(e.toString() for e in self.component.errors()))
        self.window = self.component.create()
        self.assertIsNotNone(self.window)
        QQmlEngine.setObjectOwnership(self.window, QQmlEngine.CppOwnership)
        QTest.qWait(60)
        return self.window

    def evaluate(self, code):
        expression = QQmlExpression(QQmlEngine.contextForObject(self.window), self.window, code)
        result = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return result

    def child(self, name) -> QQuickItem:
        def find(item):
            if item.objectName() == name:
                return item
            for child in item.childItems():
                result = find(child)
                if result is not None:
                    return result
            return None
        return find(self.window.contentItem())

    def click(self, item):
        point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, point)
        QTest.qWait(30)

    def create_manual(self):
        return self.create_window('''
QtObject {
    id: inspector
    property bool editable: true
    property bool taskQueued: false
    property bool expandedSubtitleEditorVisible: false
    property var expandedRequests: []
    property real panelBodyHeight: window.height - 24
    property real playheadSeconds: 1
    property int selectedSubtitleIndex: 0
    property var subtitleSegments: [
        {segment_id: "first", revision: 1, start: 0, end: 2, text: "Cảm ơn mẹ."},
        {segment_id: "second", revision: 1, start: 2, end: 4, text: "Chúc ngủ ngon."},
        {segment_id: "third", revision: 1, start: 4, end: 8, text: "Chúng sẽ như thế này mãi sao?"}]
    readonly property var selectedSubtitle: subtitleSegments[selectedSubtitleIndex] || null
    property var subtitleDrafts: ({})
    property var selectedEditorClip: ({warnings: [], resolved_style: {}})
    function rememberSubtitleDraft(id, text, revision) { subtitleDrafts[id] = {text: text, revision: revision}; }
    function clearSubtitleDraft(id) { delete subtitleDrafts[id]; }
    function subtitleDialogSelectionRequested(index) { panel.dismissEditor(); selectedSubtitleIndex = index; }
    function openExpandedTextEditor(findReplace) { expandedRequests = expandedRequests.concat([findReplace]); }
    function settingsCommitted() {}
}
ManualSubtitleToolPanel { id: panel; objectName: "panel"; x: 12; y: 12; width: window.width - 24; inspector: inspector }
''')

    def test_manual_drafts_survive_selection_and_async_save_failure_retry(self):
        self.create_manual()
        editor = self.child("manualSubtitleTextInput")
        save = self.child("manualInlineSubtitleSaveButton")
        editor.setProperty("text", "Cảm ơn mẹ rất nhiều.")
        preview = os.environ.get("HAIZFLOW_UI_PREVIEWS")
        if preview:
            self.window.grabWindow().save(str(Path(preview) / "subtitle-manual-initial.png"))
        self.click(self.child("subtitleCue_1"))
        self.assertEqual(editor.property("text"), "Chúc ngủ ngon.",
                         str(self.evaluate('inspector.selectedSubtitleIndex')))
        self.click(self.child("subtitleCue_0"))
        self.assertEqual(editor.property("text"), "Cảm ơn mẹ rất nhiều.")
        self.assertTrue(save.isEnabled())
        self.click(save)
        segment, text, revision, request = self.controller.requests[-1]
        self.assertEqual((segment, text, revision), ("first", "Cảm ơn mẹ rất nhiều.", 1))
        self.assertFalse(self.child("subtitleCue_1").isEnabled())
        self.controller.manualSubtitleSaveFailed.emit(segment, request, "Không ghi được tệp")
        QTest.qWait(20)
        self.assertEqual(editor.property("text"), text)
        self.assertTrue(save.isEnabled())
        self.click(save)
        request = self.controller.requests[-1][-1]
        self.evaluate('''inspector.subtitleSegments = inspector.subtitleSegments.map((s, i) =>
            i === 0 ? Object.assign({}, s, {text: "Cảm ơn mẹ rất nhiều.", revision: 2}) : s)''')
        self.controller.manualSubtitleSaved.emit(segment, 2, request)
        QTest.qWait(30)
        self.assertFalse(save.isEnabled())
        self.assertTrue(self.child("subtitleCue_1").isEnabled())
        self.click(self.child("subtitleCue_1"))
        self.click(self.child("subtitleCue_0"))
        self.assertEqual(editor.property("text"), text)
        self.assertFalse(save.isEnabled())

    def test_manual_layout_and_style_tab_preserve_live_draft(self):
        window = self.create_manual()
        editor = self.child("manualSubtitleTextInput")
        editor.setProperty("text", "Bản nháp tiếng Việt")
        for width, height in ((340, 480), (420, 600), (520, 800)):
            window.setWidth(width)
            window.setHeight(height)
            QTest.qWait(30)
            save = self.child("manualInlineSubtitleSaveButton")
            self.assertLessEqual(save.mapToScene(QPointF(save.width(), save.height())).x(), width)
            self.assertLessEqual(save.mapToScene(QPointF(save.width(), save.height())).y(), height)
            self.assertGreater(self.child("subtitleCueView").height(), 180)
            self.assertIsNone(self.child("subtitleStyleScope"))
        self.evaluate('panel.currentTab = "style"')
        QTest.qWait(30)
        self.assertFalse(editor.isVisible())
        self.evaluate('panel.currentTab = "content"')
        QTest.qWait(30)
        self.assertEqual(editor.property("text"), "Bản nháp tiếng Việt")
        preview = os.environ.get("HAIZFLOW_UI_PREVIEWS")
        if preview:
            window.setWidth(420)
            window.setHeight(640)
            QTest.qWait(30)
            window.grabWindow().save(str(Path(preview) / "subtitle-manual-panel.png"))

    def test_large_list_is_virtualized_and_search_wraps_without_resetting_selection(self):
        self.create_window('''
SubtitleCueList {
    id: cues; objectName: "cues"; anchors.fill: parent; anchors.margins: 12
    segments: Array.from({length: 5000}, (_, i) => ({start: i * 2, end: i * 2 + 2,
        text: i === 4321 ? "Cảm ơn mẹ" : "Phụ đề " + i}))
    onSegmentSelected: index => selectedIndex = index
}
''')
        def count_rows(item):
            return int(item.objectName().startswith("subtitleCue_")) + sum(count_rows(c) for c in item.childItems())
        self.assertLess(count_rows(self.window.contentItem()), 40)
        search = self.child("subtitleCueSearch")
        search.setProperty("text", "CẢM ƠN")
        self.evaluate('cues.findNext()')
        QTest.qWait(40)
        self.assertEqual(self.child("cues").property("selectedIndex"), 4321)
        self.assertIsNotNone(self.child("subtitleCue_4321"))
        for height in (600, 360, 720):
            self.window.setHeight(height)
            QTest.qWait(30)
            row = self.child("subtitleCue_4321")
            view = self.child("subtitleCueView")
            self.assertGreaterEqual(row.mapToScene(QPointF()).y(), view.mapToScene(QPointF()).y() - 1)
            self.assertLessEqual(row.mapToScene(QPointF(0, row.height())).y(),
                                 view.mapToScene(QPointF(0, view.height())).y() + 1)
        self.evaluate('cues.findNext(-1)')
        self.assertEqual(self.child("cues").property("selectedIndex"), 4321)
        search.setProperty("text", "không có")
        self.evaluate('cues.findNext()')
        self.assertEqual(self.child("cues").property("searchStatus"), "Không tìm thấy")
        self.evaluate('cues.segments = []')
        QTest.qWait(20)
        self.assertEqual(self.child("subtitleCueView").property("count"), 0)

    def test_style_always_targets_entire_project_without_scope_controls(self):
        self.create_manual()
        self.evaluate('panel.currentTab = "style"')
        QTest.qWait(30)
        self.assertIsNone(self.child("subtitleStyleScope"))
        self.click(self.child("compactBoldToggle"))
        self.assertEqual(self.controller.style_calls[-1], ([], {"font_weight": 700}, "project"))
        self.click(self.child("compactItalicToggle"))
        self.assertEqual(self.controller.style_calls[-1], ([], {"italic": True}, "project"))
        self.assertEqual(self.controller.requests, [])

    def test_caption_menu_uses_existing_split_merge_delete_and_toggles_closed(self):
        self.create_manual()
        button = self.child("manualSubtitleActionsButton")
        menu = self.window.findChild(QObject, "manualSubtitleActionsMenu")
        self.click(button)
        self.assertTrue(menu.property("visible"))
        self.assertGreater(menu.property("width"), 160)
        split = self.window.findChild(QObject, "manualSubtitleSplitAction")
        self.assertTrue(split.property("enabled"))
        split.triggered.emit()
        self.assertEqual(self.controller.actions[-1], ("split", "first", 1000))
        self.evaluate('panel.dismissEditor()')
        # Close the menu before exercising the same trigger again.
        menu.close()
        self.click(button)
        self.assertTrue(menu.property("visible"))
        self.click(button)
        self.assertFalse(menu.property("visible"))
        self.window.findChild(QObject, "manualSubtitleMergeAction").triggered.emit()
        self.window.findChild(QObject, "manualSubtitleDeleteAction").triggered.emit()
        self.assertEqual(self.controller.actions[-2:], [("merge", "first"), ("delete", "first")])
        self.child("manualSubtitleTextInput").setProperty("text", "Chưa lưu")
        self.assertTrue(button.isEnabled())
        self.assertFalse(split.property("enabled"))

    def test_expand_is_a_visible_icon_outside_the_actions_menu(self):
        self.create_manual()
        expand = self.child("manualSubtitleExpandButton")
        self.assertTrue(expand.isVisible())
        self.assertEqual(expand.property("iconName"), "fullscreen")
        self.assertEqual(expand.property("toolTipText"), "Mở rộng")
        self.assertGreaterEqual(expand.width(), 30)
        menu = self.window.findChild(QObject, "manualSubtitleActionsMenu")
        self.assertFalse(menu.property("visible"))
        self.click(expand)
        count = self.evaluate('inspector.expandedRequests.length')
        find_replace = self.evaluate('inspector.expandedRequests[0]')
        self.assertEqual(count[0] if isinstance(count, tuple) else count, 1)
        self.assertEqual(find_replace[0] if isinstance(find_replace, tuple) else find_replace, False)
        self.assertFalse(menu.property("visible"))
        for width in (300, 380, 460):
            self.window.setWidth(width)
            QTest.qWait(20)
            save = self.child("manualInlineSubtitleSaveButton")
            self.assertLess(expand.mapToScene(QPointF(expand.width(), 0)).x(), save.mapToScene(QPointF()).x())
            self.assertLessEqual(save.mapToScene(QPointF(save.width(), 0)).x(), width)

    def test_keyboard_find_and_adjacent_cues_preserve_drafts(self):
        self.create_manual()
        editor = self.child("manualSubtitleTextInput")
        editor.forceActiveFocus()
        editor.setProperty("text", "Bản nháp")
        QTest.keyClick(self.window, Qt.Key_Down, Qt.AltModifier)
        QTest.qWait(30)
        self.assertEqual(editor.property("text"), "Chúc ngủ ngon.")
        QTest.keyClick(self.window, Qt.Key_Up, Qt.AltModifier)
        QTest.qWait(30)
        self.assertEqual(editor.property("text"), "Bản nháp")
        QTest.keyClick(self.window, Qt.Key_F, Qt.ControlModifier)
        self.assertTrue(self.child("subtitleCueSearch").hasActiveFocus())

    def test_expanded_and_docked_editors_cannot_accept_each_others_save_signals(self):
        self.create_window('''
SubtitleTextEditor {
    id: first; objectName: "firstEditor"; x: 0; width: 200; height: 300
    segmentId: "same-cue"; savedText: "Bản gốc"
    onCommitRequested: (id, text, revision, request) =>
        AppController.saveManualSubtitleText(id, text, revision, request)
}
SubtitleTextEditor {
    id: second; objectName: "secondEditor"; x: 210; width: 200; height: 300
    segmentId: "same-cue"; savedText: "Bản gốc"
    onCommitRequested: (id, text, revision, request) =>
        AppController.saveManualSubtitleText(id, text, revision, request)
}
''')
        first = self.child("firstEditor")
        second = self.child("secondEditor")
        first.findChild(QQuickItem, "manualSubtitleTextInput").setProperty("text", "Bản thứ nhất")
        second.findChild(QQuickItem, "manualSubtitleTextInput").setProperty("text", "Bản thứ hai")
        self.evaluate('first.apply(); second.apply()')
        QTest.qWait(20)
        one, two = self.controller.requests
        self.assertNotEqual(one[-1], two[-1])
        self.controller.manualSubtitleSaved.emit("same-cue", 1, one[-1])
        self.assertEqual(first.property("saveStatus"), "saved")
        self.assertEqual(second.property("saveStatus"), "saving")
        self.controller.manualSubtitleSaved.emit("same-cue", 2, two[-1])
        self.assertEqual(second.property("saveStatus"), "saved")
        self.assertEqual(first.property("committedText"), "Bản thứ nhất")
        self.assertEqual(second.property("committedText"), "Bản thứ hai")

    def test_save_acknowledgment_preserves_text_typed_while_write_is_pending(self):
        self.create_manual()
        editor = self.child("manualSubtitleTextInput")
        editor.setProperty("text", "Nội dung đã gửi")
        self.click(self.child("manualInlineSubtitleSaveButton"))
        segment, _, _, request = self.controller.requests[-1]
        editor.setProperty("text", "Tiếp tục gõ trong khi đang lưu")
        self.controller.manualSubtitleSaved.emit(segment, 2, request)
        QTest.qWait(20)
        self.assertEqual(editor.property("text"), "Tiếp tục gõ trong khi đang lưu")
        self.assertTrue(self.child("manualInlineSubtitleSaveButton").isEnabled())

    def test_opening_expanded_editor_suspends_docked_save_callbacks_until_handoff(self):
        self.create_manual()
        editor = self.child("manualSubtitleTextInput")
        editor.setProperty("text", "Bản gửi từ panel")
        self.click(self.child("manualInlineSubtitleSaveButton"))
        segment, _, _, request = self.controller.requests[-1]
        self.evaluate('inspector.expandedSubtitleEditorVisible = true')
        self.controller.manualSubtitleSaved.emit(segment, 2, request)
        inline = self.child("manualInlineSubtitleEditor")
        self.assertEqual(inline.property("saveStatus"), "saving")
        self.assertEqual(inline.property("committedText"), "Cảm ơn mẹ.")
        self.evaluate('''
            inspector.subtitleSegments = inspector.subtitleSegments.map((s, i) => i === 0
                ? Object.assign({}, s, {text: "Bản gửi từ panel", revision: 2}) : s);
            inspector.subtitleDrafts.first = {text: "Bản nháp trong cửa sổ mở rộng", revision: 2};
            inspector.expandedSubtitleEditorVisible = false;
            panel.reloadText();
        ''')
        self.assertEqual(editor.property("text"), "Bản nháp trong cửa sổ mở rộng")
        self.assertTrue(self.child("manualInlineSubtitleSaveButton").isEnabled())
        self.controller.manualSubtitleSaveFailed.emit(segment, request, "Late completion")
        self.assertEqual(inline.property("saveStatus"), "dirty")

    def test_caption_browser_uses_english_translations(self):
        translator = QTranslator()
        self.assertTrue(translator.load(str(QML_DIR.parent / "translations/haizflow_en.qm")))
        self.app.installTranslator(translator)
        try:
            self.create_window('SubtitleCueList { anchors.fill: parent }')
            self.assertEqual(self.child("subtitleCueSearch").property("placeholderText"), "Find captions…")
        finally:
            self.app.removeTranslator(translator)

    def test_auto_editor_keeps_composition_and_commits_before_explicit_selection(self):
        self.create_window('''
property var edits: []
SubtitleEditorInspector {
    id: inspector; anchors.fill: parent; anchors.margins: 12
    segments: [{start: 0, end: 2, text: "Cảm ơn mẹ"}, {start: 2, end: 4, text: "Chúc ngủ ngon"}]
    segment: segments[selectedIndex] || null
    segmentCount: segments.length; selectedIndex: 0
    onTextCommitted: value => {
        window.edits = window.edits.concat([value]);
        segments = segments.map((s, i) => i === selectedIndex ? Object.assign({}, s, {text: value}) : s);
    }
    onSegmentSelected: index => { commitPendingText(); selectedIndex = index; setEditorText(segment.text); }
    Component.onCompleted: setEditorText(segment.text)
}
''')
        editor = self.child("autoSubtitleTextInput")
        editor.forceActiveFocus()
        event = QInputMethodEvent("ngủ", [])
        self.app.sendEvent(editor, event)
        QTest.qWait(350)
        self.assertTrue(editor.property("inputMethodComposing"))
        self.assertEqual(self.window.property("edits").toVariant(), [])
        event = QInputMethodEvent()
        event.setCommitString(" ngon")
        self.app.sendEvent(editor, event)
        self.click(self.child("subtitleCue_1"))
        self.assertEqual(editor.property("text"), "Chúc ngủ ngon")
        self.assertEqual(len(self.window.property("edits").toVariant()), 1)

    def test_expanded_find_replace_never_overlaps_editor_or_footer(self):
        window = self.create_window('''
ManualSubtitleEditorDialog {
    id: dialog
    segment: ({segment_id: "first", revision: 1, start: 0, end: 2, text: "Cảm ơn mẹ."})
    selectedIndex: 0; segmentCount: 3
    Component.onCompleted: { openForSelection(); showFindReplace(true); }
}
''', width=1120, height=720)
        for width, height in ((1120, 720), (900, 600), (720, 480), (1440, 900)):
            window.setWidth(width)
            window.setHeight(height)
            QTest.qWait(50)
            editor = self.child("manualSubtitleTextInput")
            find = self.child("subtitleFindReplaceScroll")
            footer = self.child("appDialogFooter")
            save = self.child("manualSubtitleSaveButton")
            editor_top = editor.mapToScene(QPointF()).y()
            editor_bottom = editor.mapToScene(QPointF(0, editor.height())).y()
            self.assertGreaterEqual(editor_top, find.mapToScene(QPointF(0, find.height())).y())
            self.assertLessEqual(editor_bottom, footer.mapToScene(QPointF()).y())
            self.assertLessEqual(save.mapToScene(QPointF(0, save.height())).y(), height)
        preview = os.environ.get("HAIZFLOW_UI_PREVIEWS")
        if preview:
            window.setWidth(1120)
            window.setHeight(720)
            QTest.qWait(50)
            window.grabWindow().save(str(Path(preview) / "subtitle-find-replace-fixed.png"))

    def test_expanded_find_and_replace_dispatches_correct_caption_scope(self):
        self.create_window('''
ManualSubtitleEditorDialog {
    id: dialog
    segment: AppController.manualEditorDocumentModel.subtitleSegments[selectedIndex]
    selectedIndex: 0; segmentCount: 2
    onSelectionRequested: index => selectedIndex = index
    Component.onCompleted: { openForSelection(); showFindReplace(true); }
}
''', width=1120, height=720)
        self.child("subtitleFindField").setProperty("text", "ngủ")
        self.evaluate('dialog.findNext()')
        QTest.qWait(30)
        self.assertEqual(self.child("manualSubtitleTextInput").property("text"), "Chúc ngủ ngon.")
        self.child("subtitleReplaceField").setProperty("text", "ngủ thật")
        self.evaluate('dialog.replaceText(false)')
        self.assertEqual(self.controller.replacements[-1], ("ngủ", "ngủ thật", False, False, "second"))
        self.evaluate('dialog.replaceText(true)')
        self.assertEqual(self.controller.replacements[-1], ("ngủ", "ngủ thật", False, True, ""))

    def test_review_workspace_keeps_preview_list_and_timeline_visible_when_resized(self):
        window = self.create_window('''
SubtitleEditorWorkspace {
    id: workspace; objectName: "workspace"; anchors.fill: parent; anchors.margins: 12
    segments: Array.from({length: 24}, (_, i) => ({start: i * 3, end: i * 3 + 3,
        text: ["Cảm ơn mẹ rất nhiều.", "Chúc ngủ ngon.", "Chúng sẽ như thế này mãi sao?"][i % 3]}))
    selectedIndex: 1; selectedSegment: segments[selectedIndex]
    duration: 72; position: 3; canCommit: true; primaryText: qsTr("Lưu phụ đề")
    onSegmentSelected: index => selectedIndex = index
    Component.onCompleted: setEditorText(selectedSegment.text)
}
''', width=1440, height=900)
        for width, height in ((1120, 720), (1440, 900), (1706, 960)):
            window.setWidth(width)
            window.setHeight(height)
            QTest.qWait(40)
            editor = self.child("autoSubtitleTextInput")
            view = self.child("subtitleCueView")
            self.assertGreater(view.height(), 90)
            self.assertGreater(view.width(), 250)
            self.assertGreater(editor.height(), 80)
            bottom = editor.mapToScene(QPointF(editor.width(), editor.height()))
            self.assertLessEqual(bottom.x(), width)
            self.assertLess(bottom.y(), height - 200)
        preview = os.environ.get("HAIZFLOW_UI_PREVIEWS")
        if preview:
            window.setWidth(1440)
            window.setHeight(900)
            QTest.qWait(40)
            window.grabWindow().save(str(Path(preview) / "subtitle-auto-workspace.png"))


def test_subtitle_cue_editor_in_isolated_process():
    result = subprocess.run([sys.executable, str(Path(__file__).resolve())],
                            capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

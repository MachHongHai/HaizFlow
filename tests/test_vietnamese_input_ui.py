"""Real Qt text/preedit/cursor regressions, isolated from other QML engines.

QInputMethodEvent exercises the editor protocol, not the Windows Telex driver.
"""

import os
import subprocess
import sys
import unittest
import unicodedata
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QFontDatabase, QGuiApplication, QInputMethodEvent
from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from hflow.desktop.input_method_commit_filter import InputMethodCommitFilter

QML_DIR = Path(__file__).resolve().parents[1] / "src/hflow/desktop/qml"


class VietnameseInputUiTests(unittest.TestCase):
    __test__ = False

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QGuiApplication.instance() or QGuiApplication([])
        for name in ("segoeui.ttf", "SegUIVar.ttf"):
            path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
            if path.is_file():
                QFontDatabase.addApplicationFont(str(path))

    def setUp(self):
        self.engine = QQmlEngine()
        self.window = None
        self.commits = 0

        def finish_preedit():
            field = self.window.activeFocusItem()
            self.commits += 1
            self.send_commit(field, field.property("preeditText"))

        self.filter = InputMethodCommitFilter(commit_callback=finish_preedit)
        self.app.installEventFilter(self.filter)

    def tearDown(self):
        self.app.removeEventFilter(self.filter)
        if self.window:
            self.window.close()
            self.window.deleteLater()
        self.engine.deleteLater()
        self.app.processEvents()

    def create_window(self, body):
        self.component = QQmlComponent(self.engine)
        self.component.setData((f'''import QtQuick
import QtQuick.Controls.Basic
import "{QML_DIR.as_uri()}"
ApplicationWindow {{ id: root; width: 800; height: 550; visible: true; color: Theme.window
{body}
}}''').encode(), QUrl())
        self.assertTrue(self.component.isReady(), "\n".join(e.toString() for e in self.component.errors()))
        self.window = self.component.create()
        self.assertIsNotNone(self.window)
        self.window.requestActivate()
        QTest.qWait(50)
        return self.window

    def expression(self, obj, code):
        expr = QQmlExpression(self.engine.rootContext(), obj, code)
        result, _ = expr.evaluate()
        self.assertFalse(expr.hasError(), expr.error().toString())
        return result

    @classmethod
    def send_commit(cls, field, text, start=0, length=0):
        event = QInputMethodEvent()
        event.setCommitString(text, start, length)
        cls.app.sendEvent(field, event)

    @classmethod
    def preedit(cls, field, text):
        cls.app.sendEvent(field, QInputMethodEvent(text, []))

    def click_cursor(self, field, position):
        QTest.qWait(25)
        rect = self.expression(field, f"positionToRectangle({position})")
        current = self.expression(field, "positionToRectangle(cursorPosition)")
        cursor = field.property("cursorRectangle")
        rect.translate(cursor.x() - current.x(), cursor.y() - current.y())
        point = field.mapToScene(QPointF(rect.x() + 1, rect.y() + rect.height() / 2)).toPoint()
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, point)

    def test_arrow_and_mouse_reposition_commit_one_word_once(self):
        for control in ("AppTextField", "AppTextArea", "AutoSaveTextField"):
            with self.subTest(control=control):
                if self.window:
                    self.window.close()
                    self.window.deleteLater()
                    self.app.processEvents()
                self.create_window(f'{control} {{ objectName: "field"; x: 20; y: 20; width: 620; height: 160 }}')
                field = self.window.findChild(QQuickItem, "field")
                QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, QPoint(60, 40))
                field.setProperty("text", "Xin chào Việt Nam")
                field.setProperty("cursorPosition", 4)
                self.preedit(field, "tiếng ")
                before = self.commits
                QTest.keyClick(self.window, Qt.Key_Left)
                self.assertEqual(field.property("text"), "Xin tiếng chào Việt Nam")
                self.assertEqual(self.commits, before + 1)
                QTest.keyClick(self.window, Qt.Key_Right)
                self.click_cursor(field, 0)
                self.assertEqual(self.commits, before + 1)
                self.assertEqual(field.property("cursorPosition"), 0)
                self.preedit(field, "Đầu ")
                self.click_cursor(field, len(field.property("text")))
                self.assertEqual(field.property("text"), "Đầu Xin tiếng chào Việt Nam")
                self.assertEqual(self.commits, before + 2)
                self.assertFalse(field.property("inputMethodComposing"))
                self.send_commit(field, "!")
                self.assertEqual(field.property("text"), "Đầu Xin tiếng chào Việt Nam!")

    def test_vietnamese_replacements_unicode_and_plain_text_preserve_content(self):
        self.create_window('AppTextArea { objectName: "field"; x: 20; y: 20; width: 620; height: 160 }')
        field = self.window.findChild(QQuickItem, "field")
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, QPoint(60, 40))
        self.send_commit(field, "Tieng")
        self.send_commit(field, "Tiếng", -5, 5)
        self.assertEqual(field.property("text"), "Tiếng")
        value = " Việt <b>không phải HTML</b>\n" + unicodedata.normalize("NFD", "Đường phố")
        self.send_commit(field, value)
        self.assertEqual(field.property("text"), "Tiếng" + value)
        before = self.commits
        for key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Home, Qt.Key_End):
            QTest.keyClick(self.window, key)
        self.assertEqual(self.commits, before)

    def test_auto_subtitle_does_not_save_or_reinstall_live_composition(self):
        self.create_window('''
property int saves: 0
SubtitleEditorInspector {
    id: inspector; objectName: "inspector"; x: 20; y: 20; width: 650; height: 360
    segment: ({text: "Xin "}); selectedIndex: 0; segmentCount: 1
    onTextCommitted: function(value) {
        root.saves++; segment = ({text: value}); setEditorText(value);
    }
    Component.onCompleted: setEditorText("Xin ")
}''')
        field = self.window.findChild(QQuickItem, "autoSubtitleTextInput")
        inspector = self.window.findChild(QQuickItem, "inspector")
        field.forceActiveFocus()
        field.setProperty("cursorPosition", 4)
        self.preedit(field, "Việt")
        self.expression(inspector, 'setEditorText("Xin ")')
        QTest.qWait(400)
        self.assertTrue(field.property("inputMethodComposing"))
        self.assertEqual(self.window.property("saves"), 0)
        self.send_commit(field, "Việt")
        QTest.qWait(400)
        self.assertEqual(self.window.property("saves"), 1)
        self.assertEqual(field.property("text"), "Xin Việt")
        self.assertEqual(field.property("cursorPosition"), 8)
        QTest.keyClick(self.window, Qt.Key_Left)
        self.send_commit(field, "ệ", -1, 1)
        QTest.qWait(400)
        self.assertEqual(field.property("text"), "Xin Việt")
        self.assertEqual(self.window.property("saves"), 1)

    def test_manual_subtitle_model_refresh_never_discards_preedit(self):
        self.create_window('''
QtObject { id: controller
    signal manualSubtitleSaved(string id, int version, string request)
    signal manualSubtitleSaveFailed(string id, string request, string message)
}
property string savedValue: ""
SubtitleTextEditor {
    id: editor; objectName: "editor"; x: 20; y: 20; width: 650; height: 360
    controller: controller; segmentId: "a"; savedText: "Xin "
    onCommitRequested: function(id, text, version, request) {
        root.savedValue = text; controller.manualSubtitleSaved(id, version + 1, request);
    }
}''')
        field = self.window.findChild(QQuickItem, "manualSubtitleTextInput")
        editor = self.window.findChild(QQuickItem, "editor")
        field.forceActiveFocus()
        field.setProperty("cursorPosition", 4)
        self.preedit(field, "Việt")
        editor.setProperty("savedText", "An asynchronous model refresh")
        self.assertTrue(field.property("inputMethodComposing"))
        self.assertEqual(field.property("text"), "Xin ")
        QTest.keyClick(self.window, Qt.Key_Left)
        self.expression(editor, "apply()")
        QTest.qWait(40)
        self.assertEqual(self.window.property("savedValue"), "Xin Việt")
        self.assertEqual(field.property("text"), "Xin Việt")

    def test_watermark_model_updates_do_not_replace_active_edits(self):
        self.create_window('''
property string modelValue: "Gốc"
property int saves: 0
AutoSaveTextField {
    objectName: "field"; x: 20; y: 20; width: 620; sourceText: root.modelValue
    onValueCommitted: function(value) { root.modelValue = value; root.saves++ }
}''')
        field = self.window.findChild(QQuickItem, "field")
        self.assertEqual(field.property("text"), "Gốc")
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, QPoint(60, 40))
        field.selectAll()
        self.send_commit(field, "Mới ")
        self.preedit(field, "Việt")
        self.window.setProperty("modelValue", "Old backend value")
        self.assertEqual(field.property("text"), "Mới ")
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, QPoint(740, 470))
        self.assertEqual(field.property("text"), "Mới Việt")
        self.assertEqual(self.window.property("modelValue"), "Mới Việt")
        self.assertEqual(self.window.property("saves"), 1)
        self.window.setProperty("modelValue", "Dự án khác")
        self.assertEqual(field.property("text"), "Dự án khác")

    def test_control_focus_is_neutral_on_mouse_and_visible_on_keyboard(self):
        self.create_window('''
AppTextField { objectName: "field"; x: 20; y: 20; width: 250 }
AppTextArea { objectName: "area"; x: 20; y: 80; width: 250; height: 100 }
AppButton { objectName: "button"; x: 300; y: 20; text: "Chọn" }
AppComboBox { objectName: "combo"; x: 300; y: 80; width: 250; model: ["Một", "Hai"] }
''')
        for name in ("field", "area", "button", "combo"):
            field = self.window.findChild(QQuickItem, name)
            point = field.mapToScene(QPointF(field.width()/2, field.height()/2)).toPoint()
            QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, point)
            self.assertNotEqual(self.expression(field, "background.border.color").name(), "#e2b47f")
            self.assertEqual(self.expression(field, "background.border.width"), 1)
            if name == "combo":
                self.expression(field, "popup.close()")
            field.setFocus(False)
            field.forceActiveFocus(Qt.TabFocusReason)
            QTest.qWait(10)
            self.assertEqual(self.expression(field, "background.border.color").name(), "#b8b1a6")
            self.assertEqual(self.expression(field, "background.border.width"), 2)
        directory = os.environ.get("HFLOW_UI_PREVIEWS")
        if directory:
            self.window.grabWindow().save(str(Path(directory) / "neutral-focus-controls.png"))


def test_vietnamese_input_ui_in_isolated_process():
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve())], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_all_shared_control_focus_outlines_are_neutral():
    controls = (
        "AppButton", "AppCheckBox", "AppComboBox", "AppSlider", "AppSpinBox",
        "AppSwitch", "AppTextArea", "AppTextField", "BatchVideoCard", "HelpPopover",
        "HomeActionButton", "IconButton", "InspectorSection", "ManualToolNavigator",
        "NavigationRail", "NavigationTabs", "ProjectCard", "SearchableLanguageCombo",
        "SegmentedControl", "SubtitleTextEditor", "TextColorStrip", "VoicePicker",
    )
    for control in controls:
        source = (QML_DIR / f"{control}.qml").read_text(encoding="utf-8")
        assert "Theme.focus" not in source, control
        assert "Theme.controlFocus" in source, control
    # Keep the unrelated content selection markers, not a global theme rewrite.
    for overlay in ("OcrRegionOverlay", "SubtitleTransformOverlay", "WatermarkTransformOverlay"):
        assert "Theme.focus" in (QML_DIR / f"{overlay}.qml").read_text(encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

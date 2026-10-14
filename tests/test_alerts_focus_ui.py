"""Window-level input focus and compact notification regressions."""

import json
import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest

from hflow.desktop.input_method_commit_filter import InputMethodCommitFilter


QML_DIR = Path(__file__).resolve().parents[1] / "src/hflow/desktop/qml"


class AlertsFocusUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])
        for font in ("SegUIVar.ttf", "segoeui.ttf", "SegoeIcons.ttf", "segmdl2.ttf"):
            path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / font
            if path.is_file():
                QFontDatabase.addApplicationFont(str(path))

    def create_item(self, body):
        engine = QQmlEngine()
        component = QQmlComponent(engine)
        component.setData(
            (f'import QtQuick\nimport QtQuick.Controls.Basic\nimport "{QML_DIR.as_uri()}"\nItem {{\n{body}\n}}').encode(), QUrl(),
        )
        self.assertTrue(component.isReady(), "\n".join(e.toString() for e in component.errors()))
        item = component.create()
        self.assertIsNotNone(item)
        window = QQuickWindow()
        window.resize(600, 400)
        item.setParent(window)
        item.setParentItem(window.contentItem())
        item.setSize(window.size())
        window.show()
        QTest.qWait(40)
        self.addCleanup(self.dispose, window, item, engine)
        return window, item

    def dispose(self, window, item, engine):
        window.close()
        item.deleteLater()
        window.deleteLater()
        engine.deleteLater()
        self.app.processEvents()

    @staticmethod
    def visual_child(item, name):
        if item.objectName() == name:
            return item
        for child in item.childItems():
            found = AlertsFocusUiTests.visual_child(child, name)
            if found is not None:
                return found
        return None

    def test_outside_press_blurs_inputs_without_losing_text_or_button_clicks(self):
        window, item = self.create_item('''
            property int clicks: 0
            AppTextField { objectName: "key"; x: 20; y: 20; width: 280; echoMode: TextInput.Password }
            AppTextArea { objectName: "watermark"; x: 20; y: 80; width: 280; height: 100 }
            AppButton { x: 330; y: 20; text: "Save"; onClicked: parent.clicks++ }
        ''')
        event_filter = InputMethodCommitFilter()
        self.app.installEventFilter(event_filter)
        try:
            key = item.findChild(QQuickItem, "key")
            watermark = item.findChild(QQuickItem, "watermark")
            for field in (key, watermark):
                center = field.mapToScene(QPointF(40, 20)).toPoint()
                QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, center)
                self.assertTrue(field.property("activeFocus"))
                field.setProperty("text", "Nội dung tiếng Việt")
                QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, center)
                self.assertTrue(field.property("activeFocus"))
                QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(550, 300))
                self.assertFalse(field.property("activeFocus"))
                self.assertEqual(field.property("text"), "Nội dung tiếng Việt")
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(60, 40))
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(350, 40))
            self.assertFalse(key.property("activeFocus"))
            self.assertEqual(item.property("clicks"), 1)
            # The original key focus is released before a different editor gets it.
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(60, 40))
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(60, 100))
            self.assertFalse(key.property("activeFocus"))
            self.assertTrue(watermark.property("activeFocus"))
            QTest.keyClick(window, Qt.Key_Tab)
            self.assertIsNotNone(window.activeFocusItem())
        finally:
            self.app.removeEventFilter(event_filter)

    def test_long_toast_offers_full_details_and_short_notice_fits(self):
        for message, truncated in (
            ("Có thể tính phí khi bật thanh toán. Kiểm tra Billing trong AI Studio.", False),
            ("Thông tin cần xem đầy đủ. " * 30, True),
        ):
            with self.subTest(truncated=truncated):
                window, item = self.create_item(f'''
                    property string openedMessage: ""
                    ToastStack {{
                        width: 380
                        onDetailsRequested: (title, message, tone) => parent.openedMessage = message
                        Component.onCompleted: show("Gemini", {json.dumps(message)}, "info", 60000)
                    }}
                ''')
                label = self.visual_child(item, "toastMessage")
                details = self.visual_child(item, "toastDetailsButton")
                self.assertEqual(label.property("truncated"), truncated)
                self.assertEqual(details.property("visible"), truncated)
                if truncated:
                    point = details.mapToScene(QPointF(details.width() / 2, details.height() / 2)).toPoint()
                    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
                    self.assertEqual(item.property("openedMessage"), message)

    def test_voice_edit_notice_is_visible_and_dismissible_above_modal_editor(self):
        main = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
        toast_block = main.split("    ToastStack {", 1)[1]
        self.assertIn("parent: Overlay.overlay", toast_block)
        engine = QQmlEngine()
        component = QQmlComponent(engine)
        component.setData((f'''import QtQuick
import QtQuick.Controls.Basic
import "{QML_DIR.as_uri()}"
ApplicationWindow {{ width: 600; height: 400; visible: true
''' + '''
            AppDialog {
                id: dialog; objectName: "editor"; title: "Chỉnh phụ đề"
                preferredWidth: 580; preferredHeight: 300
                Text { text: "Nội dung đã lưu" }
            }
            ToastStack {
                id: notice; objectName: "notice"; parent: Overlay.overlay
                width: 380; anchors.top: parent.top; anchors.right: parent.right; z: 200
            }
            Component.onCompleted: {
                dialog.open();
                notice.show("Cần tạo lại giọng",
                    "Hãy tạo lại giọng cho câu vừa sửa phụ đề. Giọng của các câu khác được giữ nguyên.",
                    "warning", 60000)
            }
        }''').encode(), QUrl())
        self.assertTrue(component.isReady(), "\n".join(e.toString() for e in component.errors()))
        window = component.create()
        self.assertIsNotNone(window)
        QQmlEngine.setObjectOwnership(window, QQmlEngine.CppOwnership)

        def cleanup(_component=component):
            window.close()
            window.deleteLater()
            engine.deleteLater()
            self.app.processEvents()

        self.addCleanup(cleanup)
        QTest.qWait(50)
        notice = window.findChild(QQuickItem, "notice")
        editor = window.findChild(QObject, "editor")
        close = self.visual_child(window.contentItem(), "toastCloseButton")
        message = self.visual_child(window.contentItem(), "toastMessage")
        self.assertIsNotNone(close)
        self.assertTrue(notice.isVisible())
        self.assertFalse(message.property("truncated"))
        point = close.mapToScene(QPointF(close.width()/2, close.height()/2)).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
        QTest.qWait(30)
        self.assertIsNone(self.visual_child(window.contentItem(), "toastCloseButton"))
        self.assertTrue(editor.property("visible"))

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from PySide6.QtCore import Property, QObject, QPointF, Qt, QUrl, Slot
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from haizflow.core.subtitle_fonts import font_choices
from haizflow.desktop.manual_editor_document_model import ManualEditorDocumentModel
from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.desktop.subtitle_fonts import qt_subtitle_font
from haizflow.schemas.editor import EditorDocument, EditorTextStyle

ROOT = Path(__file__).resolve().parents[1]


class FontController(QObject):
    @Slot(str, str, result="QVariantList")
    def subtitleFontChoices(self, language, sample):
        rows = []
        for row in font_choices(language, sample):
            spec = qt_subtitle_font(row["sample"], language, row["family"])
            rows.append({**row, "qtFamily": spec["family"], "weight": spec["weight"]})
        return rows


class ManualFontController(FontController):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.model = ManualEditorDocumentModel(self)
        self.model.set_document(EditorDocument(video_id="old-project", default_subtitle_style_id="default",
            styles=[EditorTextStyle(style_id="default", font_family="Bangers")]))

    manualEditorDocumentModel = Property(QObject, lambda self: self.model, constant=True)
    manualVoiceLanguage = Property(str, lambda self: "vi", constant=True)

    @Slot("QVariantList", "QVariantMap", str, result=bool)
    def applyTextStyle(self, targets, patch, scope):
        self.calls.append((targets, dict(patch), scope))
        return HaizFlowController.applyTextStyle(self, targets, patch, scope)

    def _apply_editor_mutation(self, _label, callback):
        document = self.model.document_object.model_copy(deep=True)
        callback(document)
        self.model.set_document(document)
        return True


def test_manual_font_picker_updates_button_using_real_application_command(tmp_path):
    app = QApplication.instance() or QApplication([])
    engine = QQmlEngine()
    controller = ManualFontController()
    warnings = []
    engine.warnings.connect(lambda errors: warnings.extend(error.toString() for error in errors))
    engine.rootContext().setContextProperty("AppController", controller)
    engine.rootContext().setContextProperty("TestController", controller)
    qml_dir = QUrl.fromLocalFile(str(ROOT / "src/haizflow/desktop/qml")).toString()
    component = QQmlComponent(engine)
    component.setData(f'''
import QtQuick
import QtQuick.Controls.Basic
import "{qml_dir}"
ApplicationWindow {{
    width: 640; height: 680; visible: true
    ManualSubtitleStyleControls {{ width: 320; x: 20; y: 20; controller: TestController }}
}}
'''.encode(), QUrl.fromLocalFile(str(tmp_path / "manual.qml")))
    for _ in range(30):
        if component.status() != QQmlComponent.Loading:
            break
        QTest.qWait(20)
    window = component.create()
    assert window is not None, [error.toString() for error in component.errors()]
    try:
        QTest.qWait(60)
        button = window.findChild(QQuickItem, "subtitleFontButton")
        assert button.property("text") == "Bangers"
        font_picker = next(item for item in window.findChildren(QObject)
            if item.metaObject().indexOfSignal("fontSelected(QString)") >= 0)
        compact_bar = next(item for item in window.findChildren(QObject)
            if item.metaObject().indexOfSignal("changeRequested(QVariant)") >= 0)
        selected_spy = QSignalSpy(font_picker.fontSelected)
        changed_spy = QSignalSpy(compact_bar.changeRequested)
        for family in ("Lobster", "Be Vietnam Pro", "Bangers"):
            point = button.mapToScene(QPointF(button.width()/2, button.height()/2)).toPoint()
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
            QTest.qWait(50)
            popup = window.findChild(QObject, "subtitleFontPopup")
            assert popup.property("opened"), (button.width(), button.height(), point)
            search = window.findChild(QQuickItem, "subtitleFontSearch")
            search.setProperty("text", family)
            QTest.qWait(30)
            view = window.findChild(QQuickItem, "subtitleFontList")
            assert view.property("count") == 1
            search.forceActiveFocus()
            row_point = view.mapToScene(QPointF(90, 38)).toPoint()
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, row_point)
            QTest.qWait(60)
            assert controller.model.defaultSubtitleStyle["font_family"] == family, (controller.calls,
                selected_spy.count(), changed_spy.count(), warnings)
            assert button.property("text") == family
            restored = EditorDocument.model_validate_json(controller.model.document_object.model_dump_json())
            controller.model.set_document(restored)
            QTest.qWait(30)
            assert button.property("text") == family
    finally:
        controller.model.close()
        window.close()
        window.deleteLater()
        app.processEvents()


def test_picker_search_filter_selection_keyboard_and_popup_bounds(tmp_path):
    app = QApplication.instance() or QApplication([])
    # The Windows offscreen plugin does not enumerate system fonts like the
    # real windows platform plugin does. Register UI faces for visual QA only.
    if os.name == "nt" and os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        for name in ("SegUIVar.ttf", "SegoeIcons.ttf"):
            QFontDatabase.addApplicationFont(str(Path(os.environ["WINDIR"]) / "Fonts" / name))
    engine = QQmlEngine()
    controller = FontController()
    engine.rootContext().setContextProperty("AppController", controller)
    component = QQmlComponent(engine)
    qml_dir = QUrl.fromLocalFile(str(ROOT / "src/haizflow/desktop/qml")).toString()
    component.setData(f'''
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "{qml_dir}"
ApplicationWindow {{
    width: 740; height: 640; visible: true; color: Theme.window
    SubtitleFontPicker {{
        id: picker; objectName: "fontPicker"; width: 300; x: 420; y: 520
        onFontSelected: function(value) {{ family = value; }}
    }}
}}
'''.encode(), QUrl.fromLocalFile(str(tmp_path / "picker.qml")))
    for _ in range(30):
        if component.status() != QQmlComponent.Loading:
            break
        QTest.qWait(20)
    window = component.create()
    assert window is not None, [error.toString() for error in component.errors()]
    try:
        QTest.qWait(80)
        picker = window.findChild(QObject, "fontPicker")
        trigger = window.findChild(QQuickItem, "subtitleFontButton")
        def open_picker():
            point = trigger.mapToScene(QPointF(trigger.width() / 2, trigger.height() / 2)).toPoint()
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
            QTest.qWait(80)
        open_picker()
        popup = window.findChild(QObject, "subtitleFontPopup")
        assert popup.property("opened")
        view = window.findChild(QQuickItem, "subtitleFontList")
        assert view.property("count") == 19
        search = window.findChild(QQuickItem, "subtitleFontSearch")
        search.setProperty("text", "Lobster")
        QTest.qWait(40)
        assert view.property("count") == 1
        QTest.keyClick(window, Qt.Key_Down)
        QTest.keyClick(window, Qt.Key_Return)
        QTest.qWait(80)
        assert picker.property("family") == "Lobster"
        assert not popup.property("opened")
        picker.setProperty("language", "ja")
        open_picker()
        assert view.property("count") == 4
        category = window.findChild(QObject, "subtitleFontCategory")
        category.setProperty("currentIndex", 2)
        category.activated.emit(2)
        QTest.qWait(40)
        assert view.property("count") == 1
        output = ROOT / "build/font-picker-japanese.png"
        assert window.grabWindow().save(str(output))
        QTest.keyClick(window, Qt.Key_Escape)
        QTest.qWait(50)
        assert not popup.property("opened")
        window.setWidth(360)
        window.setHeight(520)
        picker.setProperty("x", 30)
        picker.setProperty("y", 430)
        picker.setProperty("language", "vi")
        open_picker()
        assert popup.property("x") >= 0 and popup.property("y") >= 0
        assert popup.property("x") + popup.property("width") <= window.width()
        assert popup.property("y") + popup.property("height") <= window.height()
        assert window.grabWindow().save(str(ROOT / "build/font-picker-vietnamese.png"))
        QTest.keyClick(window, Qt.Key_Escape)
        QTest.qWait(50)
        assert picker.property("catalog").toVariant() == []
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()

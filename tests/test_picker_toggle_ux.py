"""Real pointer/keyboard interaction for shared selectors, without app jobs."""
from pathlib import Path

import pytest
from PySide6.QtCore import Property, QObject, QPoint, QPointF, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlProperty
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from haizflow.desktop.models import DownloadProjectSourceListModel, SocialProjectSourceListModel

QML = Path(__file__).resolve().parents[1] / "src/haizflow/desktop/qml"
_APP = None
_UI_FONTS_LOADED = False


class Controller(QObject):
    translationApi = Property(QObject, lambda self: None, constant=True)
    projectKey = Property(str, lambda self: "test", constant=True)

    @Slot(str, str, result="QVariantList")
    def subtitleFontChoices(self, _language, _sample):
        return [dict(family=family, category="sans", sample="Xin bạn 1 star GitHub",
                     qtFamily="Segoe UI", weight=400) for family in ("Bangers", "Be Vietnam Pro")]


class SourceController(Controller):
    selectionChanged = Signal()
    socialImportBusy = Property(bool, lambda self: False, constant=True)

    def __init__(self):
        super().__init__()
        self.social = SocialProjectSourceListModel()
        self.downloads = DownloadProjectSourceListModel()
        self.social.set_items([dict(video_id="manual", project_name="Video đã dựng", project_type="manual",
                                   file_name="video.mp4", thumbnail_source="", video_size="25 MB", selected=False)])
        self.downloads.set_items([dict(item_id="download", project_name="Video đã tải", category="video",
                                      file_name="video.mp4", file_path="", file_size=1024, selected=False)])

    tiktokProjectSourceModel = Property(QObject, lambda self: self.social, constant=True)
    downloadProjectSourceModel = Property(QObject, lambda self: self.downloads, constant=True)
    tiktokProjectSourceSelectedCount = Property(
        int, lambda self: sum(row["selected"] for row in self.social._items), notify=selectionChanged,
    )
    downloadProjectSourceSelectedCount = Property(
        int, lambda self: self.downloads.selected_count, notify=selectionChanged,
    )

    @Slot(int, bool)
    def setTikTokProjectSourceSelected(self, index, checked):
        self.social.set_selected(index, checked)
        self.selectionChanged.emit()

    @Slot(int, bool, bool)
    def setDownloadProjectSourceSelected(self, index, checked, exclusive):
        self.downloads.set_selected(index, checked, exclusive=exclusive)
        self.selectionChanged.emit()


@pytest.fixture
def create_window(tmp_path):
    global _APP, _UI_FONTS_LOADED
    _APP = QGuiApplication.instance() or QGuiApplication([])
    if not _UI_FONTS_LOADED:
        for name in ("SegUIVar.ttf", "segoeui.ttf", "SegoeIcons.ttf"):
            path = Path("C:/Windows/Fonts") / name
            if path.is_file():
                QFontDatabase.addApplicationFont(str(path))
        _UI_FONTS_LOADED = True
    instances = []

    def create(body, controller=None):
        engine, controller = QQmlEngine(), controller or Controller()
        warnings = []
        engine.warnings.connect(lambda errors: warnings.extend(error.toString() for error in errors))
        engine.rootContext().setContextProperty("AppController", controller)
        engine.rootContext().setContextProperty("TestController", controller)
        component = QQmlComponent(engine)
        component.setData(('import QtQuick\nimport QtQuick.Controls.Basic\nimport QtQuick.Layouts\n'
                           f'import "{QUrl.fromLocalFile(str(QML)).toString()}"\n'
                           'ApplicationWindow { width: 900; height: 900; visible: true; color: Theme.window; '
                           + body + '}').encode(), QUrl.fromLocalFile(str(tmp_path / "picker.qml")))
        for _ in range(30):
            if component.status() != QQmlComponent.Loading:
                break
            QTest.qWait(10)
        window = component.create()
        assert window is not None, [error.toString() for error in component.errors()]
        instances.append((window, engine, controller, component))
        QTest.qWait(30)
        return window, warnings

    yield create
    for window, engine, _controller, _component in reversed(instances):
        window.close()
        window.deleteLater()
        _APP.processEvents()
        engine.deleteLater()
        _APP.processEvents()


def click(window, item):
    point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
    QTest.qWait(180)


def visual_children(item):
    for child in item.childItems():
        yield child
        yield from visual_children(child)


SELECTORS = [
    ("SubtitleFontPicker", "", "subtitleFontButton", "subtitleFontPopup"),
    ("SearchableLanguageCombo", 'options: [{code: "vi", label: "Tiếng Việt", search: "vi"}];',
     "languageDisplayButton", "languageSearchPopup"),
    ("TranslationModelCombo", "", "projectTranslationModelButton", "projectTranslationModelPopup"),
    ("VoicePicker", 'previewEnabled: false; model: [{voice: "one", label: "One"}];',
     "selector", "voicePickerPopup"),
    ("StudioComboBox", 'model: ["One", "Two"]; Component.onCompleted: popup.objectName = "comboPopup";',
     "selector", "comboPopup"),
    ("OutputSpeedButton", "", "selector", "outputSpeedPopup"),
    ("PlaybackSpeedButton", "", "selector", "previewSpeedPopup"),
    ("HelpPopover", 'helpText: "Help";', "selector", "helpPopoverPopup"),
    ("MediaSourceImportButton", "", "selector", ""),
]


def selector_parts(window, trigger_name, popup_name):
    selector = window.findChild(QQuickItem, "selector")
    trigger = window.findChild(QQuickItem, trigger_name)
    popup = window.findChild(QObject, popup_name) if popup_name else next(
        child for child in selector.findChildren(QObject) if child.metaObject().indexOfMethod("open()") >= 0
    )
    assert trigger is not None and popup is not None
    return selector, trigger, popup


@pytest.mark.parametrize("type_name,properties,trigger_name,popup_name", SELECTORS)
def test_selector_second_click_closes_and_outside_escape_do_not_reopen(
    create_window, type_name, properties, trigger_name, popup_name,
):
    window, warnings = create_window(
        f'{type_name} {{ objectName: "selector"; x: 80; y: 80; width: 300; {properties} }}'
    )
    _selector, trigger, popup = selector_parts(window, trigger_name, popup_name)
    for _ in range(2):
        click(window, trigger)
        assert popup.property("opened"), (type_name, warnings)
        click(window, trigger)
        assert not popup.property("visible"), (type_name, warnings)
    click(window, trigger)
    QTest.keyClick(window, Qt.Key_Escape)
    QTest.qWait(180)
    assert not popup.property("visible"), (type_name, warnings)
    click(window, trigger)
    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(850, 850))
    QTest.qWait(180)
    assert not popup.property("visible"), (type_name, warnings)


@pytest.mark.parametrize("type_name,properties,trigger_name,popup_name", SELECTORS)
@pytest.mark.parametrize("changed_property", ["visible", "enabled"])
def test_selector_cannot_leave_an_orphan_popup_after_navigation_or_locking(
    create_window, type_name, properties, trigger_name, popup_name, changed_property,
):
    window, warnings = create_window(
        f'{type_name} {{ objectName: "selector"; x: 80; y: 80; width: 300; {properties} }}'
    )
    selector, trigger, popup = selector_parts(window, trigger_name, popup_name)
    click(window, trigger)
    assert popup.property("opened"), warnings
    selector.setProperty(changed_property, False)
    QTest.qWait(180)
    assert not popup.property("visible"), (type_name, changed_property, warnings)


def test_font_popup_leaves_trigger_accessible_in_short_window(create_window):
    window, _warnings = create_window(
        'SubtitleFontPicker { objectName: "selector"; x: 30; y: 210; width: 300; }'
    )
    window.setWidth(360)
    window.setHeight(520)
    trigger = window.findChild(QQuickItem, "subtitleFontButton")
    popup = window.findChild(QObject, "subtitleFontPopup")
    click(window, trigger)
    popup_item = popup.property("contentItem")
    top = popup_item.mapToScene(QPointF()).y()
    bottom = top + popup_item.height()
    button_top = trigger.mapToScene(QPointF()).y()
    assert bottom < button_top or top > button_top + trigger.height()
    assert window.grabWindow().save(str(QML.parents[3] / "build/font-picker-short-window.png"))
    click(window, trigger)
    assert not popup.property("visible")


@pytest.mark.parametrize("key", [Qt.Key_Space, Qt.Key_Return])
def test_font_trigger_keyboard_toggle_and_focus_restore(create_window, key):
    window, warnings = create_window('SubtitleFontPicker { x: 80; y: 80; width: 300; }')
    trigger = window.findChild(QQuickItem, "subtitleFontButton")
    popup = window.findChild(QObject, "subtitleFontPopup")
    trigger.forceActiveFocus(Qt.TabFocusReason)
    QTest.keyClick(window, key)
    QTest.qWait(60)
    assert popup.property("opened"), warnings
    QTest.keyClick(window, Qt.Key_Escape)
    QTest.qWait(60)
    assert not popup.property("visible")
    assert trigger.hasActiveFocus()


@pytest.mark.parametrize("dialog_type,role", [
    ("SocialProjectSourceDialog", "sourceSelected"),
    ("DownloadProjectSourceDialog", "downloadSelected"),
])
def test_source_selection_uses_neutral_border_and_preserves_keyboard_focus(create_window, dialog_type, role):
    controller = SourceController()
    # A real singleton registered by another test module must not override this
    # fixture's model. Execute the actual dialog body with an explicit test name.
    source = (QML / f"{dialog_type}.qml").read_text("utf-8")
    body = source[source.index("AppDialog {"):].replace("AppController", "TestController")
    body = body.replace("AppDialog {", 'AppDialog { objectName: "sources";', 1)
    window, warnings = create_window(body, controller)
    dialog = window.findChild(QObject, "sources")
    dialog.open()
    QTest.qWait(60)
    row = next(item for item in visual_children(window.contentItem())
               if item.metaObject().indexOfProperty(role) >= 0)
    checkbox = next(item for item in visual_children(row)
                    if item.metaObject().indexOfSignal("toggled()") >= 0)
    assert QQmlProperty(row, "border.color").read().name() == "#48423a"
    click(window, checkbox)
    assert row.property(role)
    assert QQmlProperty(row, "border.color").read().name() == "#665f55"
    QTest.keyClick(window, Qt.Key_Tab)
    QTest.keyClick(window, Qt.Key_Backtab)
    QTest.qWait(10)
    assert checkbox.property("visualFocus"), (checkbox.hasActiveFocus(), checkbox.property("focusReason"),
                                             window.isActive(), window.activeFocusItem())
    QTest.keyClick(window, Qt.Key_Space)
    QTest.qWait(30)
    assert not row.property(role)
    QTest.keyClick(window, Qt.Key_Space)
    QTest.qWait(30)
    assert row.property(role)
    assert QQmlProperty(row, "border.color").read().name() != "#e2b47f"
    assert window.grabWindow().save(str(QML.parents[3] / f"build/{dialog_type}-neutral-selection.png"))
    assert not warnings, warnings


def test_actual_manual_subtitle_action_menu_can_be_closed_by_its_button(create_window):
    source = (QML / "ManualSubtitleToolPanel.qml").read_text("utf-8")
    start = source.index('            StudioIconButton {\n                objectName: "manualSubtitleActionsButton"')
    depth = 0
    for end in range(source.index("{", start), len(source)):
        if source[end] == "{":
            depth += 1
        elif source[end] == "}":
            depth -= 1
            if not depth:
                break
    window, warnings = create_window(
        'Item { id: root; x: 80; y: 80; width: 300; height: 100; '
        'property bool writable: true; property var segment: ({start: 0, end: 10}); '
        'property var inspector: ({subtitleSegments: [{}], selectedSubtitleIndex: 0, playheadSeconds: 1}); '
        'QtObject { id: subtitleEditor; property string saveStatus: "saved" } '
        + source[start:end + 1] + '}'
    )
    trigger = window.findChild(QQuickItem, "manualSubtitleActionsButton")
    popup = window.findChild(QObject, "manualSubtitleActionsMenu")
    click(window, trigger)
    assert popup.property("opened"), warnings
    click(window, trigger)
    assert not popup.property("visible"), warnings

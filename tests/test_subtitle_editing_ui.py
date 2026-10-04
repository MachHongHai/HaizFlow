"""Pointer selection and repeated-save regressions using the production QML."""

import os
import re
import subprocess
import sys
import time
import unittest
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, Qt, QUrl, Property, Slot, Signal
from PySide6.QtGui import QFontDatabase, QGuiApplication, QInputMethodEvent
from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlPropertyMap, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest


QML_DIR = Path(__file__).resolve().parents[1] / "src" / "haizflow" / "desktop" / "qml"


class SubtitleEditingUiTests(unittest.TestCase):
    __test__ = False  # Isolate Qt registration and engine lifetimes from other suites.

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QGuiApplication.instance() or QGuiApplication([])
        if os.environ.get("HAIZFLOW_UI_PREVIEWS") and os.name == "nt":
            # The offscreen plugin doesn't discover Windows fonts. Seed only
            # visual-QA runs so they show the same UI fonts as the native app.
            fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
            for name in ("SegUIVar.ttf", "SegoeIcons.ttf"):
                path = fonts / name
                if path.is_file():
                    QFontDatabase.addApplicationFont(str(path))

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
ApplicationWindow {{ id: root; width: 1120; height: 720; visible: true; color: Theme.window
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

    def test_labeled_buttons_drop_redundant_icons_but_icon_only_actions_remain(self):
        window = self.create_window('''
AppButton { objectName: "labeled"; x: 20; y: 20; text: "Xuất"; iconGlyph: "\\uE898" }
AppButton { objectName: "iconOnly"; x: 180; y: 20; iconGlyph: "\\uE768"; toolTipText: "Phát" }
''')
        labeled = window.findChild(QQuickItem, "labeled")
        icon_only = window.findChild(QQuickItem, "iconOnly")
        self.assertFalse(labeled.property("showLeadingIcon"))
        self.assertFalse(labeled.findChild(QQuickItem, "buttonLeadingIcon").isVisible())
        self.assertTrue(icon_only.property("showLeadingIcon"))
        self.assertTrue(icon_only.findChild(QQuickItem, "buttonLeadingIcon").isVisible())

    def test_settings_apply_is_explicit_and_footer_does_not_scroll(self):
        class SettingsController(QObject):
            settingsChanged = Signal()
            language = "vi"
            device = "cpu"
            warm = False
            applied = None
            settingsLanguage = Property(str, lambda self: self.language, notify=settingsChanged)
            processingDevice = Property(str, lambda self: self.device, notify=settingsChanged)
            keepModelsWarm = Property(bool, lambda self: self.warm, notify=settingsChanged)
            isProcessing = Property(bool, lambda self: False, constant=True)
            performanceProfileDetail = Property(str, lambda self: "CPU · 16 GB RAM", constant=True)
            appUpdateState = Property(str, lambda self: "idle", constant=True)
            currentAppVersion = Property(str, lambda self: "0.1.0", constant=True)
            latestAppVersion = Property(str, lambda self: "", constant=True)

            @Slot(str, str, bool, result=bool)
            def applyGeneralSettings(self, language, device, warm):
                self.applied = (language, device, warm)
                self.language, self.device, self.warm = self.applied
                self.settingsChanged.emit()
                return True

        controller = SettingsController()
        self.engine.rootContext().setContextProperty("AppController", controller)
        window = self.create_window('SettingsPage { objectName: "settingsPage"; anchors.fill: parent }')
        page = window.findChild(QQuickItem, "settingsPage")
        button = window.findChild(QQuickItem, "applyGeneralSettingsButton")
        footer = window.findChild(QQuickItem, "generalSettingsFooter")
        language = window.findChild(QQuickItem, "settingsLanguageChoice")
        initial_y = button.mapToScene(QPointF()).y()
        self.assertFalse(button.isEnabled())
        self.assertAlmostEqual(footer.mapToScene(QPointF()).x() + footer.width() / 2, window.width() / 2, delta=1)
        language.activated.emit("en")
        QTest.qWait(30)
        self.assertEqual(controller.language, "vi")
        self.assertEqual(page.property("draftLanguage"), "en")
        self.assertTrue(button.isEnabled())
        self.assertAlmostEqual(button.mapToScene(QPointF()).y(), initial_y, delta=1)
        button.clicked.emit()
        QTest.qWait(30)
        self.assertEqual(controller.applied, ("en", "cpu", False))
        self.assertFalse(button.isEnabled())
        preview_directory = os.environ.get("HAIZFLOW_UI_PREVIEWS")
        if preview_directory:
            window.grabWindow().save(str(Path(preview_directory) / "general-settings.png"))
        window.setHeight(400)
        QTest.qWait(50)
        self.assertLess(button.mapToScene(QPointF()).y() + button.height(), window.height())

    def test_copyright_dialog_fits_content_without_unnecessary_scroll(self):
        window = self.create_window('''
CopyrightDialog { id: dialog; Component.onCompleted: open(); }
''')
        dialog = window.findChild(QObject, "copyrightDialog")
        scroll = window.findChild(QQuickItem, "copyrightScroll")
        QTest.qWait(80)
        self.assertTrue(dialog.property("opened"))
        self.assertLessEqual(scroll.property("contentHeight"), scroll.property("availableHeight") + 1)
        self.assertLessEqual(dialog.property("height"), window.height() - 48)
        preview_directory = os.environ.get("HAIZFLOW_UI_PREVIEWS")
        if preview_directory:
            window.grabWindow().save(str(Path(preview_directory) / "copyright.png"))
        # Retain scrolling when a smaller screen cannot fit all legal text.
        window.setHeight(400)
        QTest.qWait(50)
        self.assertGreater(scroll.property("contentHeight"), scroll.property("availableHeight"))

    def test_activity_strip_keeps_ready_and_task_states_visible(self):
        window = self.create_window('ActivityTray { objectName: "tray"; width: parent.width }')
        tray = window.findChild(QQuickItem, "tray")
        label = window.findChild(QQuickItem, "activityStatusLabel")
        height = tray.height()
        for state, text in (("ready", "Sẵn sàng"), ("processing", "Đang xử lý"),
                            ("paused", "Đã tạm dừng"), ("failed", "Có lỗi"), ("ready", "Sẵn sàng")):
            tray.setProperty("activityState", state)
            QTest.qWait(20)
            self.assertTrue(label.isVisible())
            self.assertEqual(label.property("text"), text)
            self.assertEqual(tray.height(), height)

    def test_manual_music_loop_control_tracks_document_and_updates_without_ducking(self):
        class MusicModel(QObject):
            changed = Signal()
            payload = {"clips": [{"track_id": "music", "loop": True}], "audio_ducking_enabled": False}
            document = Property("QVariantMap", lambda self: self.payload, notify=changed)

        class MusicController(QObject):
            changed = Signal()
            model = MusicModel()
            originalVolume = Property(int, lambda self: 60, constant=True)
            ttsVolume = Property(int, lambda self: 100, constant=True)
            backgroundMusicVolume = Property(int, lambda self: 30, constant=True)
            backgroundMusicPath = Property(str, lambda self: "D:/project/music.wav", constant=True)
            enableAudioSeparation = Property(bool, lambda self: False, constant=True)
            manualEditorDocumentModel = Property(QObject, lambda self: self.model, constant=True)
            last_loop = None

            @Slot(bool, result=bool)
            def setMusicLoop(self, value):
                self.last_loop = value
                self.model.payload = {"clips": [{"track_id": "music", "loop": value}],
                                      "audio_ducking_enabled": False}
                self.model.changed.emit()
                return True

        controller = MusicController()
        self.engine.rootContext().setContextProperty("AppController", controller)
        window = self.create_window('''
            QtObject { id: inspector; property bool editable: true
                function hasCurrentCache(stage) { return false; }
                function scheduleSave() {}
            }
            ManualAudioToolPanel { width: 320; inspector: inspector }
        ''')
        loop = window.findChild(QQuickItem, "manualMusicLoopSwitch")
        self.assertTrue(loop.property("checked"))
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier,
                         loop.mapToScene(QPointF(loop.width() / 2, loop.height() / 2)).toPoint())
        QTest.qWait(40)
        self.assertFalse(controller.last_loop)
        self.assertFalse(loop.property("checked"))
        self.assertFalse(controller.model.payload["audio_ducking_enabled"])
        controller.model.payload = {"clips": [{"track_id": "music", "loop": True}]}
        controller.model.changed.emit()
        QTest.qWait(40)
        self.assertTrue(loop.property("checked"))

    def test_api_settings_switch_providers_mask_secrets_and_handle_first_install(self):
        class ApiController(QObject):
            changed = Signal()
            apiKeySettingsRequested = Signal(str)
            apiKeyGuideRequested = Signal(str)
            geminiSetupRequested = Signal()
            keys = []
            social_keys = []
            checking = False
            configured = False
            verified = False
            result = ""
            submitted = None
            geminiApiKeys = Property("QVariantList", lambda self: self.keys, notify=changed)
            zernioApiKeys = Property("QVariantList", lambda self: self.social_keys, notify=changed)
            zernioCredentialBusy = Property(bool, lambda self: self.checking, notify=changed)
            zernioCredentialResult = Property(str, lambda self: self.result, notify=changed)
            zernioApiKeyConfigured = Property(bool, lambda self: self.configured, notify=changed)
            zernioApiKeyVerified = Property(bool, lambda self: self.verified, notify=changed)
            tiktokPublishBusy = Property(bool, lambda self: False, constant=True)
            zernioAccountSyncing = Property(bool, lambda self: False, constant=True)

            @Slot(str, str, result=bool)
            def addGeminiApiKey(self, label, key):
                self.submitted = (label, key)
                self.keys = [dict(id="one", label=label, active=True)]
                self.changed.emit()
                return True

            @Slot(str, str, result=bool)
            def addZernioApiKey(self, label, key):
                self.submitted = (label, key)
                self.checking = True
                self.changed.emit()
                return True

            @Slot(result=bool)
            def openZernioApiKeys(self):
                return True

            @Slot(result=bool)
            def openZernioSignIn(self):
                return True

            @Slot(result=bool)
            def openZernioPostingDocs(self):
                return True

        controller = ApiController()
        self.engine.rootContext().setContextProperty("AppController", controller)
        window = self.create_window('ApiKeysPage { objectName: "apiPage"; anchors.fill: parent }')
        page = window.findChild(QQuickItem, "apiPage")
        name = window.findChild(QQuickItem, "apiKeyNameInput")
        secret = window.findChild(QQuickItem, "apiKeySecretInput")
        save = window.findChild(QQuickItem, "saveApiKeyButton")
        status = window.findChild(QQuickItem, "credentialStatus")
        dot = window.findChild(QQuickItem, "credentialStatusDot")
        self.assertFalse(dot.isVisible())
        self.assertFalse(save.isEnabled())
        self.assertFalse(secret.hasActiveFocus())
        echo_mode, _ = QQmlExpression(self.engine.rootContext(), secret, "Number(echoMode)").evaluate()
        self.assertEqual(echo_mode, 2)  # TextInput.Password
        self.assertIn("cục bộ", status.property("text"))
        name.setProperty("text", "Dịch")
        secret.setProperty("text", "example-gemini-key")
        QTest.qWait(30)
        save.clicked.emit()
        QTest.qWait(30)
        self.assertEqual(controller.submitted, ("Dịch", "example-gemini-key"))
        self.assertEqual(secret.property("text"), "")
        controller.apiKeySettingsRequested.emit("zernio")
        QTest.qWait(50)
        self.assertEqual(page.property("provider"), "zernio")
        self.assertTrue(name.isVisible())
        self.assertIn("Chưa có key", status.property("text"))
        name.setProperty("text", "Đăng bài")
        secret.setProperty("text", "sk_" + "a" * 64)
        QTest.qWait(30)
        save.clicked.emit()
        QTest.qWait(50)
        self.assertTrue(controller.checking)
        self.assertEqual(secret.property("text"), "")
        self.assertFalse(save.isEnabled())
        self.assertIn("Đang kiểm tra", status.property("text"))
        controller.checking = False
        controller.configured = True
        controller.social_keys = [dict(id="social", label="Đăng bài", active=True)]
        controller.verified = True
        controller.result = "verified"
        controller.changed.emit()
        QTest.qWait(50)
        self.assertEqual("Kiểm tra thành công", status.property("text"))
        self.assertTrue(dot.isVisible())
        success_color = dot.property("color")
        self.assertLess(save.mapToScene(QPointF()).y() + save.height(), window.height())
        preview_directory = os.environ.get("HAIZFLOW_UI_PREVIEWS")
        if preview_directory:
            window.grabWindow().save(str(Path(preview_directory) / "zernio-api-settings.png"))
        # A failed replacement attempt must not inherit the old key's green state.
        controller.result = "invalid"
        controller.changed.emit()
        QTest.qWait(30)
        self.assertIn("Kiểm tra thất bại", status.property("text"))
        self.assertNotEqual(success_color, dot.property("color"))
        controller.checking = True
        controller.changed.emit()
        QTest.qWait(30)
        self.assertFalse(dot.isVisible())
        controller.checking = False
        controller.result = "verified"
        controller.changed.emit()
        controller.apiKeyGuideRequested.emit("zernio")
        QTest.qWait(160)
        guide = window.findChild(QObject, "zernioApiGuide")
        self.assertIsNotNone(guide)
        self.assertTrue(guide.property("visible"))
        self.assertLessEqual(guide.property("height"), window.height())
        if preview_directory:
            window.grabWindow().save(str(Path(preview_directory) / "zernio-api-guide.png"))
        guide.close()
        QTest.qWait(30)
        secret.setProperty("text", "never-retain-between-providers")
        controller.apiKeySettingsRequested.emit("gemini")
        QTest.qWait(30)
        self.assertEqual(secret.property("text"), "")
        window.findChild(QQuickItem, "editApiKeyButton").clicked.emit()
        QTest.qWait(30)
        self.assertTrue(name.isVisible())

    def test_batch_subtitle_draft_serializes_every_appearance_field_without_editor_writes(self):
        from haizflow.schemas.video import SubtitleStyle

        source = (QML_DIR / "BatchSettingsDialog.qml").read_text(encoding="utf-8")
        properties = re.findall(r"^    property (?:string|bool|int|var) draft\w+:.*$", source, re.M)
        current_draft = re.search(r"    function currentDraft\(\) \{.*?\n    \}", source, re.S)
        self.assertIsNotNone(current_draft)
        window = self.create_window("\n".join(properties) + "\n" + current_draft.group() + '''
SubtitleAppearanceControls {
    id: controls; objectName: "batchAppearance"; width: 290
    style: Object.assign({}, root.draftSubtitleStyle, {font_size: root.draftSubtitleFontSize})
    onChangeRequested: function(patch) {
        root.draftSubtitleStyle = Object.assign({}, root.draftSubtitleStyle, patch);
        if (patch.font_size !== undefined) root.draftSubtitleFontSize = Number(patch.font_size);
        if (patch.outline !== undefined) root.draftSubtitleOutline = Number(patch.outline);
    }
}
function readDraft() { return currentDraft(); }
''')
        initial = SubtitleStyle().model_dump()
        window.setProperty("draftSubtitleStyle", initial)
        controls = window.findChild(QQuickItem, "batchAppearance")
        style = dict(font_family="Arial", font_size=84, text_color="#EF5350",
                     karaoke_color="#FFEF00", outline_color="#FFFFFF", outline=8,
                     bold=True, italic=True, uppercase=True, shadow=4, letter_spacing=1.5, alignment="left")
        controls.changeRequested.emit(style)
        window.setProperty("draftSubtitleManual", True)
        draft = window.readDraft().toVariant()["subtitleStyle"]
        self.assertTrue(draft.pop("manual"))
        self.assertEqual(SubtitleStyle.model_validate(draft).model_dump(), {**initial, **style})
        self.assertIn("appearance: Object.assign({}, root.draftSubtitleStyle", source)
        self.assertNotIn("AppController.applySubtitleAppearance", source)
        self.assertIn("editable: !AppController.isBatchRunning", source)

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

    def test_subtitle_box_resizes_each_axis_without_font_scaling_or_mid_drag_save(self):
        window = self.create_window('''
property int commits: 0
property int previews: 0
SubtitleTransformOverlay {
    id: transform; objectName: "transform"; anchors.fill: parent
    videoRect: Qt.rect(60, 40, 800, 450)
    sampleText: "Một câu phụ đề đủ dài để kiểm tra khung"
    fontSize: 68; positionXPercent: 50; positionYPercent: 70
    referenceWidthPixels: 1920; referenceHeightPixels: 1080
    boxWidthPercent: 72; boxHeightPercent: 12
    interactive: true; editing: true
    onLayoutPreviewChanged: root.previews += 1
    onLayoutCommitted: function(font, x, y, w, h) {
        root.commits += 1;
        fontSize = font; positionXPercent = x; positionYPercent = y;
        boxWidthPercent = w; boxHeightPercent = h;
    }
}
''')
        overlay = window.findChild(QQuickItem, "transform")
        selection = window.findChild(QQuickItem, "subtitleTransformSelection")

        def visual_find(item, name):
            if item.objectName() == name:
                return item
            for child in item.childItems():
                found = visual_find(child, name)
                if found is not None:
                    return found
            return None

        right = visual_find(window.contentItem(), "subtitleBoxHandle_1_0")
        self.assertIsNotNone(right)
        left_before = selection.x()
        height_before = selection.height()
        width_before = selection.width()
        start = right.mapToScene(QPointF(right.width()/2, right.height()/2)).toPoint()
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
        previous = width_before / 800 * 100
        for delta in (15, 35, 55, 80):
            QTest.mouseMove(window, start + QPointF(delta, 0).toPoint(), 35)
            self.assertGreaterEqual(overlay.property("draftBoxWidth"), previous)
            previous = overlay.property("draftBoxWidth")
            self.assertAlmostEqual(selection.x(), left_before, delta=1)
            self.assertAlmostEqual(selection.height(), height_before, delta=1)
            self.assertEqual(window.property("commits"), 0)
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, start + QPointF(80, 0).toPoint())
        QTest.qWait(30)
        self.assertAlmostEqual(overlay.property("boxWidthPercent"), round((width_before + 80) / 800 * 100), delta=1)
        self.assertEqual(overlay.property("fontSize"), 68)
        self.assertEqual(window.property("commits"), 1)
        self.assertGreater(window.property("previews"), 0)
        width_before = selection.width()
        top_before = selection.y()
        height_before = selection.height()
        bottom = visual_find(window.contentItem(), "subtitleBoxHandle_0_1")
        start = bottom.mapToScene(QPointF(bottom.width()/2, bottom.height()/2)).toPoint()
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
        QTest.mouseMove(window, start + QPointF(0, 36).toPoint(), 40)
        self.assertAlmostEqual(selection.y(), top_before, delta=1)
        self.assertAlmostEqual(selection.width(), width_before, delta=1)
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, start + QPointF(0, 36).toPoint())
        QTest.qWait(30)
        self.assertAlmostEqual(overlay.property("boxHeightPercent"), round(12 * (height_before + 36) / height_before), delta=1)
        self.assertEqual(overlay.property("fontSize"), 68)
        self.assertEqual(window.property("commits"), 2)

    def test_music_link_reopening_does_not_display_old_import_result_as_error(self):
        window = self.create_window('''
QtObject {
    id: musicController; objectName: "musicController"
    property bool backgroundMusicImportBusy: false
    property string backgroundMusicImportStatus: "Background music imported"
    property string submittedUrl: ""
    signal backgroundMusicImportChanged()
    signal batchBackgroundMusicDraftReady(string path)
    function importBackgroundMusicFromLink(url) {
        submittedUrl = url;
        backgroundMusicImportStatus = "";
        backgroundMusicImportBusy = true;
        backgroundMusicImportChanged();
    }
    function cancelBackgroundMusicLinkImport() {
        backgroundMusicImportBusy = false;
        backgroundMusicImportStatus = "Download canceled";
        backgroundMusicImportChanged();
    }
}
BackgroundMusicLinkDialog { id: dialog; controller: musicController }
function openMusic() { dialog.open(); }
function completeMusic() {
    musicController.backgroundMusicImportStatus = "Background music imported";
    musicController.backgroundMusicImportBusy = false;
    musicController.backgroundMusicImportChanged();
}
function failMusic() {
    musicController.backgroundMusicImportStatus = "Network error";
    musicController.backgroundMusicImportBusy = false;
    musicController.backgroundMusicImportChanged();
}
''')
        dialog = window.findChild(QObject, "backgroundMusicLinkDialog")
        field = window.findChild(QObject, "backgroundMusicLinkField")
        controller = window.findChild(QObject, "musicController")
        window.openMusic()
        QTest.qWait(80)
        self.assertFalse(dialog.property("hasError"))
        self.assertEqual(field.property("text"), "")
        preview_directory = os.environ.get("HAIZFLOW_UI_PREVIEWS")
        if preview_directory:
            window.grabWindow().save(str(Path(preview_directory) / "music-link.png"))
        field.setProperty("text", "https://example.com/new-music")
        dialog.startImport()
        self.assertTrue(dialog.property("busy"))
        window.completeMusic()
        QTest.qWait(80)
        self.assertFalse(dialog.property("opened"))
        window.openMusic()
        QTest.qWait(80)
        self.assertFalse(dialog.property("hasError"))
        self.assertEqual(field.property("text"), "")
        field.setProperty("text", "https://example.com/failed-music")
        dialog.startImport()
        window.failMusic()
        QTest.qWait(80)
        self.assertTrue(dialog.property("hasError"))
        self.assertTrue(dialog.property("opened"))
        dialog.close()
        QTest.qWait(80)
        window.openMusic()
        QTest.qWait(80)
        self.assertFalse(dialog.property("hasError"))
        self.assertEqual(controller.property("submittedUrl"), "https://example.com/failed-music")

    def test_auto_preview_long_sample_capacity_and_cover_alignment_lock(self):
        import tempfile
        from datetime import timedelta
        import srt
        from PySide6.QtGui import QImage
        from haizflow.pipeline.render import SubtitleRegionLayout, _subtitle_parts_for_region
        from haizflow.desktop.subtitle_overlay_renderer import SubtitleOverlayRenderer
        from haizflow.schemas.video import SubtitleStyle

        class PreviewController(QObject):
            thumbnail = ""
            renderer = None
            subtitleAppearance = Property("QVariantMap", lambda self: SubtitleStyle(font_size=68).model_dump(), constant=True)
            subtitleSampleOverlayRenderer = Property(QObject, lambda self: self.renderer, constant=True)
            reviewPreviewMedia = Property("QVariantMap", lambda self: {"videoWidth": 720, "videoHeight": 1280}, constant=True)
            videoThumbnailSource = Property(str, lambda self: self.thumbnail, constant=True)
            subtitleFontFamily = Property(str, lambda self: "Bangers", constant=True)
            subtitlePreviewFontScale = Property(float, lambda self: 1000 / 1757, constant=True)
            subtitleTextColor = Property(str, lambda self: "yellow", constant=True)
            subtitleOutlineColor = Property(str, lambda self: "black", constant=True)
            subtitleBold = Property(bool, lambda self: False, constant=True)
            subtitleItalic = Property(bool, lambda self: False, constant=True)

            @Slot(str, int, int, int, int, int, "QVariantMap", result=str)
            def subtitleSampleText(self, text, font, width, height, source_width, source_height, appearance):
                cue = srt.Subtitle(1, timedelta(0), timedelta(seconds=10), text)
                parts = _subtitle_parts_for_region(cue, SubtitleRegionLayout(
                    0, 0, source_width * width / 100, source_height * height / 100),
                    SubtitleStyle.model_validate({**appearance, "font_size": font}), fixed_font_size=True)
                return parts[0][2]

        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "preview.png")
            image = QImage(720, 1280, QImage.Format_RGB32)
            image.fill(Qt.black)
            image.save(path)
            controller = PreviewController()
            controller.renderer = SubtitleOverlayRenderer(controller)
            renderer_errors = []
            controller.renderer._ready.connect(lambda result: renderer_errors.append(result)
                if result[0] in ("error", "failed_frame") else None)
            self.addCleanup(controller.renderer.close)
            controller.thumbnail = QUrl.fromLocalFile(path).toString()
            self.engine.rootContext().setContextProperty("AppController", controller)
            window = self.create_window('''
property int commits: 0
property int lastWidth: 0
property int lastHeight: 0
property var lastAppearancePatch: ({})
SubtitlePreviewDialog {
    id: dialog; objectName: "autoDialog"
    coverEnabled: true; autoAlignToCover: true
    coverLayout: ({fontSize: 68, positionXPercent: 50, positionYPercent: 70,
        boxWidthPercent: 50, boxHeightPercent: 12})
    onAutoAlignmentEdited: function(enabled) { autoAlignToCover = enabled; }
    onSubtitleLayoutEdited: function(font, x, y, w, h) {
        root.commits += 1; root.lastWidth = w; root.lastHeight = h;
    }
    onSubtitleAppearanceEdited: function(patch) { root.lastAppearancePatch = patch; }
}
function openPreview() { dialog.openWithLayout(68, 50, 70, 35, 12); }
''')
            window.openPreview()
            QTest.qWait(180)
            dialog = window.findChild(QObject, "autoDialog")
            for redundant in ("subtitleFontFamilyField", "subtitleAppearanceFontSize",
                              "subtitleShadowField", "subtitleLetterSpacingField",
                              "subtitleUppercaseToggle"):
                self.assertIsNone(window.findChild(QObject, redundant))
            overlay = window.findChild(QQuickItem, "autoSubtitleTransformOverlay")
            self.assertTrue(dialog.property("layoutLocked"))
            self.assertFalse(overlay.property("editing"))
            check = window.findChild(QQuickItem, "subtitleAutoCoverCheck")
            point = check.mapToScene(QPointF(10, check.height()/2)).toPoint()
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
            QTest.qWait(60)
            self.assertFalse(dialog.property("layoutLocked"))
            self.assertTrue(overlay.property("editing"))

            bold = window.findChild(QQuickItem, "compactBoldToggle")
            point_bold = bold.mapToScene(QPointF(10, bold.height()/2)).toPoint()
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point_bold)
            QTest.qWait(60)
            self.assertTrue(dialog.property("draftAppearance").toVariant()["bold"])
            self.assertEqual(window.property("lastAppearancePatch").toVariant(), {"bold": True})
            strip = window.findChild(QQuickItem, "subtitleTextColorStrip")
            def visual_items(item):
                yield item
                for child in item.childItems():
                    yield from visual_items(child)
            red = next(item for item in visual_items(strip)
                       if item.property("modelData") == "#EF5350")
            point_red = red.mapToScene(QPointF(red.width()/2, red.height()/2)).toPoint()
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point_red)
            QTest.qWait(60)
            self.assertEqual(dialog.property("draftAppearance").toVariant()["text_color"], "#EF5350")

            def find_visual(item, name):
                if item.objectName() == name:
                    return item
                for child in item.childItems():
                    found = find_visual(child, name)
                    if found is not None:
                        return found
                return None

            selection = window.findChild(QQuickItem, "subtitleTransformSelection")
            handle = find_visual(window.contentItem(), "subtitleBoxHandle_1_0")
            self.assertIsNotNone(handle)
            self.assertAlmostEqual(handle.x() + handle.width()/2, selection.width(), delta=.1)
            words_before = len(overlay.property("sampleText").split())
            start = handle.mapToScene(QPointF(handle.width()/2, handle.height()/2)).toPoint()
            QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
            QTest.mouseMove(window, start + QPointF(75, 0).toPoint(), 150)
            self.assertEqual(window.property("commits"), 0)
            QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, start + QPointF(75, 0).toPoint())
            QTest.qWait(160)
            self.assertGreater(len(overlay.property("sampleText").split()), words_before)
            self.assertEqual(dialog.property("draftFontSize"), 68)
            self.assertEqual(dialog.property("draftBoxWidth"), window.property("lastWidth"))
            self.assertNotIn("\n", overlay.property("sampleText"))
            bottom = find_visual(window.contentItem(), "subtitleBoxHandle_0_1")
            start = bottom.mapToScene(QPointF(bottom.width()/2, bottom.height()/2)).toPoint()
            QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
            QTest.mouseMove(window, start + QPointF(0, 75).toPoint(), 150)
            QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, start + QPointF(0, 75).toPoint())
            QTest.qWait(160)
            self.assertIn("\n", overlay.property("sampleText"))
            self.assertEqual(dialog.property("draftBoxHeight"), window.property("lastHeight"))
            self.assertEqual(dialog.property("draftFontSize"), 68)
            # The auto sample shows one moment on the shared sequential clock,
            # never the same percentage on every row after increasing height.
            for _attempt in range(40):
                sample_frame = overlay.property("sprite").toVariant()
                if sample_frame.get("lineCount", 0) > 1:
                    break
                time.sleep(.025)  # Release the GIL for the Python raster worker.
                QTest.qWait(25)
            self.assertGreater(sample_frame.get("lineCount", 0), 1,
                f"frame={controller.renderer.frame}; events={controller.renderer._events}; "
                f"pending={controller.renderer._pending}; errors={renderer_errors}")
            lines = sample_frame["karaokeLines"]
            elapsed_cs = sum(line["durationCs"] for line in lines) * .45
            self.assertGreater(lines[0]["progress"], 0)
            for index, line in enumerate(lines):
                expected = max(0, min(1, (elapsed_cs - line["startCs"]) / line["durationCs"]))
                self.assertAlmostEqual(line["progress"], expected)
                if index and line["progress"] > 0:
                    self.assertEqual(lines[index - 1]["progress"], 1)
            preview_directory = os.environ.get("HAIZFLOW_UI_PREVIEWS")
            if preview_directory:
                window.grabWindow().save(str(Path(preview_directory) / "auto-subtitle.png"))
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
            QTest.qWait(80)
            self.assertTrue(dialog.property("layoutLocked"))
            self.assertFalse(overlay.property("editing"))
            self.assertFalse(bold.isEnabled())
            dialog.close()
            QTest.qWait(80)
            self.assertEqual(controller.renderer.frame, {})

    def test_watermark_blur_commits_vietnamese_edits_once_and_repeats(self):
        from haizflow.desktop.input_method_commit_filter import InputMethodCommitFilter

        window = self.create_window('''
property int commits: 0
property string savedText: ""
AutoSaveTextField {
    objectName: "watermarkAutoSave"; x: 40; y: 40; width: 360
    onValueCommitted: function(value) { root.savedText = value; root.commits += 1; }
}
''')
        field = window.findChild(QQuickItem, "watermarkAutoSave")
        event_filter = InputMethodCommitFilter(self.app)
        self.app.installEventFilter(event_filter)
        try:
            for index, text in enumerate(("Nội dung tiếng Việt", "Dòng chữ đã sửa"), 1):
                QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPointF(80, 60).toPoint())
                field.selectAll()
                event = QInputMethodEvent()
                event.setCommitString(text)
                self.app.sendEvent(field, event)
                self.assertEqual(window.property("commits"), index - 1)
                QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPointF(800, 600).toPoint())
                QTest.qWait(20)
                self.assertEqual(window.property("savedText"), text)
                self.assertEqual(window.property("commits"), index)
                self.assertFalse(field.property("activeFocus"))
            field.setProperty("text", "Loaded from another project")
            QTest.qWait(20)
            self.assertEqual(window.property("commits"), 2)
        finally:
            self.app.removeEventFilter(event_filter)

    def test_multiline_karaoke_masks_advance_sequentially_without_recreating_delegates(self):
        import tempfile

        from haizflow.desktop.subtitle_overlay_renderer import SubtitleOverlayRenderer, export_events, rasterize

        with tempfile.TemporaryDirectory() as directory:
            layout = dict(outputWidth=720, outputHeight=1280, layoutWidth=320, layoutHeight=270,
                          fontSize=60, outline=3, positionXPercent=50, positionYPercent=65,
                          fontFamily="Bangers", shadow=0)
            header, events = export_events([dict(start=0, end=9,
                text="Những người bạn đang trò chuyện trong căn phòng vào buổi tối")],
                layout, True, Path(directory))
            event = next(event for event in events if event["body"].count(r"\N") == 2)
            frame = rasterize(header, event["body"], layout, Path(directory))
            window = self.create_window('''
SubtitleTransformOverlay {
    objectName: "transform"; anchors.fill: parent
    videoRect: Qt.rect(320, 40, 360, 640)
    fontSize: 60; positionXPercent: 50; positionYPercent: 65
    referenceWidthPixels: 720; referenceHeightPixels: 1280
}
''')
            overlay = window.findChild(QQuickItem, "transform")

            def visual_find(item, name):
                if item.objectName() == name:
                    return item
                for child in item.childItems():
                    found = visual_find(child, name)
                    if found is not None:
                        return found
                return None

            renderer = SubtitleOverlayRenderer()
            try:
                renderer._events = [event]
                renderer._cache[(0, event["body"])] = frame
                delegates = None
                for active_index in (0, 1, 2, 0):  # Includes seeking backwards.
                    clock = frame["karaokeLines"][active_index]
                    renderer.seek(event["start"] + (clock["startCs"] + clock["durationCs"] / 2) / 100)
                    overlay.setProperty("sprite", renderer.frame)
                    QTest.qWait(30)
                    masks = [visual_find(window.contentItem(), f"subtitleKaraokeLine{i}") for i in range(3)]
                    self.assertTrue(all(mask is not None for mask in masks))
                    if delegates is not None:
                        self.assertEqual(masks, delegates)
                    delegates = masks
                    for _attempt in range(40):
                        ready = all(QQmlExpression(self.engine.rootContext(), child,
                            "Number(status)").evaluate()[0] == 1
                            for mask in masks for child in mask.childItems())
                        if ready:
                            break
                        time.sleep(.025)
                        QTest.qWait(25)
                    self.assertTrue(ready, "Karaoke image did not finish loading")
                    for index, mask in enumerate(masks):
                        expected_progress = 1 if index < active_index else .5 if index == active_index else 0
                        self.assertAlmostEqual(mask.width(),
                            frame["karaokeLines"][index]["width"] / 2 * expected_progress, delta=.01)
                        if index:
                            self.assertGreaterEqual(mask.y(), masks[index - 1].y() + masks[index - 1].height())
                    screenshot = window.grabWindow()
                    if os.environ.get("HAIZFLOW_KARAOKE_PREVIEW"):
                        screenshot.save(os.environ["HAIZFLOW_KARAOKE_PREVIEW"])
                    self.assertFalse(screenshot.isNull())
                    for index, mask in enumerate(masks):
                        position = mask.mapToScene(QPointF())
                        line = frame["karaokeLines"][index]
                        yellow = 0
                        for y in range(round(position.y()), round(position.y() + line["height"] / 2)):
                            for x in range(round(position.x()), round(position.x() + line["width"] / 2)):
                                color = screenshot.pixelColor(x, y)
                                yellow += color.red() > 150 and color.green() > 140 and color.blue() < 80
                        if index > active_index:
                            self.assertEqual(yellow, 0)
                        else:
                            self.assertGreater(yellow, 10,
                                f"row={index}; active={active_index}; position={position}; size={screenshot.size()}")
            finally:
                renderer.close()

    def test_selection_hugs_real_caption_pixels_and_horizontal_drag_changes_capacity(self):
        import json
        import tempfile

        from haizflow.desktop.subtitle_overlay_renderer import export_events, rasterize

        with tempfile.TemporaryDirectory() as directory:
            layout = dict(outputWidth=720, outputHeight=1280, layoutWidth=640, layoutHeight=205,
                          fontSize=112, outline=10, positionXPercent=50, positionYPercent=79,
                          fontFamily="Bangers")
            header, events = export_events([dict(start=0, end=3, text="Một câu ngắn")],
                                          layout, True, Path(directory))
            frame = rasterize(header, events[0]["body"], layout, Path(directory))
            window = self.create_window('''
property int commits: 0
SubtitleTransformOverlay {
    objectName: "transform"; anchors.fill: parent
    videoRect: Qt.rect(320, 40, 360, 640)
    fontSize: 112; positionXPercent: 50; positionYPercent: 79
    referenceWidthPixels: 720; referenceHeightPixels: 1280
    boxWidthPercent: 89; boxHeightPercent: 16
    interactive: true; editing: true
    onLayoutCommitted: function(font, x, y, w, h) {
        root.commits += 1;
        fontSize = font; positionXPercent = x; positionYPercent = y;
        boxWidthPercent = w; boxHeightPercent = h;
    }
}
''')
            overlay = window.findChild(QQuickItem, "transform")
            overlay.setProperty("sprite", frame)
            QTest.qWait(60)
            selection = window.findChild(QQuickItem, "subtitleTransformSelection")
            self.assertAlmostEqual(selection.width(), frame["width"] / 2 + 6, delta=0.1)
            self.assertAlmostEqual(selection.height(), frame["height"] / 2 + 6, delta=0.1)
            self.assertAlmostEqual(selection.x(), frame["x"] / 2 - 3, delta=0.1)
            self.assertAlmostEqual(selection.y(), frame["y"] / 2 - 3, delta=0.1)
            self.assertLess(selection.width(), 360 * 0.89)
            window.setProperty("visible", True)
            preview_path = os.environ.get("HAIZFLOW_CROP_PREVIEW")
            if preview_path:
                window.grabWindow().save(preview_path)

            def visual_find(item, name):
                if item.objectName() == name:
                    return item
                for child in item.childItems():
                    found = visual_find(child, name)
                    if found is not None:
                        return found
                return None

            handle = visual_find(window.contentItem(), "subtitleBoxHandle_1_0")
            initial_width = selection.width()
            start = handle.mapToScene(QPointF(handle.width() / 2, handle.height() / 2)).toPoint()
            QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
            for delta in (-15, -30, -50):
                QTest.mouseMove(window, start + QPointF(delta, 0).toPoint(), 40)
                self.assertAlmostEqual(selection.width(), initial_width + delta, delta=1)
                self.assertEqual(overlay.property("draftFontSize"), 112)
                self.assertEqual(window.property("commits"), 0)
            QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, start + QPointF(-50, 0).toPoint())
            QTest.qWait(30)
            self.assertLess(overlay.property("boxWidthPercent"), 89)
            self.assertEqual(overlay.property("fontSize"), 112)
            self.assertEqual(window.property("commits"), 1)
            self.assertFalse(overlay.property("boxResizeActive"))
            # A real renderer update may change bounds; the resting frame must
            # still fit those bounds, never grow back to the capacity region.
            frame = dict(frame, width=frame["width"] * 0.6)
            overlay.setProperty("sprite", json.loads(json.dumps(frame)))
            QTest.qWait(30)
            self.assertAlmostEqual(selection.width(), frame["width"] / 2 + 6, delta=0.1)


def test_subtitle_editing_in_isolated_qt_process():
    completed = subprocess.run([sys.executable, str(Path(__file__).resolve())],
                               capture_output=True, text=True, timeout=45)
    assert completed.returncode == 0, completed.stdout + completed.stderr


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

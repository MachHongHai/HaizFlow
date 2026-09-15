import os
import re
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from haizflow.desktop.models import ProjectBrowserProxyModel, ProjectListModel


ROOT = Path(__file__).resolve().parents[1]
QML_DIR = ROOT / "src" / "haizflow" / "desktop" / "qml"


class UiFoundationTests(unittest.TestCase):
    @staticmethod
    def _contrast_ratio(first: str, second: str) -> float:
        def luminance(value: str) -> float:
            channels = [int(value[index : index + 2], 16) / 255 for index in (1, 3, 5)]
            linear = [
                channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels
            ]
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

        high, low = sorted((luminance(first), luminance(second)), reverse=True)
        return (high + 0.05) / (low + 0.05)

    def test_english_catalog_is_complete_and_loads_at_runtime(self):
        translation_dir = ROOT / "src" / "haizflow" / "desktop" / "translations"
        catalog_source = translation_dir / "haizflow_en.ts"
        catalog_binary = translation_dir / "haizflow_en.qm"
        tree = ET.parse(catalog_source)
        unfinished = tree.findall(".//translation[@type='unfinished']")
        self.assertEqual(unfinished, [])
        self.assertTrue(catalog_binary.is_file())

        script = f"""
from PySide6.QtCore import QCoreApplication, QTranslator
app = QCoreApplication([])
translator = QTranslator(app)
assert translator.load(r'{catalog_binary}')
assert app.installTranslator(translator)
assert QCoreApplication.translate('HomePage', 'Dự án gần đây') == 'Recent projects'
assert QCoreApplication.translate('ProjectSetupDialog', 'Tạo dự án') == 'Create project'
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_ui_gallery_creates_offscreen(self):
        script = f"""
from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
app = QGuiApplication([])
engine = QQmlEngine()
engine.addImportPath(r'{QML_DIR}')
component = QQmlComponent(engine, QUrl.fromLocalFile(r'{QML_DIR / "UiGallery.qml"}'))
assert component.isReady(), '\\n'.join(error.toString() for error in component.errors())
for width, height in ((1120, 720), (1440, 900), (1920, 1080), (2560, 1440)):
    gallery = component.create()
    assert gallery is not None, '\\n'.join(error.toString() for error in component.errors())
    gallery.setProperty('width', width)
    gallery.setProperty('height', height)
    app.processEvents()
    assert gallery.property('width') == width
    assert gallery.property('height') == height
    gallery.deleteLater()
    app.processEvents()
"""
        environment = os.environ.copy()
        environment["QT_QPA_PLATFORM"] = "offscreen"
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_home_uses_real_actions_and_an_empty_tutorial_frame(self):
        home = (QML_DIR / "HomePage.qml").read_text(encoding="utf-8")
        hero = (QML_DIR / "HomeHero.qml").read_text(encoding="utf-8")
        tutorial = (QML_DIR / "TutorialPlaceholder.qml").read_text(encoding="utf-8")

        self.assertIn("HomeHero {", home)
        self.assertIn("HomeCreatorPanel {", home)
        self.assertEqual(home.count("HomeActionButton {"), 4)
        self.assertIn("TutorialPlaceholder {", home)
        self.assertIn('qsTr("Biên dịch video ngay trên máy")', hero)
        self.assertNotIn("MediaPlayer", tutorial)
        self.assertNotIn("VideoOutput", tutorial)

    def test_ui_gallery_renders_at_supported_dpi_scales(self):
        script = f"""
from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickView
app = QGuiApplication([])
view = QQuickView()
view.engine().addImportPath(r'{QML_DIR}')
view.setResizeMode(QQuickView.SizeRootObjectToView)
view.setSource(QUrl.fromLocalFile(r'{QML_DIR / "UiGallery.qml"}'))
assert view.status() == QQuickView.Ready, '\\n'.join(error.toString() for error in view.errors())
for width, height in ((1120, 720), (1440, 900), (1920, 1080), (2560, 1440)):
    view.resize(width, height)
    view.show()
    for _ in range(4):
        app.processEvents()
    image = view.grabWindow()
    assert not image.isNull()
    assert image.width() >= width and image.height() >= height
view.close()
"""
        for scale in ("1", "1.25", "1.5", "1.75"):
            environment = os.environ.copy()
            environment["QT_QPA_PLATFORM"] = "offscreen"
            environment["QT_SCALE_FACTOR"] = scale
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            self.assertEqual(result.returncode, 0, f"DPI {scale}: {result.stdout}{result.stderr}")

    def test_warm_graphite_text_and_focus_contrast(self):
        theme = (QML_DIR / "Theme.qml").read_text(encoding="utf-8")
        colors = dict(re.findall(r"readonly property color (\w+): \"(#[0-9A-Fa-f]{6})\"", theme))
        for foreground, background, minimum in (
            ("text", "window", 4.5),
            ("text", "surface", 4.5),
            ("textMuted", "surface", 4.5),
            ("textOnAccent", "interactive", 4.5),
            ("focus", "window", 3.0),
        ):
            self.assertGreaterEqual(
                self._contrast_ratio(colors[foreground], colors[background]),
                minimum,
                f"{foreground} on {background}",
            )

    def test_project_browser_filters_and_sorts_without_copying_rows(self):
        source = ProjectListModel()
        browser = ProjectBrowserProxyModel(source)
        source.set_projects(
            [
                {
                    "key": "auto",
                    "project_name": "Zulu",
                    "project_type": "single",
                    "video_count": 1,
                    "status": "done",
                    "progress": 100,
                    "thumbnail_source": "",
                    "activity_at": "2026-08-01T00:00:00Z",
                },
                {
                    "key": "manual",
                    "project_name": "Alpha",
                    "project_type": "manual",
                    "video_count": 1,
                    "status": "processing",
                    "progress": 40,
                    "thumbnail_source": "",
                    "activity_at": "2026-08-27T00:00:00Z",
                },
                {
                    "key": "downloads",
                    "project_name": "Downloaded clips",
                    "project_type": "download",
                    "video_count": 3,
                    "status": "ready",
                    "progress": 0,
                    "thumbnail_source": "",
                    "activity_at": "2026-08-20T00:00:00Z",
                },
                {
                    "key": "publishing",
                    "project_name": "Publishing queue",
                    "project_type": "publish",
                    "video_count": 2,
                    "status": "ready",
                    "progress": 0,
                    "thumbnail_source": "",
                    "activity_at": "2026-08-19T00:00:00Z",
                },
            ]
        )
        self.assertEqual(browser.rowCount(), 4)
        self.assertEqual(browser.project_at(0)["project_name"], "Alpha")
        browser.typeFilter = "single"
        self.assertEqual(browser.rowCount(), 1)
        self.assertEqual(browser.project_at(0)["project_name"], "Zulu")
        browser.typeFilter = "all"
        browser.query = "alp"
        self.assertEqual(browser.rowCount(), 1)
        self.assertEqual(browser.project_at(0)["key"], "manual")
        browser.query = ""
        browser.typeFilter = "download"
        self.assertEqual(browser.rowCount(), 1)
        self.assertEqual(browser.project_at(0)["key"], "downloads")
        browser.typeFilter = "publish"
        self.assertEqual(browser.rowCount(), 1)
        self.assertEqual(browser.project_at(0)["key"], "publishing")

    def test_bundled_fluent_icons_use_the_warm_graphite_palette(self):
        icon_dir = QML_DIR / "icons"
        icons = list(icon_dir.glob("*.svg"))
        self.assertGreater(len(icons), 0)
        for icon in icons:
            source = icon.read_text(encoding="utf-8")
            self.assertNotIn("#7CC6DF", source, icon.name)
            self.assertNotIn("#A8B3C1", source, icon.name)
            expected = "#C4915E" if icon.stem.endswith("-accent") else "#B8B1A6"
            self.assertIn(expected, source, icon.name)

    def test_user_dialogs_share_the_studio_shell(self):
        migrated_dialogs = (
            "AudioMixDialog.qml",
            "BatchAudioMixDialog.qml",
            "DownloadProjectSourceDialog.qml",
            "SocialProjectSourceDialog.qml",
            "SocialDefaultsDialog.qml",
            "SocialPublishConfirmDialog.qml",
            "UrlImportDialog.qml",
            "ZernioApiKeyDialog.qml",
            "ZernioConnectionDialog.qml",
            "ZernioGuideDialog.qml",
            "ZernioPostOptionsDialog.qml",
        )
        for filename in migrated_dialogs:
            source = (QML_DIR / filename).read_text(encoding="utf-8")
            self.assertIn("AppDialog {", source, filename)
            self.assertNotIn("\nDialog {", source, filename)

        dialog_shell = (QML_DIR / "AppDialog.qml").read_text(encoding="utf-8")
        self.assertIn("readonly property int footerHeight", dialog_shell)
        self.assertIn("Layout.preferredHeight: root.footerHeight", dialog_shell)
        self.assertIn('objectName: "appDialogBackground"', dialog_shell)
        self.assertIn('objectName: "appDialogFooter"', dialog_shell)

        progress = (QML_DIR / "AppProgressBar.qml").read_text(encoding="utf-8")
        self.assertNotIn('tone === "blue"', progress)
        self.assertNotIn('tone === "violet"', progress)

    def test_user_actions_use_the_shared_studio_button(self):
        allowed_base_button_files = {"AppButton.qml", "StudioButton.qml", "UiGallery.qml"}
        legacy_uses = []
        for source_file in QML_DIR.glob("*.qml"):
            if source_file.name in allowed_base_button_files:
                continue
            if "AppButton {" in source_file.read_text(encoding="utf-8"):
                legacy_uses.append(source_file.name)
        self.assertEqual(legacy_uses, [])

    def test_app_dialog_footer_stays_inside_its_background(self):
        script = f"""
from PySide6.QtCore import QObject, QPointF, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem
app = QGuiApplication([])
engine = QQmlEngine()
engine.addImportPath(r'{QML_DIR}')
component = QQmlComponent(engine)
component.setData(b'''import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "{QML_DIR.as_uri()}"
ApplicationWindow {{
    width: 900; height: 700; visible: true
    AppDialog {{
        objectName: "testDialog"
        title: "Dialog"
        Text {{ text: "Body"; Layout.fillWidth: true }}
        footerActions: [
            StudioButton {{ text: "Cancel"; variant: "ghost" }},
            StudioButton {{ objectName: "acceptButton"; text: "Accept"; variant: "primary" }}
        ]
        Component.onCompleted: open()
    }}
}}''', QUrl())
assert component.isReady(), '\\n'.join(error.toString() for error in component.errors())
window = component.create()
assert window is not None, '\\n'.join(error.toString() for error in component.errors())
for _ in range(8):
    app.processEvents()
dialog = window.findChild(QObject, "testDialog")
background = window.findChild(QQuickItem, "appDialogBackground")
footer = window.findChild(QQuickItem, "appDialogFooter")
button = window.findChild(QQuickItem, "acceptButton")
dialog_bottom = float(dialog.property("y")) + float(dialog.property("height"))
assert abs(float(background.property("height")) - float(dialog.property("height"))) <= 0.5
assert footer.mapToScene(QPointF(0, float(footer.property("height")))).y() <= dialog_bottom + 0.5
assert button.mapToScene(QPointF(0, float(button.property("height")))).y() <= dialog_bottom + 0.5
window.close()
"""
        environment = os.environ.copy()
        environment["QT_QPA_PLATFORM"] = "offscreen"
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_static_qml_copy_uses_the_qt_catalog(self):
        legacy_calls = []
        for source_file in QML_DIR.glob("*.qml"):
            source = source_file.read_text(encoding="utf-8")
            if "I18n.t(" in source:
                legacy_calls.append(source_file.name)
        self.assertEqual(legacy_calls, [])

        runtime_text = (QML_DIR / "I18n.qml").read_text(encoding="utf-8")
        self.assertNotIn("function t(", runtime_text)
        self.assertIn("fixedVietnamese", runtime_text)
        self.assertLess(len(runtime_text.splitlines()), 400)

    def test_heavy_dialogs_are_created_on_demand(self):
        expected_loaders = {
            "Main.qml": 5,
            "DubbingSetupPanel.qml": 5,
            "ManualStageInspector.qml": 3,
            "BatchSettingsDialog.qml": 4,
            "SocialPublishPage.qml": 7,
        }
        for filename, minimum_count in expected_loaders.items():
            source = (QML_DIR / filename).read_text(encoding="utf-8")
            self.assertGreaterEqual(source.count("LazyDialogLoader {"), minimum_count, filename)
            self.assertIn(".invoke(", source, filename)

        loader = (QML_DIR / "LazyDialogLoader.qml").read_text(encoding="utf-8")
        self.assertIn("status !== Loader.Ready", loader)
        self.assertIn("active = false", loader)

    def test_manual_editor_keeps_subtitle_editing_out_of_the_visual_tool(self):
        inspector = (QML_DIR / "ManualStageInspector.qml").read_text(encoding="utf-8")
        visual_start = inspector.index("id: imageInspectorComponent")
        visual_end = inspector.index("id: voiceInspectorComponent")
        visual_tool = inspector[visual_start:visual_end]
        self.assertIn('text: qsTr("Phụ đề gốc")', visual_tool)
        self.assertNotIn("id: subtitleTextEditor", visual_tool)
        self.assertIn('qsTr("Che · Làm mờ")', visual_tool)
        self.assertIn('qsTr("Che · Vá nền")', visual_tool)
        self.assertIn("setManualSubtitleTreatment", visual_tool)
        self.assertIn('qsTr("Áp dụng")', visual_tool)
        self.assertLess(visual_tool.index("onActivated:"), visual_tool.index("setManualSubtitleTreatment"))
        activated_body = visual_tool[visual_tool.index("onActivated:"):visual_tool.index("StudioButton {")]
        self.assertNotIn("setManualSubtitleTreatment", activated_body)
        self.assertNotIn('qsTr("Che phụ đề")', visual_tool)
        self.assertNotIn("helpText:", visual_tool)
        self.assertIn("id: subtitleInspectorComponent", inspector)
        self.assertIn('"source", "translation", "subtitle", "image"', inspector)

    def test_manual_source_and_audio_are_direct_controls(self):
        inspector = (QML_DIR / "ManualStageInspector.qml").read_text(encoding="utf-8")
        source_start = inspector.index("id: sourceInspectorComponent")
        source_end = inspector.index("id: translationInspectorComponent")
        source_tool = inspector[source_start:source_end]
        audio_start = inspector.index("id: audioInspectorComponent")
        audio_end = inspector.index("id: exportInspectorComponent")
        audio_tool = inspector[audio_start:audio_end]

        self.assertIn('qsTr("Từ tệp")', source_tool)
        self.assertIn('qsTr("Từ liên kết")', source_tool)
        self.assertIn('qsTr("Giữ âm thanh gốc")', source_tool)
        self.assertIn('qsTr("Tách giọng")', source_tool)
        self.assertNotIn("Chuẩn bị âm thanh", source_tool)
        self.assertGreaterEqual(audio_tool.count("AudioLevelControl"), 3)
        self.assertIn('root.hasCurrentCache("voice")', audio_tool)
        self.assertNotIn("nghe thử", audio_tool.lower())
        self.assertNotIn("AudioMixDialog", inspector)
        self.assertIn("onCurrentStageChanged: inspectorScroll.contentY = 0", inspector)
        self.assertIn("id: stageLoader", inspector)
        self.assertIn("id: imageInspectorComponent", inspector)
        self.assertIn("id: audioInspectorComponent", inspector)
        self.assertIn('objectName: "manualInspectorScroll"', inspector)
        self.assertIn("Layout.maximumHeight: implicitHeight", inspector)
        self.assertEqual(inspector.count("parent: root\n        sourceComponent:"), 5)
        self.assertNotIn('text: qsTr("Chỉnh bố cục")', inspector)
        self.assertIn("ManualSubtitleEditorDialog", inspector)
        self.assertIn('qsTr("Mở rộng")', inspector)
        subtitle_dialog = (QML_DIR / "ManualSubtitleEditorDialog.qml").read_text(encoding="utf-8")
        self.assertIn("preferredWidth: 1080", subtitle_dialog)
        self.assertIn("preferredHeight: 760", subtitle_dialog)
        self.assertIn("SubtitleTextEditor {", subtitle_dialog)
        compare_preview = (QML_DIR / "ManualComparePreview.qml").read_text(encoding="utf-8")
        transform_overlay = (QML_DIR / "SubtitleTransformOverlay.qml").read_text(encoding="utf-8")
        self.assertIn("SubtitleTransformOverlay {", compare_preview)
        self.assertIn("signal layoutCommitted", transform_overlay)
        self.assertIn("signal layoutPreviewChanged", transform_overlay)
        self.assertIn('objectName: "subtitleTransformSprite"', transform_overlay)
        self.assertIn("root.sprite.normal", transform_overlay)
        self.assertIn("root.sprite.karaoke", transform_overlay)

        self.assertNotIn("textMeasure", transform_overlay)
        self.assertNotIn("FontLoader", transform_overlay)
        self.assertIn("selection.rasterScale", transform_overlay)
        self.assertIn("visible: root.livePreviewVisible", transform_overlay)
        self.assertIn("signal activated()", transform_overlay)
        self.assertEqual(transform_overlay.count("ScaleHandle {"), 4)
        self.assertIn("Qt.SizeFDiagCursor : Qt.SizeBDiagCursor", transform_overlay)
        self.assertIn("cursorShape: root.editing ? Qt.SizeAllCursor : Qt.PointingHandCursor", transform_overlay)
        self.assertNotIn("visible: root.currentStage", inspector)

        self.assertNotIn('qsTr("Cắt khung hình")', inspector)
        self.assertNotIn("CropTransformOverlay {", compare_preview)

        activity_tray = (QML_DIR / "ActivityTray.qml").read_text(encoding="utf-8")
        self.assertIn("implicitHeight: UiMetrics.activityTrayHeight", activity_tray)
        self.assertIn("visible: true", activity_tray)
        navigation_rail = (QML_DIR / "NavigationRail.qml").read_text(encoding="utf-8")
        self.assertNotIn("runtimeMessage", navigation_rail)
        self.assertNotIn("runtimeState", navigation_rail)
        self.assertNotIn("InlineBanner {", navigation_rail)

        workspace = (QML_DIR / "ManualWorkspace.qml").read_text(encoding="utf-8")
        timeline = (QML_DIR / "SubtitleTimeline.qml").read_text(encoding="utf-8")
        self.assertIn("function selectSubtitle(index, seek)", workspace)
        self.assertNotIn("onSegmentEditRequested:", workspace)
        self.assertNotIn("openEditor", workspace)
        self.assertIn("signal segmentFocused(int index)", timeline)
        self.assertNotIn("signal segmentEditRequested(int index)", timeline)
        self.assertIn("if (timingChanged)", timeline)
        self.assertIn("else\n                                root.segmentSelected(sourceIndex);", timeline)
        self.assertIn("subtitleInteractive: root.previewSubtitleIndex >= 0", workspace)
        self.assertIn("subtitleTransformActive = true", workspace)
        self.assertIn("onSubtitleActivated:", workspace)
        self.assertIn("saveManualSubtitleTiming", workspace)
        self.assertNotIn("approveTranslationReview", workspace)
        self.assertIn("AppController.subtitleOverlayRenderer.frame", workspace)
        self.assertIn("AppController.adoptSubtitlePreviewLayout()", workspace)
        self.assertIn("previewMedia.subtitleRenderLayout", workspace)
        self.assertIn("subtitleAudioRefreshPending", workspace)
        activated_block = workspace[
            workspace.index("onSubtitleActivated:") : workspace.index("onSubtitleEditingDismissed:")
        ]
        self.assertNotIn("adoptSubtitlePreviewLayout", activated_block)
        self.assertIn("subtitleLivePreviewEnabled: true", workspace)
        self.assertIn(
            "effectiveResultSource: subtitleLivePreviewEnabled",
            compare_preview,
        )
        self.assertNotIn("cropEditEnabled:", workspace)
        self.assertIn("subtitleKaraokeProgress: root.previewSubtitleKaraokeProgress", workspace)
        self.assertIn("subtitleLayoutWidth: root.subtitleLayoutWidth", workspace)
        self.assertIn("subtitleLayoutHeight: root.subtitleLayoutHeight", workspace)
        self.assertIn("root.subtitleTransformActive = false;", workspace)
        self.assertIn("onInteractionDismissed: root.dismissSubtitleEditor()", workspace)
        committed_block = workspace[
            workspace.index("onSubtitleLayoutCommitted:") : workspace.index(
                "ManualStageInspector {"
            )
        ]
        self.assertNotIn("root.subtitleTransformActive = false", committed_block)

        panel = (QML_DIR / "InspectorPanel.qml").read_text(encoding="utf-8")
        self.assertIn("Layout.fillHeight: true", panel)

    def test_manual_subtitle_editor_dialog_is_large_and_responsive(self):
        script = f"""
from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
app = QGuiApplication([])
engine = QQmlEngine()
engine.addImportPath(r'{QML_DIR}')
source = '''import QtQuick
import QtQuick.Controls.Basic
import "{QML_DIR.as_uri()}"
ApplicationWindow {{
    width: 1120
    height: 720
    visible: true
    QtObject {{
        id: fakeController
        signal manualSubtitleSaved(string id, int revision, string requestId)
        signal manualSubtitleSaveFailed(string id, string requestId, string message)
    }}
    ManualSubtitleEditorDialog {{
        id: subtitleDialog
        controller: fakeController
        segment: ({{"segment_id": "segment-1", "text": "Một đoạn phụ đề dài", "revision": 1,
            "start": 1.25, "end": 5.5}})
        selectedIndex: 0
        segmentCount: 8
        Component.onCompleted: openForSelection()
    }}
}}'''.encode('utf-8')
component = QQmlComponent(engine)
component.setData(source, QUrl())
assert component.isReady(), '\\n'.join(error.toString() for error in component.errors())
window = component.create()
assert window is not None, '\\n'.join(error.toString() for error in component.errors())
for _ in range(6):
    app.processEvents()
dialog = window.findChild(QObject, 'manualSubtitleEditorDialog')
editor = window.findChild(QObject, 'manualSubtitleTextInput')
assert dialog is not None and editor is not None
assert dialog.property('width') == 1072
assert dialog.property('height') == 672
assert editor.property('height') >= 440
window.close()
window.deleteLater()
app.processEvents()
"""
        environment = os.environ.copy()
        environment["QT_QPA_PLATFORM"] = "offscreen"
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_manual_visual_and_audio_inspectors_keep_the_full_scroll_viewport(self):
        script = f"""\
from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlPropertyMap

app = QGuiApplication([])
engine = QQmlEngine()
controller = QQmlPropertyMap()
for name, value in {{
    "canEditSelectedVideo": True,
    "hasSelectedVideo": True,
    "isSelectedVideoQueued": True,
    "isSelectedVideoProcessing": False,
    "selectedStatus": "queued",
    "selectedVideoId": "video-1",
    "manualTargetStage": "translation",
    "selectedProgressDetail": "Queued",
    "selectedStep": "",
    "selectedProgress": 20,
    "removeOriginalSubtitles": True,
    "originalSubtitleRemovalMode": "blur",
    "watermarkText": "HaizFlow",
    "backgroundMusicPath": "",
}}.items():
    controller.insert(name, value)
engine.rootContext().setContextProperty("AppController", controller)
component = QQmlComponent(engine)
component.setData(b'''import QtQuick
import QtQuick.Controls.Basic
import "{QML_DIR.as_uri()}"
ApplicationWindow {{
    width: 288
    height: 536
    visible: true
    ManualStageInspector {{
        id: inspector
        objectName: "manualInspector"
        anchors.fill: parent
        subtitleSegments: [{{"text": "Example"}}]
    }}
}}''', QUrl())
assert component.isReady(), "\\n".join(error.toString() for error in component.errors())
window = component.create()
assert window is not None, "\\n".join(error.toString() for error in component.errors())
app.processEvents()
inspector = window.findChild(QObject, "manualInspector")
scroll = window.findChild(QObject, "manualInspectorScroll")
loader = window.findChild(QObject, "manualInspectorStageLoader")
footer = window.findChild(QObject, "manualInspectorActionFooter")
for stage in range(8):
    inspector.setProperty("currentStage", stage)
    app.processEvents()
    assert float(scroll.property("height")) > 300
    assert float(scroll.property("height")) >= float(loader.property("height"))
assert float(footer.property("height")) <= float(footer.property("implicitHeight")) + 0.01
window.close()
window.deleteLater()
engine.deleteLater()
app.processEvents()
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_subtitle_transform_overlay_activates_from_a_direct_video_click(self):
        script = f"""\
from PySide6.QtCore import QPoint, QPointF, QUrl, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

app = QGuiApplication([])
engine = QQmlEngine()
engine.addImportPath(r'{QML_DIR}')
component = QQmlComponent(engine)
component.setData(b'''import QtQuick
import QtQuick.Controls.Basic
import "{QML_DIR.as_uri()}"
ApplicationWindow {{
    id: window
    width: 800
    height: 600
    visible: true
    property int activations: 0
    SubtitleTransformOverlay {{
        id: overlay
        objectName: "overlay"
        anchors.fill: parent
        videoRect: Qt.rect(100, 50, 600, 500)
        subtitleText: "Phu de tren video"
        livePreviewVisible: true
        sprite: ({{normal: "file:///nonexistent-fixture.png", karaoke: "",
            x: 680, y: 700, width: 300, height: 60, fontSize: 60,
            outputWidth: 1920, outputHeight: 1080, positionXPercent: 50, positionYPercent: 70}})
        fontSize: 60
        positionXPercent: 50
        positionYPercent: 70
        referenceHeightPixels: 1080
        interactive: true
        onActivated: {{
            window.activations += 1
            editing = true
        }}
        onEditingDismissed: editing = false
    }}
}}''', QUrl())
assert component.isReady(), "\\n".join(error.toString() for error in component.errors())
window = component.create()
assert window is not None, "\\n".join(error.toString() for error in component.errors())
app.processEvents()
overlay = window.findChild(QQuickItem, "overlay")
selection = overlay.findChild(QQuickItem, "subtitleTransformSelection")
live_text = overlay.findChild(QQuickItem, "subtitleTransformSprite")
assert overlay.isVisible() and selection.isVisible()
assert live_text.isVisible()
point = selection.mapToScene(QPointF(selection.width() / 2, selection.height() / 2))
QTest.mouseClick(
    window,
    Qt.LeftButton,
    Qt.NoModifier,
    QPoint(round(point.x()), round(point.y())),
)
app.processEvents()
assert window.property("activations") == 1
assert overlay.property("editing")
assert live_text.isVisible()
QTest.mouseClick(
    window,
    Qt.LeftButton,
    Qt.NoModifier,
    QPoint(120, 80),
)
app.processEvents()
assert not overlay.property("editing")
assert live_text.isVisible()
window.close()
window.deleteLater()
engine.deleteLater()
app.processEvents()
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_manual_preview_primes_the_first_video_frame_silently(self):
        preview = (QML_DIR / "ManualComparePreview.qml").read_text(encoding="utf-8")
        self.assertIn("function primeInputFrame()", preview)
        self.assertIn("function primeResultFrame()", preview)
        self.assertIn("paneVideoOutput.videoSink.videoSize.width", preview)
        self.assertIn("root.resultPriming", preview)
        self.assertIn("root.resultSourceSwitching", preview)
        self.assertIn("property bool resultPlaybackRequested", preview)
        self.assertIn("id: frameRefreshSafetyTimer", preview)
        self.assertIn("target: fullscreenOutput.videoSink", preview)
        self.assertIn("root.finishFrameRefresh(!root.fullscreenResult)", preview)
        self.assertIn("function closeFullscreen()", preview)
        self.assertNotIn("id: resultAudio", preview)
        self.assertNotIn("usesExternalAudio", preview)
        self.assertNotIn("resultAudioSource:", (QML_DIR / "ManualWorkspace.qml").read_text(encoding="utf-8"))
        self.assertIn('property url attachedInputSource: ""', preview)
        self.assertIn('property url attachedResultSource: ""', preview)
        self.assertIn("source: root.attachedInputSource", preview)
        self.assertIn("source: root.attachedResultSource", preview)
        self.assertIn("id: inputSourceSwapTimer", preview)
        self.assertIn("id: resultSourceSwapTimer", preview)
        self.assertIn('attachedResultSource = ""', preview)
        self.assertNotIn("source: root.effectiveResultSource", preview)

    def test_voice_library_uses_one_inline_preview_control_per_row(self):
        voice_picker = (QML_DIR / "VoicePicker.qml").read_text(encoding="utf-8")
        processing_form = (QML_DIR / "ProcessingSettingsForm.qml").read_text(encoding="utf-8")
        manual_inspector = (QML_DIR / "ManualStageInspector.qml").read_text(encoding="utf-8")
        manual_dialog = (QML_DIR / "ManualVoiceDialog.qml").read_text(encoding="utf-8")

        self.assertIn("StudioIconButton", voice_picker)
        self.assertIn("signal previewRequested(string voice)", voice_picker)
        self.assertIn("parent: Overlay.overlay", voice_picker)
        self.assertIn("parent.width - width - Theme.space8", voice_picker)
        self.assertIn("signal ttsVoicePreviewRequested(string value)", processing_form)
        self.assertIn("ManualVoiceDialog", manual_inspector)
        self.assertNotIn("AppController.ttsProvider =", manual_inspector)
        self.assertNotIn("AppController.ttsVoice =", manual_inspector)
        self.assertIn("previewEnabled: true", manual_dialog)
        self.assertIn("previewVoiceSample", manual_dialog)
        self.assertIn("previewSource: AppController.audioPreviewSource", manual_dialog)
        self.assertIn("previewState: AppController.audioPreviewState", manual_dialog)
        self.assertIn("configureAndRunManualVoice", manual_inspector)
        self.assertIn('"value": "all"', manual_dialog)
        self.assertIn('"value": "segment"', manual_dialog)
        self.assertIn("referenceJustAdded", manual_dialog)
        self.assertIn("root.openedVideoId", manual_dialog)
        self.assertIn('qsTr("Phát mẫu giọng")', voice_picker)
        self.assertNotIn("VoicePreviewPanel", voice_picker)

    def test_manual_export_completion_is_visible_and_loaded_on_demand(self):
        workspace = (QML_DIR / "ManualWorkspace.qml").read_text(encoding="utf-8")
        inspector = (QML_DIR / "ManualStageInspector.qml").read_text(encoding="utf-8")
        dialog = (QML_DIR / "ExportCompletedDialog.qml").read_text(encoding="utf-8")

        self.assertIn('text: qsTr("Mở video xuất")', workspace)
        self.assertIn("onClicked: AppController.openOutputFile()", workspace)
        self.assertIn("id: exportCompletedDialogLoader", workspace)
        self.assertIn("active: false", workspace[workspace.index("id: exportCompletedDialogLoader"):])
        self.assertIn("onManualExportCompleted(videoId, outputPath)", workspace)
        self.assertIn("signal exportRequested()", inspector)
        self.assertIn('root.toolId === "export" && started', inspector)
        self.assertIn('title: qsTr("Video đã xuất")', dialog)
        self.assertIn('text: qsTr("Mở video")', dialog)
        self.assertIn('text: qsTr("Mở thư mục")', dialog)
        self.assertIn("signal openVideoRequested()", dialog)

    def test_manual_workspace_flushes_drafts_before_route_teardown(self):
        workspace = (QML_DIR / "ManualWorkspace.qml").read_text(encoding="utf-8")
        inspector = (QML_DIR / "ManualStageInspector.qml").read_text(encoding="utf-8")

        destruction = workspace[workspace.index("Component.onDestruction:"):
            workspace.index("Timer {", workspace.index("Component.onDestruction:"))]
        self.assertIn("stageInspector.dismissTextEditor()", destruction)
        self.assertIn("AppController.releaseEditorPreview()", destruction)
        self.assertIn("Component.onDestruction:", inspector)
        self.assertIn("AppController.persistVideoSettingsFor(pendingSettingsVideoId)", inspector)

    def test_manual_progress_separates_queue_prepare_and_measured_work(self):
        inspector = (QML_DIR / "ManualStageInspector.qml").read_text(encoding="utf-8")
        progress = (QML_DIR / "ManualToolProgress.qml").read_text(encoding="utf-8")
        main = (QML_DIR / "Main.qml").read_text(encoding="utf-8")

        self.assertIn("ManualToolProgress {", inspector)
        self.assertIn("stepId: AppController.selectedStepId", inspector)
        self.assertIn('phase === "queued"', progress)
        self.assertIn('stepId === "waiting_for_models"', progress)
        self.assertIn('phase === "running"', progress)
        self.assertIn("visible: root.measured", progress)
        self.assertIn('qsTr("Đang chuẩn bị")', progress)
        self.assertIn('AppController.selectedStepId !== "waiting_for_models"', main)
        self.assertIn('AppController.selectedStepId !== "starting"', main)

    def test_unused_redesign_prototypes_are_removed(self):
        removed = (
            "BreadcrumbBar.qml",
            "BusyOverlay.qml",
            "CommandBar.qml",
            "CompactActionCard.qml",
            "WorkspaceActionCard.qml",
        )
        for filename in removed:
            self.assertFalse((QML_DIR / filename).exists(), filename)


    def test_resource_packages_present_real_install_units(self):
        page = (QML_DIR / "ResourcePacksPage.qml").read_text(encoding="utf-8")
        raw_row = (QML_DIR / "ResourcePackRow.qml").read_text(encoding="utf-8")
        settings = (QML_DIR / "SettingsPage.qml").read_text(encoding="utf-8")
        shell = (QML_DIR / "SettingsPageShell.qml").read_text(encoding="utf-8")

        self.assertIn("AppController.resourcePackageRows", page)
        self.assertIn("SettingsPageShell {", page)
        self.assertIn("SettingsPageShell {", settings)
        self.assertIn("Layout.preferredHeight: 64", shell)
        self.assertIn("root.horizontalInset", shell)
        self.assertIn("AppController.setHardwareTelemetryActive(visible)", page)
        self.assertIn("ResourcePackRow", page)
        self.assertNotIn("ResourceBundleRow", page)
        self.assertNotIn("installResourceBundle", page)
        self.assertIn('qsTr("Nhận dạng và dịch · CPU")', page)
        self.assertIn('qsTr("Giọng đọc OmniVoice")', page)
        self.assertIn('qsTr("Tách giọng")', page)
        self.assertIn('qsTr("Che phụ đề gốc")', page)
        self.assertIn("AppController.installResourcePacks([root.packId])", raw_row)
        self.assertIn("Layout.alignment: Qt.AlignRight | Qt.AlignVCenter", raw_row)
        self.assertNotIn("Bộ xử lý này thuộc bản cài cũ", raw_row)

    def test_dialogs_share_chrome_and_about_links_use_one_alignment(self):
        about = (QML_DIR / "AboutDialog.qml").read_text(encoding="utf-8")
        log_dialog = (QML_DIR / "ActivityLogDialog.qml").read_text(encoding="utf-8")
        subtitle_dialog = (QML_DIR / "ManualSubtitleEditorDialog.qml").read_text(encoding="utf-8")
        direct_dialogs = []
        for path in QML_DIR.glob("*.qml"):
            if re.search(r"^Dialog\s*\{", path.read_text(encoding="utf-8"), re.MULTILINE):
                direct_dialogs.append(path.name)

        self.assertEqual(sorted(direct_dialogs), ["AppDialog.qml", "FloatingToolDialog.qml"])
        self.assertEqual(about.count("AboutLinkRow {"), 3)
        self.assertIn('label: qsTr("Email")', about)
        self.assertNotIn("SettingRow {", about)
        self.assertIn("SearchField {", log_dialog)
        self.assertIn('qsTr("Tất cả mức")', log_dialog)
        self.assertIn('title: qsTr("Sửa phụ đề")', subtitle_dialog)
        self.assertNotIn("Video chỉ cập nhật sau khi lưu thay đổi", subtitle_dialog)


if __name__ == "__main__":
    unittest.main()

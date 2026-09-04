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

        progress = (QML_DIR / "AppProgressBar.qml").read_text(encoding="utf-8")
        self.assertNotIn('tone === "blue"', progress)
        self.assertNotIn('tone === "violet"', progress)

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
        self.assertEqual(inspector.count("parent: root\n        sourceComponent:"), 3)
        self.assertNotIn('text: qsTr("Chỉnh bố cục")', inspector)
        compare_preview = (QML_DIR / "ManualComparePreview.qml").read_text(encoding="utf-8")
        transform_overlay = (QML_DIR / "SubtitleTransformOverlay.qml").read_text(encoding="utf-8")
        self.assertIn("SubtitleTransformOverlay {", compare_preview)
        self.assertIn("signal layoutCommitted", transform_overlay)
        self.assertIn("signal layoutPreviewChanged", transform_overlay)
        self.assertIn('objectName: "subtitleTransformLiveText"', transform_overlay)
        self.assertIn("font.pixelSize: root.previewFontSize", transform_overlay)
        self.assertIn("property int layoutWidthPixels", transform_overlay)
        self.assertIn("property int layoutHeightPixels", transform_overlay)
        self.assertIn("root.layoutWidthPixels * root.previewScale", transform_overlay)
        self.assertIn("root.layoutHeightPixels * root.previewScale", transform_overlay)
        self.assertIn("textMeasure.implicitWidth + outlinePadding * 2", transform_overlay)
        self.assertIn("textMeasure.implicitHeight + outlinePadding * 2", transform_overlay)
        self.assertIn("rendererWidthLimit", transform_overlay)
        self.assertIn("rendererHeightLimit", transform_overlay)
        self.assertIn("wrapMode: Text.NoWrap", transform_overlay)
        self.assertIn('color: "#FFFFFFFF"', transform_overlay)
        self.assertIn('color: "#FFEF00"', transform_overlay)
        self.assertNotIn("font.bold: true", transform_overlay)
        self.assertIn("root.karaokeProgress", transform_overlay)
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
        self.assertGreaterEqual(workspace.count("root.selectedStageIndex = root.subtitleToolIndex"), 2)
        self.assertIn("subtitleInteractive: root.previewSubtitleIndex >= 0", workspace)
        self.assertIn("root.subtitleTransformActive = true", workspace)
        self.assertIn("onSubtitleActivated:", workspace)
        self.assertIn("next[index].timeline_edited = true", workspace)
        self.assertIn("next[index].fit_voice_to_timing = true", workspace)
        self.assertIn("AppController.subtitlePreviewFrame(", workspace)
        self.assertIn("AppController.adoptSubtitlePreviewLayout()", workspace)
        self.assertIn("previewMedia.subtitleRenderLayout", workspace)
        self.assertIn("subtitleAudioRefreshPending", workspace)
        activated_block = workspace[
            workspace.index("onSubtitleActivated:") : workspace.index("onSubtitleEditingDismissed:")
        ]
        self.assertNotIn("adoptSubtitlePreviewLayout", activated_block)
        self.assertIn("subtitleLivePreviewEnabled: root.subtitleVisualRefreshPending", workspace)
        self.assertIn(
            "effectiveResultSource: subtitleLivePreviewEnabled",
            compare_preview,
        )
        self.assertNotIn("cropEditEnabled:", workspace)
        self.assertIn("subtitleKaraokeProgress: root.previewSubtitleKaraokeProgress", workspace)
        self.assertIn("subtitleLayoutWidth: root.subtitleLayoutWidth", workspace)
        self.assertIn("subtitleLayoutHeight: root.subtitleLayoutHeight", workspace)
        self.assertIn("root.subtitleTransformActive = false;", workspace)
        self.assertIn("onInteractionDismissed: root.subtitleTransformActive = false", workspace)
        committed_block = workspace[
            workspace.index("onSubtitleLayoutCommitted:") : workspace.index(
                "ManualStageInspector {"
            )
        ]
        self.assertIn("root.subtitleTransformActive = false", committed_block)

        panel = (QML_DIR / "InspectorPanel.qml").read_text(encoding="utf-8")
        self.assertIn("Layout.fillHeight: true", panel)

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
live_text = overlay.findChild(QQuickItem, "subtitleTransformLiveText")
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

        self.assertIn("StudioIconButton", voice_picker)
        self.assertIn("signal previewRequested(string voice)", voice_picker)
        self.assertIn("parent: Overlay.overlay", voice_picker)
        self.assertIn("parent.width - width - Theme.space8", voice_picker)
        self.assertIn("signal ttsVoicePreviewRequested(string value)", processing_form)
        self.assertIn("previewEnabled: false", manual_inspector)
        self.assertNotIn("previewVoiceSample", manual_inspector)
        self.assertNotIn("VoicePreviewPanel", voice_picker)

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


if __name__ == "__main__":
    unittest.main()

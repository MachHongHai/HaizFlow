import os
import unittest
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem, QQuickView
from PySide6.QtTest import QTest


ROOT = Path(__file__).resolve().parents[1]
QML_DIR = ROOT / "src" / "haizflow" / "desktop" / "qml"


class QmlMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def test_menu_item_keeps_its_label_after_repeated_visibility_changes(self):
        engine = QQmlEngine()
        component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_DIR / "AppMenuItem.qml")))
        self.assertTrue(component.isReady(), "\n".join(error.toString() for error in component.errors()))
        item = component.createWithInitialProperties({"text": "Open project folder", "visible": True})
        self.assertIsNotNone(item, "\n".join(error.toString() for error in component.errors()))
        try:
            label = item.findChild(QObject, "menuItemLabel")
            self.assertIsNotNone(label)
            for collapsed in (True, False, True, False):
                item.setProperty("collapsed", collapsed)
                self.app.processEvents()
            self.assertEqual(label.property("text"), "Open project folder")
            self.assertGreater(label.property("implicitWidth"), 0)
            self.assertGreater(label.property("implicitHeight"), 0)
            item.setProperty("collapsed", True)
            self.app.processEvents()
            self.assertEqual(item.property("implicitWidth"), 0)
            self.assertEqual(item.property("implicitHeight"), 0)
        finally:
            item.deleteLater()
            engine.deleteLater()
            self.app.processEvents()

    def test_open_menu_keeps_every_visible_item_label(self):
        engine = QQmlEngine()
        component = QQmlComponent(engine)
        qml_directory = QML_DIR.as_uri()
        component.setData(
            f'''import QtQuick
import QtQuick.Controls.Basic
import "{qml_directory}"

ApplicationWindow {{
    width: 360
    height: 240
    visible: true

    Menu {{
        id: actionMenu
        objectName: "actionMenu"
        parent: Overlay.overlay
        AppMenuItem {{ objectName: "sourceAction"; text: "Open source video"; iconGlyph: "\\uE714" }}
        AppMenuItem {{ objectName: "projectAction"; text: "Open project folder"; iconGlyph: "\\uE8B7" }}
        AppMenuItem {{ objectName: "deleteAction"; text: "Delete project"; tone: "danger"; iconGlyph: "\\uE74D" }}
    }}

    Component.onCompleted: actionMenu.open()
}}'''.encode("utf-8"),
            QUrl(),
        )
        self.assertTrue(component.isReady(), "\n".join(error.toString() for error in component.errors()))
        window = component.create()
        self.assertIsNotNone(window, "\n".join(error.toString() for error in component.errors()))
        try:
            for _ in range(3):
                self.app.processEvents()
            menu = window.findChild(QObject, "actionMenu")
            self.assertTrue(menu.property("visible"))
            for action_name, expected_text in (
                ("sourceAction", "Open source video"),
                ("projectAction", "Open project folder"),
                ("deleteAction", "Delete project"),
            ):
                action = window.findChild(QObject, action_name)
                self.assertIsNotNone(action)
                label = action.findChild(QObject, "menuItemLabel")
                self.assertIsNotNone(label)
                self.assertEqual(label.property("text"), expected_text)
                self.assertGreater(label.property("width"), 0)
        finally:
            window.close()
            window.deleteLater()
            engine.deleteLater()
            self.app.processEvents()

    def test_batch_video_menu_does_not_offer_project_deletion(self):
        command_bar = (QML_DIR / "VideoCommandBar.qml").read_text(encoding="utf-8")
        project_actions = (QML_DIR / "ProjectHeaderActions.qml").read_text(encoding="utf-8")
        create_video_page = (QML_DIR / "CreateVideoPage.qml").read_text(encoding="utf-8")
        batch_page = (QML_DIR / "BatchPage.qml").read_text(encoding="utf-8")
        self.assertNotIn('text: qsTr("Xóa dự án")', command_bar)
        self.assertNotIn("isSelectedBatchVideo", command_bar)
        self.assertIn("ProjectHeaderActions {", batch_page)
        self.assertIn("onDeleteRequested: AppController.deleteCurrentBatch()", batch_page)
        self.assertIn("projectFolderText", project_actions)
        self.assertIn("showInputVideo", project_actions)
        self.assertIn("showOutputFolder", project_actions)
        self.assertIn("onInputVideoRequested: AppController.openInputFile()", create_video_page)
        self.assertIn("onOutputFolderRequested: AppController.openOutputFolder()", create_video_page)
        self.assertIn("readonly property bool editingBatchVideo", create_video_page)
        self.assertIn('deleteText: root.editingBatchVideo ? qsTr("Xóa video")', create_video_page)
        self.assertIn("AppController.deleteSelectedVideo()", create_video_page)
        self.assertIn("property string deleteText", project_actions)
        self.assertIn("Popup.CloseOnReleaseOutside", project_actions)
        self.assertIn("menuWasOpenOnPress || actionMenu.visible", project_actions)
        self.assertIn("closePolicy: Popup.CloseOnEscape | Popup.CloseOnReleaseOutside", project_actions)

    def test_navigation_settings_and_project_page_actions_stay_uncluttered(self):
        main = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
        route_host = (QML_DIR / "RouteHost.qml").read_text(encoding="utf-8")
        projects_page = (QML_DIR / "ProjectsPage.qml").read_text(encoding="utf-8")
        projects_hub = (QML_DIR / "ProjectsHubPage.qml").read_text(encoding="utf-8")
        navigation_rail = (QML_DIR / "NavigationRail.qml").read_text(encoding="utf-8")
        sidebar_button = (QML_DIR / "SidebarButton.qml").read_text(encoding="utf-8")
        about_link = (QML_DIR / "SidebarAboutLink.qml").read_text(encoding="utf-8")
        title_bar = (QML_DIR / "AppMenuBar.qml").read_text(encoding="utf-8")
        top_bar_popup = (QML_DIR / "TopBarPopupMenu.qml").read_text(encoding="utf-8")

        self.assertIn('text: qsTr("Dự án")', title_bar)
        self.assertIn('toolTipText: qsTr("Cài đặt")', title_bar)
        self.assertIn('toolTipText: qsTr("Trợ giúp")', title_bar)
        self.assertNotIn('text: I18n.t("Single projects")', title_bar)
        self.assertNotIn('text: I18n.t("Batch projects")', title_bar)
        self.assertNotIn('text: I18n.t("Download projects")', title_bar)
        self.assertIn("newDownloadProjectRequested", title_bar)
        self.assertIn("newPublishProjectRequested", title_bar)
        self.assertIn("root.toggleMenu(projectMenu, projectButton, menuWasOpenOnPress)", title_bar)
        self.assertIn("root.settingsRequested()", title_bar)
        self.assertIn("root.toggleMenu(helpMenu, helpButton, menuWasOpenOnPress)", title_bar)
        self.assertIn("parent: Overlay.overlay", title_bar)
        self.assertIn("TopBarPopupMenu {", title_bar)
        self.assertIn("border.width: 0", top_bar_popup)
        self.assertNotIn("Shortcut {", main)
        self.assertIn("NavigationRail {", main)
        self.assertNotIn("id: settingsItem", navigation_rail)
        self.assertIn('root.requestNewProject("download")', projects_hub)
        self.assertIn("GridView {", projects_hub)
        self.assertIn("AppController.deleteProjectFromBrowser(index)", projects_hub)
        self.assertIn("AppController.deleteProjectInMode(index, root.projectType)", projects_page)
        self.assertNotIn("AppController.deleteCurrentProject()", projects_page)
        self.assertIn('readonly property string routeProjects: "projects"', main)
        self.assertIn('readonly property string routeSettings: "settings"', main)
        self.assertIn('{ key: "home"', navigation_rail)
        self.assertIn('{ key: "projects"', navigation_rail)
        self.assertIn('{ key: "downloads"', navigation_rail)
        self.assertIn('{ key: "social"', navigation_rail)
        self.assertNotIn('I18n.t("Single")', navigation_rail)
        self.assertNotIn('I18n.t("Manual")', navigation_rail)
        self.assertIn("SearchField {", projects_hub)
        self.assertIn("projectModel.typeFilter", projects_hub)
        self.assertIn("projectModel.statusFilter", projects_hub)
        self.assertNotIn('iconGlyph: "\\uE713"', main)
        self.assertNotIn('Layout.preferredHeight: 1\n                color: Theme.divider\n            }\n\n            StackLayout', main)
        self.assertNotIn('color: Theme.divider\n        }\n\n        RowLayout', projects_page)
        self.assertNotIn('toolTipText: I18n.t("Refresh")', projects_page)
        self.assertNotIn("PageHeader {", projects_page)
        self.assertNotIn('I18n.t("Recent projects")', projects_page)
        self.assertIn("Layout.leftMargin: Theme.space20", projects_page)
        self.assertIn("Layout.topMargin: Theme.space20", projects_page)
        self.assertIn("Math.min(220", projects_page)
        self.assertIn('return qsTr("Tạo dự án Tự động")', projects_page)
        self.assertIn('return qsTr("Tạo dự án Hàng loạt")', projects_page)
        self.assertNotIn('I18n.t("Process one video")', projects_page)
        self.assertNotIn('I18n.t("Process videos in batch")', projects_page)
        create_page = (QML_DIR / "CreateVideoPage.qml").read_text(encoding="utf-8")
        self.assertIn("anchors.margins: Theme.space12", create_page)
        for filename in ("BatchPage.qml", "ChannelImportPage.qml"):
            page = (QML_DIR / filename).read_text(encoding="utf-8")
            self.assertIn("anchors.margins: Theme.space20", page, filename)
        downloads = (QML_DIR / "DownloadsPage.qml").read_text(encoding="utf-8")
        self.assertIn("AppTabBar {", downloads)
        self.assertIn("focusPolicy: Qt.TabFocus", sidebar_button)
        self.assertIn("focusPolicy: Qt.TabFocus", about_link)

    def test_application_menu_buttons_open_visible_overlay_popups(self):
        engine = QQmlEngine()
        component = QQmlComponent(engine)
        qml_directory = QML_DIR.as_uri()
        component.setData(
            f'''import QtQuick
import QtQuick.Controls.Basic
import "{qml_directory}"

ApplicationWindow {{
    width: 480
    height: 240
    visible: true
    AppMenuBar {{ anchors.left: parent.left; anchors.right: parent.right; height: 40 }}
}}'''.encode("utf-8"),
            QUrl(),
        )
        self.assertTrue(component.isReady(), "\n".join(error.toString() for error in component.errors()))
        window = component.create()
        self.assertIsNotNone(window, "\n".join(error.toString() for error in component.errors()))
        try:
            self.app.processEvents()
            for button_name, popup_name in (
                ("projectMenuButton", "projectMenuPopup"),
                ("helpMenuButton", "helpMenuPopup"),
            ):
                button = window.findChild(QQuickItem, button_name)
                popup = window.findChild(QObject, popup_name)
                self.assertIsNotNone(button)
                self.assertIsNotNone(popup)
                center = button.mapToScene(QPointF(button.property("width") / 2, button.property("height") / 2))
                QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(round(center.x()), round(center.y())))
                self.app.processEvents()
                self.assertTrue(popup.property("visible"), popup_name)
                self.assertAlmostEqual(
                    float(popup.property("width")),
                    min(float(popup.property("menuContentWidth")) + 8.0, 210.0),
                    delta=1.0,
                )
                self.assertGreater(popup.property("width"), 150)
                self.assertLess(popup.property("width"), 238)
                self.assertGreater(popup.property("height"), 1)
                QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(round(center.x()), round(center.y())))
                self.app.processEvents()
                self.assertFalse(popup.property("visible"), popup_name)
        finally:
            window.close()
            window.deleteLater()
            engine.deleteLater()
            self.app.processEvents()

    def test_back_navigation_uses_the_shared_application_header(self):
        main = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
        route_host = (QML_DIR / "RouteHost.qml").read_text(encoding="utf-8")
        title_bar = (QML_DIR / "AppMenuBar.qml").read_text(encoding="utf-8")
        downloads = (QML_DIR / "DownloadsPage.qml").read_text(encoding="utf-8")
        for filename in (
            "CreateVideoPage.qml",
            "BatchPage.qml",
            "DownloadsPage.qml",
            "ChannelDownloadPage.qml",
            "VideoDownloadPage.qml",
            "AudioDownloadPage.qml",
        ):
            source = (QML_DIR / filename).read_text(encoding="utf-8")
            self.assertNotIn("BackButton {", source, filename)
            self.assertNotIn("signal requestBack", source, filename)
        self.assertIn("signal backRequested", title_bar)
        self.assertIn("signal forwardRequested", title_bar)
        self.assertIn('glyph: "\\uE72B"', title_bar)
        self.assertIn('glyph: "\\uE72A"', title_bar)
        self.assertIn("onBackRequested: root.navigateBack()", main)
        self.assertIn("onForwardRequested: root.navigateForward()", main)
        self.assertNotIn("Shortcut {", main)
        self.assertIn("function navigateBack()", main)
        self.assertIn("function navigateForward()", main)
        self.assertIn("function routeIsAvailable(route)", main)
        self.assertIn("function pruneRouteHistory()", main)
        self.assertIn("function resetRouteHistory(route)", main)
        self.assertIn("function openProjectWorkspace(projectsRoute, workspaceRoute)", main)
        self.assertIn("if (!AppController.hasOpenProject)", main)
        self.assertIn('root.workspaceRequested("single-projects", "single-workspace")', route_host)
        self.assertIn('root.workspaceRequested("batch-projects", "batch-workspace")', route_host)
        self.assertIn('root.workspaceRequested("download-projects", "download-workspace")', route_host)
        self.assertIn("readonly property bool canGoBack: false", downloads)
        self.assertIn("function navigateBack()", downloads)
        self.assertIn("function navigateForward()", downloads)
        self.assertIn("RouteHost {", main)
        self.assertIn("Layout.margins: UiMetrics.pageMargin", route_host)
        self.assertNotIn("Layout.topMargin: root.width < 1400 ? 30 : 36", main)

    def test_main_uses_the_branded_window_chrome(self):
        main = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
        navigation = (QML_DIR / "NavigationRail.qml").read_text(encoding="utf-8")
        about = (QML_DIR / "AboutPage.qml").read_text(encoding="utf-8")
        title_bar = (QML_DIR / "AppMenuBar.qml").read_text(encoding="utf-8")

        self.assertIn(
            "flags: Qt.Window",
            main,
        )
        self.assertNotIn("Qt.FramelessWindowHint", main)
        self.assertNotIn("Qt.ExpandedClientAreaHint", main)
        self.assertNotIn("Qt.NoTitleBarBackgroundHint", main)
        self.assertNotIn("visibility: Window.FullScreen", main)
        self.assertNotIn("visibility: Window.Maximized", main)
        self.assertIn('title: ""', main)
        self.assertIn("AppMenuBar {", main)
        self.assertNotIn("WindowResizeBorder {", main)
        self.assertNotIn("Behavior on Layout.preferredWidth", main)
        self.assertFalse((QML_DIR / "BrandMark.qml").exists())
        self.assertNotIn("BrandMark {", navigation)
        self.assertNotIn("BrandMark {", about)
        self.assertNotIn("startSystemMove()", title_bar)
        self.assertNotIn("SafeArea.margins", title_bar)
        self.assertIn("signal settingsRequested", title_bar)
        self.assertIn("signal newSingleProjectRequested", title_bar)
        self.assertNotIn("showMinimized()", title_bar)
        self.assertNotIn("CaptionButton", title_bar)

    def test_desktop_launcher_sets_native_window_icons_and_uses_windowed_maximize(self):
        main_py = (ROOT / "src" / "haizflow" / "desktop" / "main.py").read_text(encoding="utf-8")

        self.assertIn("LoadImageW", main_py)
        self.assertIn("wm_seticon = 0x0080", main_py)
        self.assertIn("SetClassLongPtrW", main_py)
        self.assertIn("gclp_hicon = -14", main_py)
        self.assertIn("gclp_hiconsm = -34", main_py)
        self.assertIn("_set_windows_native_window_icon(window, app_icon_path)", main_py)
        self.assertIn('if sys.platform != "win32":', main_py)
        self.assertNotIn('or not getattr(sys, "frozen", False)', main_py)
        self.assertIn('app.setApplicationDisplayName("\\u200B")', main_py)
        self.assertIn("window.showMaximized()", main_py)
        self.assertNotIn("window.showFullScreen()", main_py)

    def test_dubbing_setup_exposes_independent_audio_mix_controls(self):
        setup = (QML_DIR / "DubbingSetupPanel.qml").read_text(encoding="utf-8")
        audio_dialog = (QML_DIR / "AudioMixDialog.qml").read_text(encoding="utf-8")
        create_page = (QML_DIR / "CreateVideoPage.qml").read_text(encoding="utf-8")
        self.assertIn('audioMixDialogLoader.invoke("open", [])', setup)
        self.assertIn("AppController.browseBackgroundMusic()", setup)
        self.assertIn('backgroundMusicLinkDialogLoader.invoke("open", [])', setup)
        self.assertIn("BackgroundMusicLinkDialog", setup)
        self.assertIn("AppController.originalVolume", audio_dialog)
        self.assertIn("AppController.ttsVolume", audio_dialog)
        self.assertIn("AppController.backgroundMusicVolume", audio_dialog)
        self.assertIn("AppController.previewAudioMix()", audio_dialog)
        self.assertIn("function pausePreview()", audio_dialog)
        self.assertIn("function flushVideoSettingsSave()", audio_dialog)
        self.assertIn("flushVideoSettingsSave()", audio_dialog)
        self.assertIn("root.visible && AppController.audioPreviewState === \"ready\"", audio_dialog)
        self.assertIn("readonly property bool previewPlaying", audio_dialog)
        self.assertIn('iconName: root.previewPlaying ? "pause" : "play"', audio_dialog)
        self.assertIn("!AppController.enableAudioSeparation", audio_dialog)
        self.assertIn("AppController.originalVolume / 100.0", audio_dialog)
        self.assertIn("AppController.ttsVolume / 100.0", audio_dialog)
        self.assertIn("AppController.backgroundMusicVolume / 100.0", audio_dialog)
        # The desktop workspace is fixed; only compact layouts may scroll the
        # page while the individual panels keep their own local overflow.
        self.assertIn("interactive: !root.wideLayout", create_page)
        self.assertIn("policy: root.wideLayout ? ScrollBar.AlwaysOff", create_page)
        self.assertIn("Flickable {", setup)

    def test_workspace_prioritizes_settings_and_expands_logs_on_demand(self):
        create_page = (QML_DIR / "CreateVideoPage.qml").read_text(encoding="utf-8")
        activity_feed = (QML_DIR / "ActivityFeed.qml").read_text(encoding="utf-8")
        log_dialog = (QML_DIR / "ActivityLogDialog.qml").read_text(encoding="utf-8")

        self.assertIn("Layout.preferredWidth: root.wideLayout ? 1040 : 600", create_page)
        self.assertIn("Layout.rowSpan: root.wideLayout ? 2 : 1", create_page)
        self.assertGreaterEqual(create_page.count("Layout.maximumWidth: root.wideLayout ? 320"), 2)
        self.assertIn("ActivityFeed {", create_page)
        self.assertIn("active: false", activity_feed)
        self.assertIn("ActivityLogDialog", activity_feed)
        self.assertIn('text: qsTr("Log kỹ thuật")', activity_feed)
        self.assertIn("LogViewer", log_dialog)

    def test_translation_editor_auto_saves_and_tool_windows_have_no_minimize_control(self):
        editor = (QML_DIR / "TranslationReviewDialog.qml").read_text(encoding="utf-8")
        inspector = (QML_DIR / "SubtitleEditorInspector.qml").read_text(encoding="utf-8")
        preview = (QML_DIR / "SubtitleEditorPreview.qml").read_text(encoding="utf-8")
        workspace = (QML_DIR / "SubtitleEditorWorkspace.qml").read_text(encoding="utf-8")
        timeline = (QML_DIR / "SubtitleTimeline.qml").read_text(encoding="utf-8")
        floating_tool = (QML_DIR / "FloatingToolDialog.qml").read_text(encoding="utf-8")

        self.assertIn("modal: true", editor)
        self.assertIn("function saveDraftOnClose()", editor)
        self.assertIn("function selectSegment(index)", editor)
        self.assertNotIn("Shortcut {", editor)
        self.assertIn("function undo()", editor)
        self.assertIn("function redo()", editor)
        self.assertIn("root.commitPendingText()", editor)
        self.assertIn("SubtitleEditorWorkspace {", editor)
        self.assertIn("SubtitleEditorInspector {", workspace)
        self.assertIn("editorWorkspace.commitPendingText()", editor)
        self.assertIn("Keys.priority: Keys.BeforeItem", inspector)
        self.assertIn("event.key === Qt.Key_Z || event.key === Qt.Key_Y", inspector)
        self.assertIn("openMaximized: true", editor)
        self.assertIn("SubtitleEditorPreview {", workspace)
        self.assertIn("id: editorVideoOutput", preview)
        self.assertIn("VideoOutput.PreserveAspectFit", preview)
        self.assertIn("AppController.requestEditorPreview", editor)
        self.assertIn("AppController.editorPreviewSource", editor)
        self.assertNotIn("seekPreviewRenderTimer", editor)
        self.assertIn("Seeking never invalidates the visual cache", editor)
        self.assertNotIn("videoPlayer.source = AppController.selectedInputSource;\n            resumeAfterPreview", editor)
        self.assertIn("AppController.releaseEditorPreview();", editor)
        self.assertIn("AppController.reviewPreviewMedia", editor)
        self.assertNotIn("previewMedia.subtitleStyle", editor)
        self.assertNotIn("AppController.subtitleFontSize", editor)
        self.assertNotIn("AppController.subtitlePositionXPercent", editor)
        self.assertNotIn("AppController.subtitlePositionYPercent", editor)
        self.assertNotIn("id: watermarkPreview", editor)
        self.assertIn("id: finalMixPlayer", editor)
        self.assertIn("id: backgroundPlayer", editor)
        self.assertIn("id: musicPlayer", editor)
        self.assertIn("function reloadPreviewAudio()", editor)
        self.assertIn("root.reloadPreviewAudio();", editor)
        self.assertNotIn("OCR region", editor)
        self.assertNotIn("Vùng OCR", editor)
        self.assertIn("SplitView", workspace)
        self.assertIn("property bool videoFullscreen", editor)
        self.assertIn("root.postProcessingEdit", editor)
        self.assertIn("SubtitleTimeline", workspace)
        self.assertIn("function commitSegmentTiming", editor)
        self.assertNotIn("function addSubtitleAtPlayhead", editor)
        self.assertNotIn("function mergeSelectedWithNext", editor)
        self.assertNotIn("function deleteSelected", editor)
        self.assertNotIn("function splitSelected", editor)
        self.assertNotIn("SpinBox", editor)
        self.assertIn("WheelHandler", timeline)
        self.assertIn("target: null", timeline)
        self.assertIn("interactive: !root.editingClip", timeline)
        self.assertIn("preventStealing: true", timeline)
        self.assertIn("function zoomAt", timeline)
        self.assertNotIn("function resetZoom", timeline)
        self.assertNotIn('I18n.t("Full overview")', timeline)
        self.assertNotIn('I18n.t("Selection")', timeline)
        self.assertIn("timingCommitted", timeline)
        self.assertIn("id: leftHandle", timeline)
        self.assertIn("id: rightHandle", timeline)
        self.assertIn("property real zoomFactor: 1", timeline)
        self.assertNotIn('I18n.t("Snap")', timeline)
        self.assertNotIn('I18n.t("Save draft")', editor)
        self.assertIn("function toggleMaximized()", floating_tool)
        self.assertNotIn("property bool collapsed", floating_tool)
        self.assertNotIn('I18n.t("Minimize")', floating_tool)

    def test_navigation_history_is_scoped_to_the_active_workspace(self):
        main = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
        downloads = (QML_DIR / "DownloadsPage.qml").read_text(encoding="utf-8")

        self.assertIn("readonly property bool globalNavigationBlocked", main)
        self.assertIn("if (globalNavigationBlocked)", main)
        self.assertIn("canGoBack: root.canNavigateBack", main)
        self.assertIn("canGoForward: root.canNavigateForward", main)
        self.assertIn("function resetNavigation()", downloads)
        self.assertIn("onProjectRootChanged: resetNavigation()", downloads)

    def test_editor_preview_primes_a_frame_without_a_second_paused_seek(self):
        editor = (QML_DIR / "TranslationReviewDialog.qml").read_text(encoding="utf-8")
        preview = (QML_DIR / "SubtitleEditorPreview.qml").read_text(encoding="utf-8")
        workspace = (QML_DIR / "SubtitleEditorWorkspace.qml").read_text(encoding="utf-8")

        self.assertIn("id: previewPrimeTimer", editor)
        self.assertIn("playbackRate = 0.25", editor)
        self.assertIn("videoPlayer.playbackRate = 1.0", editor)
        self.assertIn("Do not seek again after pausing", editor)
        self.assertIn("property bool previewScrubbing", editor)
        self.assertIn("id: previewScrubTimer", editor)
        self.assertIn("statusVisible: root.previewStatusVisible", editor)
        self.assertIn("previewBusy: root.previewUpdateBusy", editor)
        self.assertIn("statusVisible: root.statusVisible", workspace)
        self.assertIn("visible: root.statusVisible && root.busy", preview)
        self.assertIn("property bool previewUpdateBusy", editor)
        self.assertIn("property real previewUpdateProgress", editor)
        self.assertNotIn("previewAudioStatusVisible", editor)
        self.assertNotIn('I18n.t("Updating voice")', editor)
        self.assertNotIn("BusyIndicator {", editor)

    def test_subtitle_timeline_component_loads_with_editable_segments(self):
        engine = QQmlEngine()
        component = QQmlComponent(
            engine, QUrl.fromLocalFile(str(QML_DIR / "SubtitleTimeline.qml"))
        )
        self.assertTrue(
            component.isReady(),
            "\n".join(error.toString() for error in component.errors()),
        )
        timeline = component.createWithInitialProperties(
            {
                "width": 960.0,
                "height": 250.0,
                "duration": 18.0,
                "segments": [
                    {"start": 0.5, "end": 2.4, "text": "First subtitle"},
                    {"start": 3.0, "end": 5.2, "text": "Second subtitle"},
                ],
            }
        )
        self.assertIsNotNone(
            timeline, "\n".join(error.toString() for error in component.errors())
        )
        try:
            self.app.processEvents()
            self.assertEqual(timeline.property("zoomFactor"), 1.0)
            self.assertGreater(timeline.property("pixelsPerSecond"), 0)
        finally:
            timeline.deleteLater()
            engine.deleteLater()
            self.app.processEvents()

    def test_subtitle_timeline_wheel_zoom_keeps_clip_dragging_available(self):
        view = QQuickView()
        view.setResizeMode(QQuickView.SizeRootObjectToView)
        view.setSource(QUrl.fromLocalFile(str(QML_DIR / "SubtitleTimeline.qml")))
        self.assertEqual(view.status(), QQuickView.Ready)
        view.resize(960, 250)
        timeline = view.rootObject()
        timeline.setProperty("duration", 18.0)
        timeline.setProperty(
            "segments",
            [
                {"start": 0.5, "end": 2.4, "text": "First subtitle"},
                {"start": 3.0, "end": 5.2, "text": "Second subtitle"},
            ],
        )
        commits = []
        timeline.timingCommitted.connect(
            lambda index, start, end: commits.append((index, start, end))
        )
        try:
            view.show()
            QTest.qWaitForWindowExposed(view)
            QTest.qWait(30)

            QTest.wheelEvent(
                view,
                QPoint(180, 150),
                QPoint(0, 120),
                QPoint(),
                Qt.NoModifier,
                Qt.ScrollUpdate,
            )
            QTest.qWait(30)
            self.assertGreater(timeline.property("zoomFactor"), 1.0)

            # Drag the body of the first subtitle after zooming. A transparent
            # wheel overlay used to steal this gesture and made clips appear
            # editable only at the initial zoom level.
            QTest.mousePress(view, Qt.LeftButton, Qt.NoModifier, QPoint(145, 155))
            QTest.mouseMove(view, QPoint(205, 155), 20)
            QTest.mouseRelease(view, Qt.LeftButton, Qt.NoModifier, QPoint(205, 155))
            QTest.qWait(30)
            self.assertEqual(len(commits), 1)
            self.assertEqual(commits[0][0], 0)
            self.assertGreater(commits[0][1], 0.5)
            self.assertFalse(timeline.property("editingClip"))
        finally:
            view.close()
            view.deleteLater()
            self.app.processEvents()

    def test_batch_workspace_uses_the_fixed_warm_graphite_accent(self):
        batch_page = (QML_DIR / "BatchPage.qml").read_text(encoding="utf-8")
        theme = (QML_DIR / "Theme.qml").read_text(encoding="utf-8")

        self.assertIn("Theme.interactiveMuted", batch_page)
        self.assertIn("Theme.interactiveOutline", batch_page)
        self.assertNotIn("Theme.blueSurface", batch_page)
        self.assertNotIn("Theme.violetSurface", batch_page)
        self.assertIn('qsTr("Hàng đợi xử lý")', batch_page)
        self.assertIn('readonly property color interactive: "#C4915E"', theme)
        self.assertNotIn('readonly property color violet:', theme)
        self.assertNotIn('readonly property color blueSurface:', theme)
        self.assertIn('readonly property color warmSurface:', theme)
        self.assertNotIn("darkMode", theme)
        settings = (QML_DIR / "SettingsPage.qml").read_text(encoding="utf-8")
        self.assertNotIn('I18n.t("Theme")', settings)

    def test_background_music_link_import_stays_in_the_project_audio_flow(self):
        dialog = (QML_DIR / "BackgroundMusicLinkDialog.qml").read_text(encoding="utf-8")
        self.assertIn("AppController.importBackgroundMusicFromLink", dialog)
        self.assertIn("AppController.cancelBackgroundMusicLinkImport()", dialog)
        self.assertIn("AppController.backgroundMusicImportBusy", dialog)

    def test_audio_download_source_switch_enables_local_file_import(self):
        page = (QML_DIR / "AudioDownloadPage.qml").read_text(encoding="utf-8")
        self.assertIn('property string sourceMode: "link"', page)
        self.assertIn('currentValue: root.sourceMode', page)
        self.assertIn('root.sourceMode = value', page)
        self.assertIn('root.downloader.chooseAudioSource()', page)

    def test_download_workspace_uses_compact_tabs_without_legacy_choice_cards(self):
        page = (QML_DIR / "DownloadsPage.qml").read_text(encoding="utf-8")
        child_pages = [
            (QML_DIR / filename).read_text(encoding="utf-8")
            for filename in ("VideoDownloadPage.qml", "ChannelDownloadPage.qml", "AudioDownloadPage.qml")
        ]
        self.assertFalse((QML_DIR / "DownloadActionCard.qml").exists())
        self.assertNotIn("DownloadActionCard {", page)
        self.assertIn("AppTabBar {", page)
        self.assertIn('tabs: [qsTr("Video"), qsTr("Kênh"), qsTr("Âm thanh")]', page)
        self.assertEqual(page.count("DownloadQueueStatus {"), 1)
        for child_page in child_pages:
            self.assertNotIn("PageHeader {", child_page)
            self.assertNotIn("Panel {", child_page)
            self.assertNotIn("DownloadQueueStatus {", child_page)

    def test_downloads_are_project_backed_and_available_from_the_project_menu(self):
        main = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
        route_host = (QML_DIR / "RouteHost.qml").read_text(encoding="utf-8")
        menu = (QML_DIR / "AppMenuBar.qml").read_text(encoding="utf-8")
        setup = (QML_DIR / "ProjectSetupDialog.qml").read_text(encoding="utf-8")
        downloads = (QML_DIR / "DownloadsPage.qml").read_text(encoding="utf-8")

        self.assertIn('readonly property string routeDownloadProjects: "download-projects"', main)
        self.assertIn("AppController.downloadProjectModel", route_host)
        self.assertIn('root.newProjectRequested("download", "download-projects")', route_host)
        self.assertIn("signal newDownloadProjectRequested", menu)
        self.assertIn('text: qsTr("Dự án Tải xuống mới")', menu)
        self.assertIn('["batch", "manual", "download", "publish"].includes(type)', setup)
        self.assertIn("required property string projectName", downloads)
        self.assertIn("property int currentPage: 0", downloads)
        self.assertIn("VideoDownloadPage", downloads)
        self.assertIn("ChannelDownloadPage", downloads)
        self.assertIn("AudioDownloadPage", downloads)

    def test_download_single_batch_and_publish_workspaces_are_exposed(self):
        main = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
        route_host = (QML_DIR / "RouteHost.qml").read_text(encoding="utf-8")
        menu = (QML_DIR / "AppMenuBar.qml").read_text(encoding="utf-8")
        setup = (QML_DIR / "ProjectSetupDialog.qml").read_text(encoding="utf-8")

        self.assertIn('readonly property string routeDownloadProjects: "download-projects"', main)
        self.assertIn('readonly property string routeSingleProjects: "single-projects"', main)
        self.assertIn('readonly property string routeBatchProjects: "batch-projects"', main)
        self.assertIn('readonly property string routePublishProjects: "publish-projects"', main)
        self.assertEqual(menu.count("signal new"), 4)
        self.assertIn("signal newSingleProjectRequested", menu)
        self.assertIn("signal newBatchProjectRequested", menu)
        self.assertIn("signal newDownloadProjectRequested", menu)
        self.assertIn("signal newPublishProjectRequested", menu)
        self.assertIn('root.newProjectRequested("download", "download-projects")', route_host)
        self.assertIn('root.newProjectRequested("publish", "publish-projects")', route_host)
        self.assertIn('["batch", "manual", "download", "publish"].includes(type)', setup)
        self.assertIn('projectType === "batch"', setup)
        self.assertIn('projectType === "download"', setup)
        self.assertIn('projectType === "publish"', setup)

    def test_social_publishing_uses_zernio_without_browser_automation(self):
        main = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
        route_host = (QML_DIR / "RouteHost.qml").read_text(encoding="utf-8")
        page = (QML_DIR / "SocialPublishPage.qml").read_text(encoding="utf-8")
        controller = (ROOT / "src" / "haizflow" / "desktop" / "social_publish_controller.py").read_text(
            encoding="utf-8"
        )
        service = (ROOT / "src" / "haizflow" / "services" / "zernio.py").read_text(encoding="utf-8")
        connection_bar = (QML_DIR / "SocialConnectionBar.qml").read_text(encoding="utf-8")
        post_options = (QML_DIR / "ZernioPostOptionsDialog.qml").read_text(encoding="utf-8")
        card = (QML_DIR / "SocialPublishCard.qml").read_text(encoding="utf-8")
        guide = (QML_DIR / "ZernioGuideDialog.qml").read_text(encoding="utf-8")
        connections = (QML_DIR / "ZernioConnectionDialog.qml").read_text(encoding="utf-8")
        key_dialog = (QML_DIR / "ZernioApiKeyDialog.qml").read_text(encoding="utf-8")
        combined = "\n".join((main, page, connection_bar, guide, key_dialog, controller, service)).lower()

        self.assertIn('readonly property string routePublishProjects: "publish-projects"', main)
        self.assertIn("SocialPublishPage", route_host)
        self.assertIn("SocialConnectionBar", page)
        self.assertIn('qsTr("Kết nối đăng bài")', connection_bar)
        self.assertIn('qsTr("Tùy chọn bài đăng")', page)
        self.assertIn("zernioSetupPanel.openPostOptions()", page)
        self.assertIn("function openPostOptions()", connection_bar)
        self.assertFalse((QML_DIR / "ZernioAccessPanel.qml").exists())
        self.assertFalse((QML_DIR / "ZernioSetupPanel.qml").exists())
        self.assertIn('qsTr("Hướng dẫn")', connection_bar)
        self.assertIn('qsTr("API key")', connection_bar)
        self.assertIn("ZernioGuideDialog", page)
        self.assertIn("ZernioSetupStep", guide)
        self.assertIn("zernioConnectedAccountCount", connection_bar)
        self.assertNotIn('I18n.t("Zernio setup")', connection_bar)
        self.assertIn('qsTr("Nguồn video")', page)
        self.assertIn('qsTr("Thêm video")', page)
        self.assertIn('qsTr("Từ dự án")', page)
        self.assertIn('projectSourceDialogLoader.invoke("openForSelection", [])', page)
        self.assertIn('qsTr("Từ tệp")', page)
        self.assertIn('qsTr("Từ thư mục")', page)
        self.assertIn("browseSocialPublishVideos", page)
        self.assertIn("browseSocialPublishFolder", page)
        self.assertIn("menuWasOpenOnPress", page)
        self.assertIn('qsTr("Nội dung mặc định")', page)
        self.assertIn('qsTr("Chỉnh nội dung")', page)
        self.assertLess(page.index("SocialConnectionBar"), page.index('qsTr("Nội dung mặc định")'))
        self.assertLess(page.index('qsTr("Nội dung mặc định")'), page.index('qsTr("Hàng đợi đăng")'))
        self.assertNotIn("Layout.preferredWidth: 3", page)
        self.assertLess(page.index('qsTr("Nội dung mặc định")'), page.index('qsTr("Nguồn video")'))
        self.assertNotIn("Layout.fillHeight: true\n                Layout.preferredWidth", page)
        self.assertNotIn("Menu {", connection_bar)
        self.assertIn("apiKeyManagementRequested", connection_bar)
        self.assertIn("disconnectZernioConnection", connections)
        self.assertIn('qsTr("Ngắt kết nối")', connections)
        self.assertIn('onApiKeyManagementRequested: apiKeyDialogLoader.invoke("openForConfiguration", [])', page)
        self.assertIn("zernioConnectedAccountCount >= 2", connections)
        self.assertIn('qsTr("Quản lý kết nối")', guide)
        self.assertIn("onActiveChanged", main)
        self.assertIn("reconcileZernioConnections", main)
        connection_open = connections.split("Connections {", 1)[0]
        self.assertNotIn("refreshZernioConnections", connection_open)
        self.assertIn("reconcileZernioConnections", connection_open)
        self.assertIn("openZernioSignIn", guide)
        self.assertIn("openZernioApiKeys", key_dialog)
        self.assertIn("connectZernioPlatform", connections)
        self.assertIn("selectZernioConnection", connections)
        for platform in ("tiktok", "youtube", "facebook", "instagram"):
            self.assertIn(f'"key": "{platform}"', connections)
        for platform in ("tiktok", "facebook", "instagram"):
            self.assertIn(f'root.platform === "{platform}"', post_options)
        self.assertIn("zernioPrivacyLevels", post_options)
        self.assertIn('qsTr("Làm mới")', connections)
        self.assertNotIn('I18n.t("Sync connections")', connections)
        self.assertNotIn("consentCheck", page)
        self.assertNotIn('I18n.t("Refresh status")', page)
        self.assertIn("publishConfirmationLoader", page)
        self.assertIn("TextInput.Password", key_dialog)
        self.assertIn("clearZernioApiKey", key_dialog)
        self.assertNotIn("clearZernioApiKey", page)
        self.assertNotIn("clearZernioApiKey", connection_bar)
        self.assertIn("secure_credentials.write_secret", controller)
        self.assertNotIn('I18n.t("Open published post")', card)
        self.assertIn('collapsed: root.published || root.publishStatus === "scheduled"', card)
        self.assertIn("function resetReusableState()", card)
        self.assertIn('"/media/presign"', service)
        self.assertIn('"/posts"', service)
        self.assertNotIn("playwright", combined)
        self.assertNotIn("selenium", combined)
        self.assertNotIn("tiktok studio", combined)

    def test_platform_selector_uses_rendered_marks_and_languages_stay_textual(self):
        platform_picker = (QML_DIR / "ChannelDownloadPage.qml").read_text(encoding="utf-8")
        language_picker = (QML_DIR / "SearchableLanguageCombo.qml").read_text(encoding="utf-8")
        settings = (QML_DIR / "SettingsPage.qml").read_text(encoding="utf-8")
        self.assertIn('logoRole: "platform"', platform_picker)
        self.assertIn("logoModel: root.platformOptions", platform_picker)
        self.assertIn("PlatformLogo", (QML_DIR / "AppComboBox.qml").read_text(encoding="utf-8"))
        self.assertIn('"youtube": { "glyph": "▶"', (QML_DIR / "PlatformLogo.qml").read_text(encoding="utf-8"))
        self.assertNotIn("LanguageFlag", language_picker)
        self.assertNotIn('"flag": "vi"', settings)

    def test_app_settings_apply_automatically_without_an_apply_button(self):
        settings = (QML_DIR / "SettingsPage.qml").read_text(encoding="utf-8")

        self.assertIn("function applyDraft()", settings)
        self.assertIn("applyTimer.restart()", settings)
        self.assertIn("onVisibleChanged: {", settings)
        self.assertIn("applyDraft()", settings)
        self.assertNotIn('I18n.t("Apply settings")', settings)

    def test_language_labels_are_names_without_codes(self):
        from haizflow.desktop.presenters import language_label

        self.assertEqual(language_label("vi", "vi"), "Tiếng Việt")
        self.assertEqual(language_label("en", "en"), "English")

    def test_combo_focus_is_keyboard_only_and_language_search_is_stable(self):
        combo = (QML_DIR / "AppComboBox.qml").read_text(encoding="utf-8")
        language_picker = (QML_DIR / "SearchableLanguageCombo.qml").read_text(encoding="utf-8")
        self.assertIn("focusPolicy: Qt.TabFocus", combo)
        self.assertIn("contentItem: ColumnLayout", language_picker)
        self.assertIn("onClicked: root.openPicker(true)", language_picker)
        self.assertNotIn("property bool userEditing", language_picker)

    def test_processing_projects_can_import_from_download_projects(self):
        main = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
        source_panel = (QML_DIR / "SourceMediaPanel.qml").read_text(encoding="utf-8")
        batch_page = (QML_DIR / "BatchPage.qml").read_text(encoding="utf-8")
        dialog = (QML_DIR / "DownloadProjectSourceDialog.qml").read_text(encoding="utf-8")
        import_button = (QML_DIR / "MediaSourceImportButton.qml").read_text(encoding="utf-8")

        self.assertIn("DownloadProjectSourceDialog", main)
        self.assertIn("requestDownloadProjectImport", source_panel)
        self.assertIn("MediaSourceImportButton", source_panel)
        self.assertIn("requestDownloadProjectImport", batch_page)
        self.assertIn("MediaSourceImportButton", batch_page)
        self.assertIn('qsTr("Tệp")', import_button)
        self.assertIn('qsTr("Liên kết")', import_button)
        self.assertIn('qsTr("Tải xuống")', import_button)
        self.assertIn("AppController.downloadProjectSourceModel", dialog)
        self.assertIn("AppController.importSelectedDownloadProjectVideos", dialog)

    def test_model_setup_overlay_is_unloaded_after_setup_finishes(self):
        main = (QML_DIR / "Main.qml").read_text(encoding="utf-8")

        self.assertIn("id: modelSetupOverlayLoader", main)
        self.assertIn("active: AppController.modelSetupVisible", main)
        self.assertIn("sourceComponent: Component", main)

    def test_voice_clone_uses_an_audio_sample_and_supports_in_app_recording(self):
        dialog = (QML_DIR / "VoiceCloneDialog.qml").read_text(encoding="utf-8")
        controller = (ROOT / "src" / "haizflow" / "desktop" / "qml_controller.py").read_text(encoding="utf-8")

        self.assertIn("CaptureSession", dialog)
        self.assertIn("MediaRecorder", dialog)
        self.assertIn("prepareVoiceCloneRecording", dialog)
        self.assertIn("saveRecordedVoiceCloneReference", dialog)
        self.assertIn("voiceCloneReferenceAnalysis", dialog)
        self.assertIn("samplePlayer.position / playableDurationMs", dialog)
        self.assertIn("root.waveformPeaks[index]", dialog)
        self.assertIn("samplePlayer", dialog)
        self.assertIn('qsTr("Ghi lại")', dialog)
        self.assertNotIn("Math.sin", dialog)
        self.assertNotIn("TextArea", dialog)
        self.assertNotIn("Save voice", dialog)
        self.assertNotIn("Remove sample", dialog)
        self.assertIn("def prepareVoiceCloneRecording", controller)
        self.assertIn("def saveRecordedVoiceCloneReference", controller)

    def test_processing_settings_use_one_multiple_speaker_option_and_close_only_help(self):
        settings = (QML_DIR / "ProcessingSettingsForm.qml").read_text(encoding="utf-8")
        help_label = (QML_DIR / "SettingLabel.qml").read_text(encoding="utf-8")
        help_popover = (QML_DIR / "HelpPopover.qml").read_text(encoding="utf-8")

        self.assertIn('qsTr("Nhận diện nhiều người nói")', settings)
        self.assertIn('speakerModeEdited(checked ? "multiple" : "single")', settings)
        self.assertNotIn('qsTr("Một giọng")', settings)
        self.assertNotIn('qsTr("Nhiều người")', settings)
        self.assertIn("HelpPopover {", help_label)
        self.assertIn("Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent", help_popover)
        self.assertIn('qsTr("Đóng")', help_popover)
        self.assertNotIn("Maximize", help_label)


if __name__ == "__main__":
    unittest.main()

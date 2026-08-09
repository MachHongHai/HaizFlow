import os
import unittest
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem
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
        self.assertNotIn('text: I18n.t("Delete project")', command_bar)
        self.assertNotIn("isSelectedBatchVideo", command_bar)
        self.assertIn("ProjectHeaderActions {", batch_page)
        self.assertIn("onDeleteRequested: AppController.deleteCurrentBatch()", batch_page)
        self.assertIn("projectFolderText", project_actions)
        self.assertIn("showInputVideo", project_actions)
        self.assertIn("showOutputFolder", project_actions)
        self.assertIn("onInputVideoRequested: AppController.openInputFile()", create_video_page)
        self.assertIn("onOutputFolderRequested: AppController.openOutputFolder()", create_video_page)
        self.assertIn("readonly property bool editingBatchVideo", create_video_page)
        self.assertIn("deleteText: root.editingBatchVideo ? I18n.t(\"Remove video\")", create_video_page)
        self.assertIn("AppController.deleteSelectedVideo()", create_video_page)
        self.assertIn("property string deleteText", project_actions)
        self.assertIn("Popup.CloseOnReleaseOutside", project_actions)
        self.assertIn("menuWasOpenOnPress || actionMenu.visible", project_actions)
        self.assertIn("closePolicy: Popup.CloseOnEscape | Popup.CloseOnReleaseOutside", project_actions)

    def test_navigation_settings_and_project_page_actions_stay_uncluttered(self):
        main = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
        projects_page = (QML_DIR / "ProjectsPage.qml").read_text(encoding="utf-8")
        sidebar_button = (QML_DIR / "SidebarButton.qml").read_text(encoding="utf-8")
        about_link = (QML_DIR / "SidebarAboutLink.qml").read_text(encoding="utf-8")
        title_bar = (QML_DIR / "AppMenuBar.qml").read_text(encoding="utf-8")

        self.assertIn('text: I18n.t("Project")', title_bar)
        self.assertIn('text: I18n.t("Settings")', title_bar)
        self.assertNotIn('text: I18n.t("Single projects")', title_bar)
        self.assertNotIn('text: I18n.t("Batch projects")', title_bar)
        self.assertNotIn('text: I18n.t("Download projects")', title_bar)
        self.assertNotIn("MenuSeparator", title_bar)
        self.assertIn("root.toggleMenu(projectMenu, projectButton, menuWasOpenOnPress)", title_bar)
        self.assertIn("root.toggleMenu(settingsMenu, settingsButton, menuWasOpenOnPress)", title_bar)
        self.assertIn("parent: Overlay.overlay", title_bar)
        self.assertIn("component AppPopupMenu: Menu", title_bar)
        self.assertIn("border.width: 0", title_bar)
        self.assertIn('sequence: "Ctrl+,"', main)
        self.assertNotIn('toolTipText: "Ctrl+,"', main)
        self.assertNotIn('iconGlyph: "\\uE713"', main)
        self.assertNotIn('Layout.preferredHeight: 1\n                color: Theme.divider\n            }\n\n            StackLayout', main)
        self.assertNotIn('color: Theme.divider\n        }\n\n        RowLayout', projects_page)
        self.assertNotIn('toolTipText: I18n.t("Refresh")', projects_page)
        self.assertNotIn("PageHeader {", projects_page)
        self.assertNotIn('I18n.t("Recent projects")', projects_page)
        self.assertIn("Layout.leftMargin: Theme.space20", projects_page)
        self.assertIn("Layout.topMargin: Theme.space20", projects_page)
        self.assertIn("Math.min(220", projects_page)
        self.assertIn('I18n.t("Process one video")', projects_page)
        self.assertIn('I18n.t("Process videos in batch")', projects_page)
        for filename in ("CreateVideoPage.qml", "BatchPage.qml", "ChannelImportPage.qml"):
            page = (QML_DIR / filename).read_text(encoding="utf-8")
            self.assertIn("anchors.margins: Theme.space20", page, filename)
        downloads = (QML_DIR / "DownloadsPage.qml").read_text(encoding="utf-8")
        self.assertIn("anchors.margins: Theme.space20", downloads)
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
                ("settingsMenuButton", "settingsMenuPopup"),
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
        self.assertIn('sequence: "Alt+Left"', main)
        self.assertIn('sequence: "Alt+Right"', main)
        self.assertIn("function navigateBack()", main)
        self.assertIn("function navigateForward()", main)
        self.assertIn("function routeIsAvailable(route)", main)
        self.assertIn("function pruneRouteHistory()", main)
        self.assertIn("function resetRouteHistory(route)", main)
        self.assertIn("function openProjectWorkspace(projectsRoute, workspaceRoute)", main)
        self.assertIn("if (!AppController.hasOpenProject)", main)
        self.assertIn("root.openProjectWorkspace(root.routeSingleProjects, root.routeSingleWorkspace)", main)
        self.assertIn("root.openProjectWorkspace(root.routeBatchProjects, root.routeBatchWorkspace)", main)
        self.assertIn("root.openProjectWorkspace(root.routeDownloadProjects, root.routeDownloadWorkspace)", main)
        self.assertIn("root.openProjectWorkspace(root.routePublishProjects, root.routePublishWorkspace)", main)
        self.assertIn("function navigateTo(page)", downloads)
        self.assertIn("function navigateBack()", downloads)
        self.assertIn("function navigateForward()", downloads)
        self.assertEqual(main.count("Layout.leftMargin: root.width < 1400 ? 22 : 30"), 9)
        self.assertNotIn("Layout.topMargin: root.width < 1400 ? 30 : 36", main)

    def test_main_uses_the_branded_window_chrome(self):
        main = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
        brand_mark = (QML_DIR / "BrandMark.qml").read_text(encoding="utf-8")
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
        self.assertIn('source: "../assets/branding/haizflow-mark.png"', brand_mark)
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
        self.assertIn("audioMixDialog.open()", setup)
        self.assertIn("AppController.browseBackgroundMusic()", setup)
        self.assertIn("backgroundMusicLinkDialog.open()", setup)
        self.assertIn("BackgroundMusicLinkDialog", setup)
        self.assertIn("AppController.originalVolume", audio_dialog)
        self.assertIn("AppController.ttsVolume", audio_dialog)
        self.assertIn("AppController.backgroundMusicVolume", audio_dialog)
        self.assertIn("AppController.previewAudioMix()", audio_dialog)
        self.assertIn("function pausePreview()", audio_dialog)
        self.assertIn("onClosed: pausePreview()", audio_dialog)
        self.assertIn("root.visible && AppController.audioPreviewState === \"ready\"", audio_dialog)
        self.assertIn("readonly property bool previewPlaying", audio_dialog)
        self.assertIn('root.previewPlaying ? "\\uE769" : "\\uE768"', audio_dialog)
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
        log_panel = (QML_DIR / "ActivityLogPanel.qml").read_text(encoding="utf-8")
        log_dialog = (QML_DIR / "ActivityLogDialog.qml").read_text(encoding="utf-8")

        self.assertIn("Layout.preferredWidth: root.wideLayout ? 620 : 440", create_page)
        self.assertIn("Layout.maximumWidth: root.wideLayout ? 340", create_page)
        self.assertIn("active: false", log_panel)
        self.assertIn("ActivityLogDialog", log_panel)
        self.assertIn('I18n.t("Expand log")', log_panel)
        self.assertIn("LogViewer", log_dialog)

    def test_batch_workspace_and_theme_use_distinct_semantic_tones(self):
        batch_page = (QML_DIR / "BatchPage.qml").read_text(encoding="utf-8")
        theme = (QML_DIR / "Theme.qml").read_text(encoding="utf-8")

        self.assertIn("Theme.blueSurface", batch_page)
        self.assertIn("Theme.violetSurface", batch_page)
        self.assertIn('I18n.t("Processing queue")', batch_page)
        self.assertIn('readonly property color violet:', theme)
        self.assertIn('readonly property color blueSurface:', theme)
        self.assertIn('readonly property color warmSurface:', theme)

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

    def test_download_choice_cards_have_equal_columns_without_open_labels(self):
        card = (QML_DIR / "DownloadActionCard.qml").read_text(encoding="utf-8")
        page = (QML_DIR / "DownloadsPage.qml").read_text(encoding="utf-8")
        self.assertIn("Layout.preferredWidth: 1", card)
        self.assertIn("Layout.preferredHeight: 112", card)
        self.assertIn("maximumLineCount: 2", card)
        self.assertNotIn("property string actionText", card)
        self.assertNotIn("actionText:", page)
        self.assertIn('I18n.t("Browse public channel videos")', page)
        self.assertIn('I18n.t("Download one video from a link")', page)

    def test_downloads_are_project_backed_and_available_from_the_project_menu(self):
        main = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
        menu = (QML_DIR / "AppMenuBar.qml").read_text(encoding="utf-8")
        setup = (QML_DIR / "ProjectSetupDialog.qml").read_text(encoding="utf-8")
        downloads = (QML_DIR / "DownloadsPage.qml").read_text(encoding="utf-8")

        self.assertIn('readonly property string routeDownloadProjects: "download-projects"', main)
        self.assertIn("AppController.downloadProjectModel", main)
        self.assertIn('projectSetupDialog.openForType("download")', main)
        self.assertIn("signal newDownloadProjectRequested", menu)
        self.assertIn('I18n.t("New download project")', menu)
        self.assertIn('type === "download" ? "download"', setup)
        self.assertIn("required property string projectName", downloads)
        self.assertIn("function navigateTo(page)", downloads)

    def test_tiktok_publishing_is_a_project_backed_workspace(self):
        main = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
        menu = (QML_DIR / "AppMenuBar.qml").read_text(encoding="utf-8")
        setup = (QML_DIR / "ProjectSetupDialog.qml").read_text(encoding="utf-8")
        page = (QML_DIR / "TikTokPublishPage.qml").read_text(encoding="utf-8")
        sources = (QML_DIR / "TikTokProjectSourceDialog.qml").read_text(encoding="utf-8")

        self.assertIn('readonly property string routePublishProjects: "publish-projects"', main)
        self.assertIn("AppController.publishProjectModel", main)
        self.assertIn('projectSetupDialog.openForType("publish")', main)
        self.assertIn("signal newPublishProjectRequested", menu)
        self.assertIn('I18n.t("New TikTok publishing project")', menu)
        self.assertIn('type === "publish" ? "publish"', setup)
        self.assertIn("AppController.browseTikTokPublishVideos()", page)
        self.assertIn("AppController.browseTikTokPublishFolder()", page)
        self.assertIn("AppController.prepareNextTikTokPublishItem()", page)
        self.assertIn("AppController.saveTikTokPublishDefaults", page)
        self.assertIn("AppController.prepareTikTokLogin()", page)
        self.assertIn("AppController.clearTikTokLoginSession()", page)
        self.assertIn("projectSourceDialog.openForSelection()", page)
        self.assertIn("AppController.tiktokProjectSourceModel", sources)
        self.assertIn("AppController.addSelectedTikTokProjectVideos()", sources)
        self.assertLess(page.index('I18n.t("Sign in to TikTok")'), page.index('I18n.t("From files")'))
        self.assertLess(page.index('I18n.t("Sign in to TikTok")'), page.index('I18n.t("Clear login")'))
        self.assertLess(page.index('I18n.t("Clear login")'), page.index('I18n.t("From files")'))
        self.assertLess(page.index('I18n.t("From files")'), page.index('I18n.t("Folder")'))
        self.assertLess(page.index('I18n.t("Folder")'), page.index('I18n.t("From projects")'))
        self.assertLess(page.index('I18n.t("Prepare next")'), page.index('I18n.t("Sign in to TikTok")'))
        self.assertNotIn("Open the Chrome profile you want first", page)

    def test_platform_selector_uses_rendered_marks_and_languages_stay_textual(self):
        platform_picker = (QML_DIR / "ChannelDownloadPage.qml").read_text(encoding="utf-8")
        language_picker = (QML_DIR / "SearchableLanguageCombo.qml").read_text(encoding="utf-8")
        settings = (QML_DIR / "SettingsDialog.qml").read_text(encoding="utf-8")
        self.assertIn('logoRole: "platform"', platform_picker)
        self.assertIn("logoModel: root.platformOptions", platform_picker)
        self.assertIn("PlatformLogo", (QML_DIR / "AppComboBox.qml").read_text(encoding="utf-8"))
        self.assertIn('"youtube": { "glyph": "▶"', (QML_DIR / "PlatformLogo.qml").read_text(encoding="utf-8"))
        self.assertNotIn("LanguageFlag", language_picker)
        self.assertNotIn('"flag": "vi"', settings)

    def test_app_settings_apply_automatically_without_an_apply_button(self):
        settings = (QML_DIR / "SettingsDialog.qml").read_text(encoding="utf-8")

        self.assertIn("function scheduleApply()", settings)
        self.assertIn("autoApplyTimer.restart()", settings)
        self.assertIn("onClosed: {", settings)
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


if __name__ == "__main__":
    unittest.main()

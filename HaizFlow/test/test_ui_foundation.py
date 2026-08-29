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
            linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
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
component = QQmlComponent(engine, QUrl.fromLocalFile(r'{QML_DIR / 'UiGallery.qml'}'))
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
view.setSource(QUrl.fromLocalFile(r'{QML_DIR / 'UiGallery.qml'}'))
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
            "ManualStageInspector.qml": 5,
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

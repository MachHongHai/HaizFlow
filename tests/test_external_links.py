import ast
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QUrl

from haizflow.desktop.external_links import open_external_url
from haizflow.desktop.qml_controller import HaizFlowController


ROOT = Path(__file__).resolve().parents[1]
QML = ROOT / "src" / "haizflow" / "desktop" / "qml"


class ExternalLinkTests(unittest.TestCase):
    @patch("haizflow.desktop.external_links.QDesktopServices.openUrl", return_value=True)
    def test_web_links_are_delegated_to_qt(self, qt_open):
        links = (
            "https://github.com/MachHongHai/HaizFlow",
            "https://github.com/MachHongHai/HaizFlow/releases/latest",
            "https://github.com/MachHongHai/HaizFlow/issues/new",
            "https://github.com/MachHongHai/HaizFlow/blob/main/docs/user-guide.vi.md",
            "https://aistudio.google.com/apikey",
            "https://zernio.com/dashboard/api-keys",
            "http://example.com/guide?language=vi#install",
            "https://example.com/tài-liệu",
        )
        for link in links:
            with self.subTest(link=link):
                qt_open.reset_mock()
                self.assertTrue(open_external_url(link))
                qt_open.assert_called_once()
                url = qt_open.call_args.args[0]
                self.assertIsInstance(url, QUrl)
                self.assertEqual(url.toString(), link)

    @patch("haizflow.desktop.external_links.QDesktopServices.openUrl")
    def test_invalid_or_non_web_links_never_reach_the_handler(self, qt_open):
        for value in (
            None, 1, {}, "", "  ", "example.com", "/guide", "//example.com",
            "https://", "https:///path", "https://[bad-host", "https://host:bad",
            "https://example.com/%zz", "https://exa mple.com", "https://user:pass@example.com",
            "https://example.com/\npath", "https://example.com/\x00path",
            "file:///C:/Windows/notepad.exe", "mailto:user@example.com", "ftp://example.com",
            "javascript:alert(1)", "data:text/html,test", "ms-settings:defaultapps",
        ):
            with self.subTest(value=value):
                self.assertFalse(open_external_url(value))
        qt_open.assert_not_called()

    @patch("haizflow.desktop.external_links.QDesktopServices.openUrl", return_value=True)
    def test_surrounding_whitespace_is_trimmed(self, qt_open):
        self.assertTrue(open_external_url("  https://example.com/guide  "))
        self.assertEqual(qt_open.call_args.args[0].toString(), "https://example.com/guide")

    @patch("haizflow.desktop.external_links.QDesktopServices.openUrl", return_value=False)
    def test_system_handler_failure_is_returned(self, qt_open):
        self.assertFalse(open_external_url("https://example.com"))
        qt_open.assert_called_once()

    @patch("haizflow.desktop.external_links.QDesktopServices.openUrl", side_effect=RuntimeError("Qt unavailable"))
    def test_handler_exception_does_not_escape_into_ui(self, qt_open):
        with self.assertLogs("haizflow.desktop.external_links", level="WARNING"):
            self.assertFalse(open_external_url("https://example.com"))
        qt_open.assert_called_once()

    @patch("haizflow.desktop.qml_controller.open_external_url", return_value=False)
    def test_controller_returns_helper_status(self, helper):
        self.assertFalse(HaizFlowController.openExternalUrl(object(), "https://example.com"))
        helper.assert_called_once_with("https://example.com")

    def test_all_qml_web_links_use_shared_controller(self):
        for path in QML.glob("*.qml"):
            self.assertNotIn("Qt.openUrlExternally", path.read_text(encoding="utf-8"), str(path))
        menu = (QML / "AppMenuBar.qml").read_text(encoding="utf-8")
        for destination in (
            "https://github.com/MachHongHai/HaizFlow/blob/main/docs/user-guide.vi.md",
            "https://github.com/MachHongHai/HaizFlow/issues/new",
        ):
            self.assertIn(f'AppController.openExternalUrl("{destination}")', menu)
        self.assertIn("AppController.openExternalUrl", (QML / "ExternalTextLink.qml").read_text(encoding="utf-8"))

    def test_helper_cannot_spawn_or_inspect_browser_processes(self):
        source = (ROOT / "src/haizflow/desktop/external_links.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree) if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(node.module.split(".")[0] for node in ast.walk(tree)
                        if isinstance(node, ast.ImportFrom) and node.module)
        self.assertTrue(imported.isdisjoint({"subprocess", "ctypes", "webbrowser", "os"}))
        for forbidden in ("chrome.exe", "msedge.exe", "firefox.exe", "EnumWindows", "ShellExecute"):
            self.assertNotIn(forbidden, source)

    def test_about_email_is_displayed_as_non_clickable_text(self):
        about = (QML / "AboutDialog.qml").read_text(encoding="utf-8")
        link_row = (QML / "AboutLinkRow.qml").read_text(encoding="utf-8")
        self.assertIn('value: "machhonghaipr@gmail.com"', about)
        self.assertIn("linkEnabled: false", about)
        self.assertNotIn("mailto:", about)
        self.assertIn('copyValue: "machhonghaipr@gmail.com"', about)
        self.assertIn('destination: "https://github.com/MachHongHai/HaizFlow"', about)
        self.assertIn('destination: "https://www.linkedin.com/in/machhonghai/"', about)
        self.assertIn("AppController.copyText(root.copyValue)", link_row)

    def test_home_introduction_links_to_github_and_linkedin(self):
        creator = (QML / "HomeCreatorPanel.qml").read_text(encoding="utf-8")
        self.assertIn('destination: "https://github.com/MachHongHai/HaizFlow"', creator)
        self.assertIn('destination: "https://www.linkedin.com/in/machhonghai/"', creator)


if __name__ == "__main__":
    unittest.main()

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from haizflow.desktop.external_links import (
    ChromeLaunch,
    _active_chrome_launch,
    _launch_from_command_line,
    open_external_url,
)


ROOT = Path(__file__).resolve().parents[1]


class ExternalLinkTests(unittest.TestCase):
    def test_profile_options_are_read_from_active_chrome_command_line(self):
        launch = _launch_from_command_line(
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            'chrome.exe --user-data-dir="D:\\Chrome Profiles" --profile-directory="Profile 3"',
        )

        self.assertEqual(launch.user_data_dir, r"D:\Chrome Profiles")
        self.assertEqual(launch.profile_directory, "Profile 3")

    @patch("haizflow.desktop.external_links._chrome_process_records")
    @patch("haizflow.desktop.external_links._window_relaunch_command")
    @patch("haizflow.desktop.external_links._process_executable_path")
    @patch("haizflow.desktop.external_links._visible_chrome_windows")
    def test_active_profile_comes_from_the_top_chrome_window(
        self,
        chrome_windows,
        executable_path,
        relaunch_command,
        process_records,
    ):
        chrome_windows.return_value = [(1234, 88), (5678, 99)]
        executable_path.return_value = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        relaunch_command.return_value = 'chrome.exe --profile-directory="Profile 1"'

        launch = _active_chrome_launch()

        self.assertIsNotNone(launch)
        self.assertEqual(launch.profile_directory, "Profile 1")
        process_records.assert_not_called()

    @patch("haizflow.desktop.external_links.QDesktopServices.openUrl")
    @patch("haizflow.desktop.external_links.subprocess.Popen")
    @patch("haizflow.desktop.external_links._active_chrome_launch")
    def test_http_link_reuses_active_chrome_profile(self, active_chrome, popen, fallback):
        active_chrome.return_value = ChromeLaunch("C:\\Chrome\\chrome.exe", "D:\\Chrome Profiles", "Profile 3")

        self.assertTrue(open_external_url("https://github.com/MachHongHai"))

        popen.assert_called_once_with(
            [
                "C:\\Chrome\\chrome.exe",
                "--user-data-dir=D:\\Chrome Profiles",
                "--profile-directory=Profile 3",
                "--new-tab",
                "https://github.com/MachHongHai",
            ],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        fallback.assert_not_called()

    @patch("haizflow.desktop.external_links.QDesktopServices.openUrl", return_value=True)
    def test_non_web_link_uses_system_handler(self, fallback):
        self.assertTrue(open_external_url("mailto:machhonghaipr@gmail.com"))
        fallback.assert_called_once()

    def test_about_email_is_displayed_as_non_clickable_text(self):
        about_dialog = (ROOT / "src" / "haizflow" / "desktop" / "qml" / "AboutDialog.qml").read_text(encoding="utf-8")
        self.assertIn('text: "machhonghaipr@gmail.com"', about_dialog)
        self.assertNotIn("mail.google.com", about_dialog)
        self.assertIn('AppController.copyText("machhonghaipr@gmail.com")', about_dialog)
        self.assertIn('AppController.copyText("https://github.com/MachHongHai")', about_dialog)


if __name__ == "__main__":
    unittest.main()

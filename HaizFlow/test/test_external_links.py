import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from haizflow.desktop.external_links import (
    ChromeLaunch,
    _active_chrome_launch,
    _launch_from_command_line,
    close_managed_chrome,
    open_managed_chrome_url,
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

    def test_profile_options_support_windows_quoted_whole_arguments(self):
        launch = _launch_from_command_line(
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            'chrome.exe "--user-data-dir=D:\\HaizFlow Data\\browser-sessions\\tiktok" '
            '"--profile-directory=Default Profile"',
        )

        self.assertEqual(launch.user_data_dir, r"D:\HaizFlow Data\browser-sessions\tiktok")
        self.assertEqual(launch.profile_directory, "Default Profile")

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

    @patch("haizflow.desktop.external_links.QDesktopServices.openUrl")
    @patch("haizflow.desktop.external_links.subprocess.Popen")
    @patch("haizflow.desktop.external_links._active_chrome_launch")
    def test_saved_profile_is_preferred_over_another_active_chrome(self, active_chrome, popen, fallback):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "chrome.exe"
            executable.write_bytes(b"chrome")
            profile = {
                "executable": str(executable),
                "user_data_dir": str(Path(directory) / "User Data"),
                "profile_directory": "Profile 4",
            }

            self.assertTrue(open_external_url("https://www.tiktok.com/tiktokstudio", profile))

        active_chrome.assert_not_called()
        popen.assert_called_once_with(
            [
                str(executable),
                f"--user-data-dir={profile['user_data_dir']}",
                "--profile-directory=Profile 4",
                "--new-tab",
                "https://www.tiktok.com/tiktokstudio",
            ],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        fallback.assert_not_called()

    @patch("haizflow.desktop.external_links.subprocess.Popen")
    @patch("haizflow.desktop.external_links.find_chrome_executable")
    def test_managed_chrome_session_uses_its_own_persistent_data_directory(self, chrome, popen):
        chrome.return_value = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        with tempfile.TemporaryDirectory() as directory:
            data_directory = str(Path(directory) / "TikTok browser data")

            self.assertTrue(
                open_managed_chrome_url(
                    "https://www.tiktok.com/tiktokstudio",
                    data_directory,
                    new_window=True,
                )
            )

        popen.assert_called_once_with(
            [
                chrome.return_value,
                f"--user-data-dir={str(Path(data_directory).resolve())}",
                "--profile-directory=Default",
                "--no-first-run",
                "--no-default-browser-check",
                "--remote-debugging-address=127.0.0.1",
                "--remote-debugging-port=0",
                "--new-window",
                "https://www.tiktok.com/tiktokstudio",
            ],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    @patch("haizflow.desktop.external_links.subprocess.run")
    @patch("haizflow.desktop.external_links._chrome_process_records")
    def test_managed_chrome_close_targets_only_the_exact_data_directory(self, process_records, run):
        data_directory = r"D:\HaizFlowData\browser-sessions\tiktok"
        process_records.side_effect = [
            [
                {
                    "ProcessId": 4321,
                    "ExecutablePath": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    "CommandLine": f'chrome.exe --user-data-dir="{data_directory}" --profile-directory=Default',
                },
                {
                    "ProcessId": 9876,
                    "ExecutablePath": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    "CommandLine": r'chrome.exe --user-data-dir="C:\Users\User\Chrome"',
                },
            ],
            [],
        ]

        self.assertTrue(close_managed_chrome(data_directory))

        run.assert_called_once_with(
            ["taskkill.exe", "/PID", "4321", "/T", "/F"],
            capture_output=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=8.0,
        )

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
        self.assertIn('text: "MachHongHai/HaizFlow"', about_dialog)
        self.assertIn('destination: "https://github.com/MachHongHai/HaizFlow"', about_dialog)
        self.assertIn('AppController.copyText("https://github.com/MachHongHai/HaizFlow")', about_dialog)


if __name__ == "__main__":
    unittest.main()

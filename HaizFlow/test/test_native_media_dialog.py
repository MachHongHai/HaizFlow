import tempfile
import unittest
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from unittest import mock
from unittest.mock import patch

from haizflow.desktop import localization
from haizflow.desktop.project_import_controller import ProjectImportController


class NativeMediaDialogTests(unittest.TestCase):
    def test_native_dialog_prefers_real_downloads_over_portable_profile(self):
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "WindowsUser"
            downloads = profile / "Downloads"
            downloads.mkdir(parents=True)
            with patch.object(localization, "NATIVE_WINDOWS_USERPROFILE", str(profile)):
                self.assertEqual(localization.native_media_dialog_directory(), str(downloads.resolve()))

    def test_video_import_uses_the_native_media_location(self):
        host = type("Host", (), {"videoPath": "", "_project_directory": ""})()
        with patch(
            "haizflow.desktop.project_import_controller.native_media_dialog_directory",
            return_value="C:/Users/Example/Downloads",
        ):
            controller = ProjectImportController(host)
            self.assertEqual(controller._media_dialog_directory(), "C:/Users/Example/Downloads")

    def test_folder_import_prefers_the_modern_windows_explorer_picker(self):
        with tempfile.TemporaryDirectory() as temporary:
            selected = str(Path(temporary) / "Batch videos")
            with (
                patch.object(
                    localization, "_native_windows_folder_dialog",
                    return_value=(True, selected),
                ) as native_picker,
                patch.object(localization.QtFileDialog, "getExistingDirectory") as qt_picker,
            ):
                result = localization.QFileDialog.getExistingDirectory(
                    None, "Choose a folder of videos for batch processing", temporary,
                )

        self.assertEqual(result, selected)
        native_picker.assert_called_once_with(
            "Choose a folder of videos for batch processing", str(Path(temporary).resolve()),
        )
        qt_picker.assert_not_called()

    def test_folder_import_falls_back_to_qt_when_windows_picker_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temporary:
            fallback = str(Path(temporary) / "Fallback")
            with (
                patch.object(
                    localization, "_native_windows_folder_dialog",
                    return_value=(False, ""),
                ),
                patch.object(
                    localization.QtFileDialog, "getExistingDirectory",
                    return_value=fallback,
                ) as qt_picker,
            ):
                result = localization.QFileDialog.getExistingDirectory(
                    None, "Choose folder", temporary,
                )

        self.assertEqual(result, fallback)
        qt_picker.assert_called_once()

    def test_background_music_link_download_runs_off_the_gui_thread(self):
        signal = mock.Mock()
        host = SimpleNamespace(
            _selected_video_id="video-1",
            _background_music_import_busy=False,
            _background_music_import_status="",
            _media_import_events=Queue(),
            _processing_queue=SimpleNamespace(contains=lambda _video_id: False),
            backgroundMusicImportChanged=signal,
        )
        controller = ProjectImportController(host)
        try:
            with (
                patch("haizflow.desktop.project_import_controller.validate_video_url", return_value=("https://youtu.be/demo", "YouTube")),
                patch.object(controller, "_run_background_music_download") as run_download,
            ):
                self.assertTrue(controller.import_background_music_link("https://youtu.be/demo"))
                controller._background_music_thread.join(timeout=1)

            self.assertTrue(host._background_music_import_busy)
            self.assertEqual(host._background_music_import_status, "Downloading background music")
            run_download.assert_called_once()
            self.assertEqual(run_download.call_args.args[0]["video_id"], "video-1")
        finally:
            controller.shutdown()


if __name__ == "__main__":
    unittest.main()

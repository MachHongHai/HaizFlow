import unittest
from unittest.mock import Mock, patch

from haizflow.desktop.localization import QMessageBox, _set_ui_language, _ui_text


class UiLocalizationTests(unittest.TestCase):
    def tearDown(self):
        _set_ui_language("en")
        QMessageBox.set_alert_handler(None)

    def test_native_dialog_text_uses_vietnamese_when_selected(self):
        _set_ui_language("vi")

        self.assertEqual(_ui_text("Replace video"), "Thay video")
        self.assertEqual(
            _ui_text("Choose an MP4, MOV, or MKV video file."),
            "Hãy chọn tệp video MP4, MOV hoặc MKV.",
        )

    def test_native_dialog_text_uses_english_when_selected(self):
        _set_ui_language("en")

        self.assertEqual(_ui_text("Replace video"), "Replace video")

    def test_dynamic_native_dialog_prefix_is_localized(self):
        _set_ui_language("vi")

        self.assertEqual(
            _ui_text("Cannot save settings: permission denied"),
            "Không thể lưu cài đặt: permission denied",
        )

    def test_non_interactive_alert_uses_the_in_app_handler(self):
        handler = Mock()
        QMessageBox.set_alert_handler(handler)

        with patch("haizflow.desktop.localization.QtMessageBox.warning") as native_warning:
            result = QMessageBox.warning(None, "Settings", "Cannot save settings: denied")

        handler.assert_called_once_with("Settings", "Cannot save settings: denied", "warning")
        native_warning.assert_not_called()
        self.assertEqual(result, QMessageBox.StandardButton.Ok)


if __name__ == "__main__":
    unittest.main()

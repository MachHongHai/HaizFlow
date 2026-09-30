"""Reference selection must survive normalization, persistence and reopening."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from haizflow.desktop.presenters import voice_options_for_language
from haizflow.desktop.project_import_controller import ProjectImportController
from haizflow.desktop.qml_controller import HaizFlowController


class VoiceCloneSelectionTests(unittest.TestCase):
    def test_clone_is_supported_for_every_omnivoice_device_and_language(self):
        host = SimpleNamespace(_settings_language="vi")
        host._voice_options_for_language = lambda language, provider: voice_options_for_language(language, "vi", provider)
        for provider in ("omnivoice", "omnivoice-gpu"):
            for language in ("vi", "en", "zh"):
                with self.subTest(provider=provider, language=language):
                    self.assertEqual(HaizFlowController._normalized_voice_for_language(
                        host, language, "omnivoice:clone", provider), "omnivoice:clone")

    def test_apply_commits_clone_synchronously_for_manual_and_auto(self):
        with tempfile.TemporaryDirectory() as directory:
            sample = Path(directory) / "reference.wav"
            sample.write_bytes(b"reference")
            for project_type in ("manual", "single"):
                with self.subTest(project_type=project_type):
                    video = SimpleNamespace(video_id="v1", files={"voice_reference": str(sample)}, project_type=project_type)
                    host = SimpleNamespace(_selected_video_id="v1", _tts_provider="omnivoice-gpu", _tts_voice="omnivoice:female",
                                           _processing_queue=SimpleNamespace(contains=lambda _: False),
                                           persistVideoSettingsFor=Mock(return_value=True),
                                           ttsProviderChanged=SimpleNamespace(emit=Mock()), ttsVoiceChanged=SimpleNamespace(emit=Mock()),
                                           ttsVoiceOptionsChanged=SimpleNamespace(emit=Mock()), _audio_preview=SimpleNamespace(invalidate=Mock()))
                    with patch("haizflow.desktop.project_import_controller.video_store.get_video", return_value=video):
                        self.assertTrue(ProjectImportController(host).apply_voice_reference("v1", "omnivoice-gpu"))
                        self.assertEqual(host._tts_voice, "omnivoice:clone")
                        self.assertEqual(host._tts_provider, "omnivoice-gpu")
                        host.persistVideoSettingsFor.assert_called_once_with("v1")
                        self.assertFalse(ProjectImportController(host).apply_voice_reference("another-video", "omnivoice-gpu"))
                        host.persistVideoSettingsFor.assert_called_once_with("v1")
                        host.persistVideoSettingsFor.return_value = False
                        host._tts_voice = "omnivoice:male"
                        self.assertFalse(ProjectImportController(host).apply_voice_reference("v1", "omnivoice"))
                        self.assertEqual(host._tts_voice, "omnivoice:male")
                        self.assertEqual(host._tts_provider, "omnivoice-gpu")

    def test_recording_cannot_be_applied_to_another_project_after_navigation(self):
        host = SimpleNamespace(_selected_video_id="new-video", _voice_clone_recording_video_id="old-video",
                               cancelVoiceCloneRecording=Mock(), _voice_clone_capture=Mock())
        self.assertFalse(HaizFlowController.finishVoiceCloneRecording(host))
        host.cancelVoiceCloneRecording.assert_called_once_with()
        host._voice_clone_capture.assert_not_called()

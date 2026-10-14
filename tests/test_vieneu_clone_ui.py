from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from hflow.desktop.audio_preview_controller import AudioPreviewController
from hflow.desktop.presenters import voice_options_for_language
from hflow.desktop.project_import_controller import ProjectImportController
from hflow.desktop.qml_controller import HFlowController
from hflow.services.batch_settings import config_for


@pytest.mark.parametrize("provider", ["vieneu", "vieneu-gpu"])
@pytest.mark.parametrize("project_type", ["manual", "single"])
def test_vieneu_clone_apply_preserves_backend_and_commits_single_speaker(tmp_path, provider, project_type):
    sample = tmp_path / "reference.wav"
    sample.write_bytes(b"reference")
    video = SimpleNamespace(video_id="video", target_language="vi", project_type=project_type,
                            files={"voice_reference": str(sample)})
    host = SimpleNamespace(_selected_video_id="video", _tts_provider=provider, _tts_voice="vieneu:Hải Đăng",
        _speaker_mode="multiple", _processing_queue=SimpleNamespace(contains=lambda _: False),
        persistVideoSettingsFor=Mock(return_value=True), ttsProviderChanged=Mock(), ttsVoiceChanged=Mock(),
        ttsVoiceOptionsChanged=Mock(), speakerModeChanged=Mock(), _audio_preview=Mock())
    with patch("hflow.desktop.project_import_controller.video_store.get_video", return_value=video):
        assert ProjectImportController(host).apply_voice_reference("video", provider)
        assert host._tts_voice == "vieneu:clone" and host._tts_provider == provider
        assert host._speaker_mode == "single"
        host.persistVideoSettingsFor.assert_called_once_with("video")
        host._tts_voice, host._speaker_mode = "vieneu:Trúc Ly", "multiple"
        host.persistVideoSettingsFor.return_value = False
        assert not ProjectImportController(host).apply_voice_reference("video", provider)
        assert host._tts_voice == "vieneu:Trúc Ly" and host._speaker_mode == "multiple"


@pytest.mark.parametrize("provider", ["vieneu", "vieneu-gpu"])
def test_vieneu_clone_survives_ui_normalization_and_batch_reference_validation(provider):
    host = SimpleNamespace(_voice_options_for_language=lambda language, backend:
                           voice_options_for_language(language, "vi", backend))
    assert HFlowController._normalized_voice_for_language(host, "vi", "vieneu:clone", provider) == "vieneu:clone"
    values = {"targetLanguage": "vi", "ttsProvider": provider, "ttsVoice": "vieneu:clone"}
    with pytest.raises(ValueError, match="reference sample"):
        config_for(values)
    assert config_for({**values, "voiceReferencePath": "reference.wav"}).tts_voice == "vieneu:clone"


@pytest.mark.parametrize("provider", ["vieneu", "vieneu-gpu"])
def test_vieneu_clone_preview_uses_reference_without_synthesis(tmp_path, provider):
    sample = tmp_path / "reference.wav"
    sample.write_bytes(b"reference")
    video = SimpleNamespace(files={"voice_reference": str(sample)}, project_type="single")
    preview = AudioPreviewController(SimpleNamespace())
    with patch("hflow.desktop.audio_preview_controller.video_store.get_video", return_value=video):
        assert Path(preview.voice_sample_path(provider, "vieneu:clone", "vi", selected_video_id="video")) == sample
    assert preview.voice_sample_path(provider, "vieneu:clone", "vi") == ""


def _check_auto_clone_action_tracks_provider_and_opens_reference_setup():
    import re

    from PySide6.QtCore import QObject, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtTest import QSignalSpy

    app = QGuiApplication.instance() or QGuiApplication([])
    qml_dir = Path(__file__).resolve().parents[1] / "src/hflow/desktop/qml"
    setup = (qml_dir / "DubbingSetupPanel.qml").read_text(encoding="utf-8")
    expression = re.search(r"showCloneAction: (.*?)\s+speechRecognitionModel:", setup, re.S).group(1)
    assert 'onCloneVoiceRequested: voiceCloneDialogLoader.invoke("openForSelectedVideo", [])' in setup
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(('import QtQuick\nimport "."\nItem {\n'
        'property string provider: "vieneu-gpu"\n'
        'property var AppController: ({ttsProvider: provider})\n'
        f'ProcessingSettingsForm {{ id: form; objectName: "form"; showCloneAction: {expression}; '
        'ttsProvider: parent.provider; ttsVoiceOptions: [{voice: "vieneu:clone", available: true}] }\n'
        '}').replace('AppController', 'testController').encode(),
        QUrl.fromLocalFile(str(qml_dir / "AutoCloneRegression.qml")))
    assert component.isReady(), "\n".join(error.toString() for error in component.errors())
    root = component.create()
    assert root is not None
    try:
        form = root.findChild(QObject, "form")
        picker = next(child for child in form.findChildren(QObject) if child.metaObject().indexOfSignal("cloneRequested()") >= 0)
        spy = QSignalSpy(form.cloneVoiceRequested)
        for provider, allowed in (("vieneu-gpu", True), ("vieneu", True), ("omnivoice-gpu", True),
                                  ("omnivoice", True), ("edge", False), ("vieneu-gpu", True)):
            root.setProperty("provider", provider)
            app.processEvents()
            assert form.property("showCloneAction") == allowed
            assert picker.property("allowVoiceClone") == allowed
        picker.chooseOption({"voice": "vieneu:clone"})
        assert spy.count() == 1
    finally:
        root.deleteLater()
        app.processEvents()


def test_auto_clone_action_tracks_provider_and_opens_reference_setup():
    import subprocess
    import sys

    # A real QML singleton cannot be shared across unrelated test engines.
    # Exercise Auto's actual form in a fresh Qt process, as the app does.
    result = subprocess.run([sys.executable, str(Path(__file__).resolve())],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


if __name__ == "__main__":
    _check_auto_clone_action_tracks_provider_and_opens_reference_setup()

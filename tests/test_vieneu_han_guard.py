"""Reject unsupported target text without loading models or changing caches."""

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from haizflow.core.vieneu_voices import han_text_notice
from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.pipeline import process_video, tts, vieneu_tts
from haizflow.services.subtitle_import import voice_notice


@pytest.mark.parametrize("han", ["王", "中", "〇", "\u3400", "\uf900", "\U00020000", "\U00030000", "\U000323b0"])
def test_single_han_name_blocks_even_in_vietnamese(han):
    notice = han_text_notice([{"text": "Xin chào bạn " + han, "index": 7}])
    assert notice and f'7: “{han}”' in notice[1]
    assert "phiên âm" in notice[1] and "OmniVoice/Edge TTS" in notice[1]


@pytest.mark.parametrize("text", ["Tôi cảm ơn bạn Vương.", "Hello Adam!", "90.000 đô la", "Tốt."])
def test_supported_text_does_not_inspect_chinese_source(text):
    assert han_text_notice([{"text": text, "source_text": "你好"}]) is None


@pytest.mark.parametrize("provider", ["vieneu", "vieneu-gpu"])
def test_non_imported_captions_are_also_blocked(provider):
    video = SimpleNamespace(files={}, subtitle_language="vi")
    assert voice_notice(video, provider, [{"text": "Cảm ơn 王."}])
    assert voice_notice(video, "edge", [{"text": "Cảm ơn 王."}]) is None
    assert voice_notice(video, provider, [{"text": "Cảm ơn Vương."}]) is None


@pytest.mark.parametrize("device", ["cpu", "gpu"])
@pytest.mark.parametrize("voice", ["vieneu:Trúc Ly", "vieneu:clone"])
def test_direct_generation_blocks_before_resources_or_output(tmp_path, device, voice):
    output = tmp_path / "voice.mp3"
    with (patch.object(vieneu_tts, "verify_assets") as verify,
          patch.object(vieneu_tts, "prepare_runtime") as prepare,
          patch.object(vieneu_tts.subprocess, "Popen") as popen):
        with pytest.raises(ValueError, match="còn chữ Hán"):
            vieneu_tts.synthesize_to_mp3("Cảm ơn 王.", voice, str(output), "test", device=device)
    verify.assert_not_called()
    prepare.assert_not_called()
    popen.assert_not_called()
    assert not output.exists()


def test_worker_entry_cannot_bypass_guard():
    with patch.object(vieneu_tts, "verify_assets") as verify:
        with pytest.raises(ValueError, match="còn chữ Hán"):
            vieneu_tts._worker({"items": [{"text": "王"}]})
    verify.assert_not_called()


@pytest.mark.parametrize("provider", ["vieneu", "vieneu-gpu"])
def test_pipeline_checks_requested_cue_before_changing_files(tmp_path, provider):
    transcript = tmp_path / "segments.json"
    transcript.write_text(json.dumps([{"text": "Xin chào"}, {"text": "Cảm ơn 王."}]), encoding="utf-8")
    output = tmp_path / "parts"
    with patch.object(tts, "get_video") as get_video:
        with pytest.raises(ValueError, match='2: “王”'):
            tts.generate_voice_parts(str(transcript), str(output), "vieneu:Trúc Ly", "test",
                                     provider=provider, segment_indices=[2])
    get_video.assert_not_called()
    assert not output.exists()


def test_ui_warns_on_every_attempt_and_allows_corrected_text():
    video = SimpleNamespace(video_id="test", project_type="manual", files={})
    model = SimpleNamespace(video_id="test", segments=[{"text": "Cảm ơn 王."}])
    host = SimpleNamespace(_selected_video=lambda: video, _manual_subtitles=model,
                           _settings_language="vi", appAlertRequested=Mock())
    for provider in ("vieneu", "vieneu-gpu", "vieneu-gpu"):
        assert not HaizFlowController.validateTtsProviderForLanguage(host, "vi", provider)
    assert host.appAlertRequested.emit.call_count == 3
    assert HaizFlowController.validateTtsProviderForLanguage(host, "vi", "omnivoice-gpu")
    model.segments = [{"text": "Cảm ơn Vương."}]
    assert HaizFlowController.validateTtsProviderForLanguage(host, "vi", "vieneu-gpu")


@pytest.mark.parametrize("project_type", ["single", "batch"])
def test_cached_auto_voice_cannot_bypass_guard(tmp_path, project_type):
    transcript = tmp_path / "segments.json"
    transcript.write_text(json.dumps([{"text": "Cảm ơn 王."}]), encoding="utf-8")
    source = tmp_path / "input.mp4"
    source.write_bytes(b"existing source")
    video = SimpleNamespace(video_id="test", project_type=project_type, target_language="vi",
        tts_provider="vieneu-gpu", subtitle_style=None, files={"video_input": str(source),
        "transcript_json": str(transcript), "srt_output": str(tmp_path / "sub.srt"),
        "voice_output": str(tmp_path / "voice.wav")})
    with (patch("haizflow.services.video_export.export_destination", return_value=tmp_path / "final.mp4"),
          patch.object(process_video, "check_cancellation"),
          patch.object(process_video, "_voice_checkpoint_signature", return_value="existing"),
          patch.object(process_video, "_checkpoint_valid", return_value=True) as checkpoint,
          patch.object(process_video, "generate_voice_parts") as generate):
        with pytest.raises(ValueError, match="còn chữ Hán"):
            process_video._finish_after_translation(video, Mock(), str(tmp_path), "", stop_after="voice")
    checkpoint.assert_not_called()
    generate.assert_not_called()
    assert not (tmp_path / "temp").exists()

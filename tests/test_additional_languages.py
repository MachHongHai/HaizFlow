"""Korean/Japanese/Spanish share the same processing and caption contracts."""
from types import SimpleNamespace
from unittest.mock import Mock
import queue

import numpy as np
import pytest

from haizflow.core.edge_voices import EDGE_VOICES, edge_voice
from haizflow.core.vieneu_voices import unsupported_language_notice, unsupported_text_notice
from haizflow.desktop.catalog import TARGET_LANGUAGE_CODES
from haizflow.desktop.presenters import language_label, voice_options_for_language
from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.desktop.processing_lifecycle_controller import ProcessingLifecycleController
from haizflow.pipeline import transcribe, tts, vieneu_tts
from haizflow.services import batch_settings, subtitle_import, translation
from haizflow.services.subtitle_language import compatible_manual_voice, manual_subtitle_language


SAMPLES = {
    "ko": ("오늘은 날씨가 좋습니다.", "안녕하세요. 다음에 또 만나요!"),
    "ja": ("今日はいい天気ですね。", "こんにちは。 また会いましょう！"),
    "es": ("¿Cómo estás?", "¡Gracias, nos vemos mañana!"),
}


@pytest.mark.parametrize("code,name,label", [("ko", "Korean", "Tiếng Hàn"),
                                           ("ja", "Japanese", "Tiếng Nhật"),
                                           ("es", "Spanish", "Tiếng Tây Ban Nha")])
def test_catalog_translation_and_edge_voice_agree(code, name, label):
    assert code in TARGET_LANGUAGE_CODES
    assert language_label(code, "vi") == label and language_label(code, "en") == name
    assert translation.language_name(code) == name
    for voice, *_ in EDGE_VOICES[code]:
        assert edge_voice(voice, code) == voice
    assert voice_options_for_language(code, "vi", "edge")
    assert voice_options_for_language(code, "vi", "omnivoice-gpu")
    assert not voice_options_for_language(code, "vi", "vieneu-gpu")


@pytest.mark.parametrize("language", SAMPLES)
@pytest.mark.parametrize("provider", ["omnivoice", "omnivoice-gpu", "edge"])
def test_batch_accepts_each_supported_backend(language, provider):
    voices = voice_options_for_language(language, "vi", provider)
    config = batch_settings.config_for({"targetLanguage": language, "ttsProvider": provider,
                                       "ttsVoice": voices[0]["voice"]})
    assert config.target_language == language and config.tts_provider == provider


@pytest.mark.parametrize("language", SAMPLES)
@pytest.mark.parametrize("provider", ["vieneu", "vieneu-gpu"])
def test_vieneu_blocks_language_in_ui_batch_and_backend(language, provider):
    host = SimpleNamespace(_selected_video=lambda: None, _settings_language="vi", appAlertRequested=Mock())
    for _ in range(2):
        assert not HaizFlowController.validateTtsProviderForLanguage(host, language, provider)
    assert host.appAlertRequested.emit.call_count == 2
    with pytest.raises(ValueError, match="không hỗ trợ"):
        batch_settings.config_for({"targetLanguage": language, "ttsProvider": provider})
    with pytest.raises(ValueError, match="không hỗ trợ"):
        tts.resolve_tts_provider(provider, language)
    assert compatible_manual_voice(language, provider, "vieneu:Trúc Ly")[0] == (
        "omnivoice-gpu" if provider.endswith("-gpu") else "omnivoice")


@pytest.mark.parametrize("language", ["ko", "ja"])
@pytest.mark.parametrize("ui_language", ["vi", "en"])
def test_mixed_script_guard_reports_cue_even_when_labelled_vietnamese(language, ui_language):
    text = "Tôi cảm ơn bạn. " + SAMPLES[language][0]
    notice = unsupported_text_notice([{"text": text, "index": 7}], ui_language, imported=True)
    assert notice and "7:" in notice[1] and "SRT" in notice[1]
    assert "OmniVoice" in notice[1] and "Edge TTS" in notice[1]
    video = SimpleNamespace(files={}, subtitle_language="vi")
    assert subtitle_import.voice_notice(video, "vieneu-gpu", [{"text": text}])
    assert subtitle_import.voice_notice(video, "omnivoice-gpu", [{"text": text}]) is None


@pytest.mark.parametrize("language", SAMPLES)
def test_direct_vieneu_rejects_before_model_loading_or_cache_write(language, tmp_path, monkeypatch):
    verify = Mock(side_effect=AssertionError("Must not load unsupported TTS"))
    monkeypatch.setattr(vieneu_tts, "verify_assets", verify)
    with pytest.raises(ValueError):
        vieneu_tts.synthesize_batch_to_mp3([{"text": SAMPLES[language][0], "voice": "vieneu:Trúc Ly",
                                            "output_path": str(tmp_path / "voice.mp3")}],
                                          "new-language-test", language_id=language)
    verify.assert_not_called()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("alias", ["ko-KR", "ja_JP", "es-ES", "Spanish", "Japanese", "Korean"])
def test_vieneu_language_aliases_do_not_bypass_guard(alias):
    assert unsupported_language_notice("vieneu-gpu", alias)


@pytest.mark.parametrize("language", ["ko", "ja"])
def test_subtitle_script_detection_does_not_call_japanese_chinese(language):
    assert subtitle_import.detect_language([{"text": SAMPLES[language][0]}]) == language
    video = SimpleNamespace(files={}, target_language="zh", subtitle_language="")
    assert manual_subtitle_language(video, [{"text": SAMPLES[language][0]}]) == language


def test_a_japanese_name_does_not_relabel_a_predominantly_chinese_srt():
    assert subtitle_import.detect_language([{"text": "今天的天气非常好我们一起去公园然后回家吃饭。" * 3 + "ユキ"}]) == "zh"


@pytest.mark.parametrize("language", SAMPLES)
def test_segment_language_detection_retains_original_clock(language, monkeypatch):
    detector = Mock(return_value=(language, .99, [(language, .99)]))
    model = SimpleNamespace(model=SimpleNamespace(detect_language=detector))
    monkeypatch.setattr(transcribe, "log_to_video", Mock())
    segment = {"start": 1.25, "end": 3.75, "text": SAMPLES[language][0]}
    result = transcribe._detect_segment_languages(model, np.zeros(16000 * 5), [segment], language, "test")
    assert result[0]["language"] == language and detector.call_args.kwargs["audio"].size == 40000
    assert {key: result[0][key] for key in segment} == segment


@pytest.mark.parametrize("language", ["ko", "ja"])
def test_long_unaligned_speech_uses_real_pause_windows(language, monkeypatch):
    monkeypatch.setattr(transcribe, "log_to_video", Mock())
    monkeypatch.setattr(transcribe, "check_cancellation", Mock())
    speech = SimpleNamespace(get_timeline=lambda: [SimpleNamespace(start=1, end=3), SimpleNamespace(start=10, end=12)])
    monkeypatch.setattr("whisperx.vads.pyannote.Binarize", lambda **_: lambda _scores: speech)
    model = Mock()
    model._vad_params = {"vad_onset": .5, "vad_offset": .36}
    model.transcribe.side_effect = [{"segments": [{"text": text}]} for text in SAMPLES[language]]
    source = [{"start": 0, "end": 17, "text": " ".join(SAMPLES[language]), "language": language}]
    result = transcribe._split_long_unaligned_speech(model, np.zeros(16000 * 18), source, 4, "test", language)
    assert [(item["start"], item["end"]) for item in result] == [(1, 3), (10, 12)]
    assert [item["text"] for item in result] == list(SAMPLES[language])
    transcribe._validate_timestamp_invariants(result, 18)


def test_short_fragments_do_not_merge_across_languages_or_remove_korean_spaces():
    assert transcribe._merge_transcript_text("안녕", "고마워요") == "안녕 고마워요"
    assert transcribe._merge_transcript_text("こんにち", "は") == "こんにちは"
    source = [{"start": 0, "end": .3, "text": "はい", "language": "ja"},
              {"start": .3, "end": 1.5, "text": "Gracias", "language": "es"}]
    assert transcribe._coalesce_short_sentence_segments(source) == source


@pytest.mark.parametrize("language", SAMPLES)
def test_sentence_split_preserves_text_and_bounded_monotonic_timestamps(language):
    text = SAMPLES[language][1]
    source = {"text": text, "start": 2.25, "end": 8.75, "language": language}
    result = transcribe._split_segment_proportionally(source)
    assert "".join(item["text"] for item in result).replace(" ", "") == text.replace(" ", "")
    assert result[0]["start"] == 2.25 and result[-1]["end"] == 8.75
    transcribe._validate_timestamp_invariants(result, 9)


@pytest.mark.parametrize("language,first,second", [("ja", "こんにちは。", "またね。"),
                                                 ("ko", "안녕하세요.", "감사합니다.")])
def test_native_word_timing_keeps_real_silent_gap_and_original_text(language, first, second, monkeypatch):
    source = {"start": 1, "end": 8, "language": language, "text": first + " " + second}
    words = [SimpleNamespace(word=first, start=.2, end=1.2, probability=.98),
             SimpleNamespace(word=second, start=4.5, end=5.6, probability=.98)]
    decoder = Mock(return_value=([SimpleNamespace(words=words)], None))
    model = SimpleNamespace(model=SimpleNamespace(transcribe=decoder))
    monkeypatch.setattr(transcribe, "log_to_video", Mock())
    timed = transcribe._native_unaligned_word_timing(model, np.zeros(16000 * 9), [source], "test")
    result = transcribe._split_segment_proportionally(timed[0])
    assert [item["text"] for item in result] == [first, second]
    assert [(item["start"], item["end"]) for item in result] == [(1.2, 2.2), (5.5, 6.6)]
    assert decoder.call_args.kwargs["word_timestamps"] is True
    assert source == {"start": 1, "end": 8, "language": language, "text": first + " " + second}


@pytest.mark.parametrize("words", [
    [SimpleNamespace(word="別の言葉", start=0, end=1, probability=.99)],
    [SimpleNamespace(word="こんにちは。", start=0, end=1, probability=.05)],
    [SimpleNamespace(word="こんにちは。", start=0, end=1, probability=float("nan"))],
    [SimpleNamespace(word="こんにちは。", start=0, end=20, probability=.99)],
    [SimpleNamespace(word="こんにちは。", start=float("nan"), end=1, probability=.99)],
])
def test_native_word_timing_rejects_changed_text_low_confidence_and_bad_bounds(words, monkeypatch):
    source = {"start": 1, "end": 4, "language": "ja", "text": "こんにちは。"}
    model = SimpleNamespace(model=SimpleNamespace(transcribe=lambda *_args, **_kwargs: ([SimpleNamespace(words=words)], None)))
    monkeypatch.setattr(transcribe, "log_to_video", Mock())
    assert transcribe._native_unaligned_word_timing(model, np.zeros(16000 * 5), [source], "test") == [source]


@pytest.mark.parametrize("language", SAMPLES)
@pytest.mark.parametrize("ui", ["vi", "en"])
def test_translation_completion_syncs_vieneu_fallback_to_ui(language, ui, monkeypatch, tmp_path):
    video = SimpleNamespace(video_id="new-language", project_type="manual", subtitle_language=language,
                            tts_provider="omnivoice-gpu", tts_voice="omnivoice:female_gentle")
    host = SimpleNamespace(_log_queue=queue.Queue(), _selected_video_id=video.video_id,
        _tts_provider="vieneu-gpu", _tts_voice="vieneu:Trúc Ly", _settings_language=ui,
        refreshVideos=Mock(), selectedVideoChanged=Mock(), _refresh_batch_model=Mock(), batchChanged=Mock(),
        ttsProviderChanged=Mock(), ttsVoiceChanged=Mock(), ttsProviderOptionsChanged=Mock(),
        ttsVoiceOptionsChanged=Mock(), appAlertRequested=Mock())
    host._log_queue.put("__QUEUE_FINISHED__:" + video.video_id)
    monkeypatch.setattr("haizflow.desktop.processing_lifecycle_controller.video_store.get_video", lambda _: video)
    monkeypatch.setattr("haizflow.desktop.processing_lifecycle_controller.video_store.get_video_logs_path", lambda _: str(tmp_path / "missing.log"))
    ProcessingLifecycleController(host).drain_log_queue()
    assert host._tts_provider == "omnivoice-gpu" and host._tts_voice == video.tts_voice
    host.appAlertRequested.emit.assert_called_once()
    assert language_label(language, ui).lower() in host.appAlertRequested.emit.call_args.args[1].lower()

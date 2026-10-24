"""Offline request/persistence contracts, not a model-quality benchmark."""

import io
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from haizflow.pipeline import manual_tools, process_video
from haizflow.schemas.video import VideoConfig, VideoInfo
from haizflow.services import batch_settings, gemini_context, gemini_translation, translation, video_export
from haizflow.services.processing_resume import configuration_snapshot


@pytest.mark.parametrize("model", list(gemini_translation.MODELS))
@pytest.mark.parametrize("style", list(gemini_context.STYLE_PROMPTS))
def test_styles_control_language_instructions_not_sampling(model, style, monkeypatch):
    requests = []
    source = [(0, "My wife was the only family I had left, but she left me too."),
              (1, "First, you need to clean yourself up.")]
    expected = ["Vợ tôi là người thân duy nhất còn lại, nhưng cô ấy cũng bỏ tôi rồi.",
                "Trước tiên, anh cần tắm rửa sạch sẽ đã."]

    def send(outgoing, **_kwargs):
        requests.append(json.loads(outgoing.data))
        return io.BytesIO(json.dumps({"candidates": [{"finishReason": "STOP", "content": {"parts": [
            {"text": json.dumps({"translations": [{"id": i, "text": text} for i, text in enumerate(expected)]},
                                ensure_ascii=False)}]}}]}, ensure_ascii=False).encode("utf-8"))

    monkeypatch.setattr(gemini_translation.request, "urlopen", send)
    monkeypatch.setattr(gemini_translation, "check_cancellation", lambda _: None)
    result = gemini_translation._request_chunk(source, key="offline-key", model=model,
        source_language="English", target_language="Vietnamese", translation_style=style,
        translation_instructions="Người vợ bỏ chồng; người chồng được một cô gái giúp đỡ.",
        translation_glossary="Chồng nói với vợ: anh – em; vợ nói với chồng: em – anh.",
        speech_durations=[2.64, 1.56], translation_context={"accepted_examples": []})
    assert result == expected and len(requests) == 1
    payload = requests[0]
    config = payload["generationConfig"]
    assert not {"temperature", "topP", "topK"} & set(config)
    assert config["thinkingConfig"] == {"thinkingLevel": "low", "includeThoughts": False}
    system = payload["systemInstruction"]["parts"][0]["text"]
    assert gemini_context.STYLE_PROMPTS[style] in system
    assert "spelling and diacritics" in system and "correct speaker-to-addressee direction" in system
    assert "fallible references" in system
    assert "Người vợ bỏ chồng" not in system
    parts = payload["contents"][0]["parts"]
    task, guidance, context = [json.loads(part["text"]) for part in parts]
    assert [(entry["id"], entry["text"]) for entry in task] == source
    assert guidance["translation_guidance"]["style"] == style
    assert guidance["translation_guidance"]["names_and_address"].endswith("em – anh.")
    assert "translation_context_only" in context


@pytest.mark.parametrize("model", list(gemini_translation.MODELS))
def test_default_lite_requests_remain_fast_and_use_default_sampling(model, monkeypatch):
    send = Mock(side_effect=RuntimeError("Captured without network"))
    monkeypatch.setattr(gemini_translation.request, "urlopen", send)
    with pytest.raises(RuntimeError, match="Captured"):
        gemini_translation._request_chunk([(0, "Hello")], key="offline", model=model,
            source_language="English", target_language="Vietnamese")
    payload = json.loads(send.call_args.args[0].data)
    config = payload["generationConfig"]
    assert "temperature" not in config
    assert config["thinkingConfig"]["thinkingLevel"] == ("minimal" if "lite" in model else "low")
    assert len(payload["contents"][0]["parts"]) == 1


@pytest.mark.parametrize("model", ["q4", "gemini-3.5-flash-lite"])
def test_style_changes_only_gemini_translation_cache_and_resume(tmp_path, model, monkeypatch):
    config = VideoConfig(project_type="manual", translation_model=model)
    video = VideoInfo(**config.model_dump(), video_id="style", original_filename="a.mp4", status="manual_ready",
        created_at="2026-10-24T00:00:00Z", updated_at="2026-10-24T00:00:00Z", manual_target_tool="translation")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    monkeypatch.setattr(manual_tools, "recognition_signature", lambda _: "same-asr")
    def identities():
        return (manual_tools.translation_signature(video), process_video._translation_signature(video, str(source)),
                configuration_snapshot(video, "cpu"))
    before = identities()
    video.gemini_translation_style = "adaptive"
    assert all((old != new) == model.startswith("gemini-") for old, new in zip(before, identities()))
    assert batch_settings.config_for(batch_settings.values_for(video)).gemini_translation_style == "adaptive"


def test_policy_or_style_changes_discard_old_partial_translation(tmp_path, monkeypatch):
    source, output = tmp_path / "source.json", tmp_path / "out.json"
    source.write_text('[{"start":0,"end":2,"text":"Hello"}]', encoding="utf-8")
    generate = Mock(return_value=["Xin chào"])
    monkeypatch.setattr(gemini_translation, "translate_texts", generate)
    monkeypatch.setattr(translation, "shutdown_hymt2_worker", lambda: None)
    monkeypatch.setattr(translation, "log_to_video", Mock())
    monkeypatch.setattr(gemini_context, "VERSION", "old-policy")
    kwargs = dict(provider="gemini", translation_model="gemini-3.5-flash-lite", retain_checkpoint=True)
    translation.translate_segments(str(source), str(output), "style", **kwargs)
    translation.translate_segments(str(source), str(output), "style", **kwargs)
    assert generate.call_count == 1
    monkeypatch.setattr(gemini_context, "VERSION", "new-policy")
    translation.translate_segments(str(source), str(output), "style", **kwargs)
    assert generate.call_count == 2
    translation.translate_segments(str(source), str(output), "style", translation_style="natural", **kwargs)
    assert generate.call_count == 3 and generate.call_args.kwargs["translation_style"] == "natural"


def test_auto_render_only_tracks_nondefault_style_for_gemini(monkeypatch):
    capture = Mock(return_value="render")
    monkeypatch.setattr(video_export.manual_artifacts, "signature", capture)
    monkeypatch.setattr(video_export.manual_artifacts, "file_state", lambda _: None)
    video = SimpleNamespace(**VideoConfig().model_dump(), files={}, checkpoints={})
    video_export.render_revision(video)
    baseline = capture.call_args.args[1]
    video.gemini_translation_style = "literal"
    video_export.render_revision(video)
    assert capture.call_args.args[1] == baseline
    video.translation_model = "gemini-3.5-flash-lite"
    video_export.render_revision(video)
    assert capture.call_args.args[1]["gemini_translation_style"] == "literal"


def test_invalid_style_is_rejected_before_any_request(monkeypatch):
    send = Mock()
    monkeypatch.setattr(gemini_translation.request, "urlopen", send)
    with pytest.raises(ValueError, match="style"):
        gemini_translation._request_chunk([(0, "Hello")], key="offline", model="gemini-3.5-flash-lite",
            source_language="English", target_language="Vietnamese", translation_style="unknown")
    send.assert_not_called()

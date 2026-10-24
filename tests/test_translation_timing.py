import io
import json
import queue
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from haizflow.services import gemini_translation, hymt2_worker, translation
from haizflow.services.translation_timing import (
    POLICY_VERSION, speech_duration, timing_budget, timing_instruction,
)


def test_speech_duration_uses_complete_alignment_without_mutating_timeline():
    segment = {"start": 0, "end": 8, "text": "Go now!", "words": [
        {"word": "Go", "start": 2, "end": 2.2}, {"word": "now!", "start": 2.3, "end": 2.8},
    ]}
    assert speech_duration(segment) == pytest.approx(.8)
    assert (segment["start"], segment["end"]) == (0, 8)
    segment["words"].pop()
    assert speech_duration(segment) == 8
    segment["words"] = [{"word": "Go now!", "start": None, "end": 2}]
    assert speech_duration(segment) == 8


@pytest.mark.parametrize("start,end", [(0, float("nan")), (float("nan"), 1), (0, float("inf")), (-1, 2), (2, 1)])
def test_nonfinite_or_invalid_timing_cannot_create_a_budget(start, end):
    with pytest.raises(ValueError):
        speech_duration({"start": start, "end": end, "text": "Hello"})


def test_budgets_use_target_speech_units_not_source_character_count():
    assert timing_budget(2, "Vietnamese")["target_spoken_units"] == 9
    assert timing_budget(2, "English")["target_spoken_units"] == 6
    assert timing_budget(2, "Chinese")["target_spoken_units"] == 9
    assert timing_budget(2, "Thai") == {"speech_seconds": 2.0}
    assert timing_budget(.0001, "Vietnamese")["speech_seconds"] > 0
    assert timing_instruction(None, "Vietnamese") == ""
    assert "accuracy takes priority" in timing_instruction(1, "Vietnamese").lower()
    assert "never pad" in timing_instruction(1, "Vietnamese")


@pytest.mark.parametrize("source", ["Hello", "Do not give him 3 apples."])
def test_hymt2_prompts_receive_duration_even_for_short_labels_and_recovery(source):
    prompt = hymt2_worker._build_prompt(
        [source], ["English"], 0, "Vietnamese", duration_seconds=1.2,
        strict_source_only=True,
    )
    assert "1.200 seconds" in prompt
    assert "concise, natural spoken phrasing" in prompt
    assert "negation, names, numbers" in prompt
    assert "do not paraphrase" not in prompt
    assert prompt.endswith("[Source Text]\n" + source)


@pytest.mark.parametrize("device", ["cpu-gguf", "cuda"])
def test_worker_passes_per_sentence_timing_to_both_model_paths(device):
    with (
        patch.object(hymt2_worker, "_model_runtime", return_value=(None, None, None, device)),
        patch.object(hymt2_worker, "_translate_prompt_batch", return_value=["Đi thôi."]) as generate,
        patch.object(hymt2_worker, "_emit_event"),
    ):
        result = hymt2_worker.translate({
            "texts": ["Go now."], "source_languages": ["English"], "target_language_name": "Vietnamese",
            "speech_durations": [1.25],
        })
    assert result == ["Đi thôi."]
    assert "1.250 seconds" in generate.call_args.args[4][0]


def test_native_rpc_carries_duration_with_original_indices():
    process = Mock()
    process.stdin = io.StringIO()
    process.poll.return_value = None
    output = queue.Queue()
    output.put(json.dumps({"event": "response", "request_id": "fixture", "translations": ["Đi thôi."]}))
    with (
        patch.object(translation, "_ensure_hymt2_worker", return_value=(process, output)),
        patch.object(translation, "_WORKER_PROCESS", process),
        patch.object(translation.uuid, "uuid4", return_value=SimpleNamespace(hex="fixture")),
        patch.object(translation, "register_process"), patch.object(translation, "unregister_process"),
        patch.object(translation, "_schedule_worker_idle_shutdown"), patch.object(translation, "log_to_video"),
    ):
        translation._translate_with_hymt2_worker(
            ["Go now."], video_id="fixture", source_languages=["English"], target_language_name="Vietnamese",
            speech_durations=[1.5], translate_indices=[0],
        )
    payload = json.loads(process.stdin.getvalue())["payload"]
    assert payload["speech_durations"] == [1.5]
    assert "previous_translations" not in payload
    assert payload["translate_indices"] == [0]


def test_gemini_resume_preserves_timing_indices_in_requests():
    sent = []

    def request_chunk(chunk, **kwargs):
        sent.append((chunk, kwargs))
        return ["Đi thôi."]

    with (
        patch.object(gemini_translation, "active_key", return_value="fixture"),
        patch.object(gemini_translation, "check_cancellation"), patch.object(gemini_translation, "log_to_video"),
        patch.object(gemini_translation, "_request_chunk", side_effect=request_chunk),
    ):
        result = gemini_translation.translate_texts(
            ["Hello", "Go now"], model=next(iter(gemini_translation.MODELS)),
            source_language="English", target_language="Vietnamese", video_id="fixture",
            initial_translations=["Xin chào", None], speech_durations=[3, 1],
        )
    assert result == ["Xin chào", "Đi thôi."]
    assert sent[0][0] == [(1, "Go now")]
    assert sent[0][1]["speech_durations"] == [3, 1]


def test_gemini_json_contains_soft_budget_but_does_not_reduce_generation_token_cap():
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self, *_args):
            return json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps({
                "translations": [{"id": 1, "text": "Đi thôi."}],
            })}]}}]}).encode()

    def send(request, **kwargs):
        payload = json.loads(request.data)
        entry = json.loads(payload["contents"][0]["parts"][0]["text"])[0]
        assert entry == {"id": 1, "text": "Go now", "speech_seconds": 1.0,
                         "target_spoken_units": 5, "spoken_unit": "space-separated spoken syllables"}
        assert payload["generationConfig"]["maxOutputTokens"] >= 1024
        assert "meaning, grammar and spelling take priority" in payload["systemInstruction"]["parts"][0]["text"]
        return Response()

    with patch.object(gemini_translation.request, "urlopen", side_effect=send):
        assert gemini_translation._request_chunk(
            [(1, "Go now")], key="fixture", model=next(iter(gemini_translation.MODELS)),
            source_language="English", target_language="Vietnamese", speech_durations=[2, 1],
        ) == ["Đi thôi."]


@pytest.mark.parametrize("provider,model", [("hymt2", "q4"), ("hymt2", "full"), ("gemini", "gemini-3.5-flash-lite")])
@pytest.mark.parametrize("original", [
    "Đừng đưa anh ấy 3 quả táo.",
    "Bạn tuyệt đối đừng bao giờ đưa cho anh ấy cả 3 quả táo nhé.",
])
def test_first_pass_only_even_when_translation_exceeds_soft_length_budget(tmp_path, provider, model, original):
    source, output = tmp_path / "source.json", tmp_path / "translated.json"
    segments = [
        {"start": 0, "end": 1, "text": "Do not give him 3 apples.", "language": "en"},
        {"start": 1, "end": 3, "text": "Go now.", "language": "en"},
    ]
    source.write_text(json.dumps(segments), encoding="utf-8")
    calls = []

    def generate(texts, **kwargs):
        calls.append(kwargs)
        assert kwargs["speech_durations"] == [1, 2]
        assert "previous_translations" not in kwargs
        return [original, "Đi thôi."]

    target = "_translate_with_hymt2_worker" if provider == "hymt2" else "translate_texts"
    module = translation if provider == "hymt2" else gemini_translation
    with patch.object(module, target, side_effect=generate), patch.object(translation, "log_to_video"):
        result = translation.translate_segments(str(source), str(output), "fixture", provider=provider, translation_model=model)
    assert len(calls) == 1
    assert result[0]["text"] == original
    assert result[1]["text"] == "Đi thôi."
    assert [(row["start"], row["end"]) for row in result] == [(0, 1), (1, 3)]
    assert result[0]["source_text"] == segments[0]["text"]


def test_first_pass_pause_keeps_checkpoint_and_previous_published_result(tmp_path):
    source, output = tmp_path / "source.json", tmp_path / "translated.json"
    source.write_text(json.dumps([{"start": 0, "end": 1, "text": "Go now.", "language": "en"}]), encoding="utf-8")
    output.write_text("old published result", encoding="utf-8")
    original = "Bây giờ bạn hãy nhanh chóng bắt đầu rời khỏi nơi này ngay đi nhé."

    def generate(texts, **kwargs):
        assert kwargs["speech_durations"] == [1]
        kwargs["result_callback"]([0], [original])
        raise RuntimeError("Video cancelled by user.")

    with patch.object(translation, "_translate_with_hymt2_worker", side_effect=generate), patch.object(translation, "log_to_video"):
        with pytest.raises(RuntimeError, match="cancelled"):
            translation.translate_segments(str(source), str(output), "fixture")
    assert output.read_text(encoding="utf-8") == "old published result"
    checkpoint = json.loads((tmp_path / "translated.json.progress.json").read_text(encoding="utf-8"))
    assert checkpoint["translations"] == [original]
    assert POLICY_VERSION == "speech-length-v1"

    with patch.object(translation, "_translate_with_hymt2_worker") as worker, patch.object(translation, "log_to_video"):
        result = translation.translate_segments(str(source), str(output), "fixture")
    worker.assert_not_called()
    assert result[0]["text"] == original


@pytest.mark.parametrize("durations", [[], [0], [-1], [float("nan")], [float("inf")]])
def test_invalid_durations_rejected_before_loading_model_or_calling_api(durations):
    with patch.object(hymt2_worker, "_model_runtime") as load:
        with pytest.raises(ValueError):
            hymt2_worker.translate({
                "texts": ["Go now"], "source_languages": ["English"],
                "target_language_name": "Vietnamese", "speech_durations": durations,
            })
    load.assert_not_called()
    with patch.object(gemini_translation, "active_key") as key:
        with pytest.raises(ValueError):
            gemini_translation.translate_texts(
                ["Go now"], model=next(iter(gemini_translation.MODELS)), video_id="fixture",
                source_language="English", target_language="Vietnamese", speech_durations=durations,
            )
    key.assert_not_called()
    with patch.object(translation, "_ensure_hymt2_worker") as worker:
        with pytest.raises(ValueError):
            translation._translate_with_hymt2_worker(
                ["Go now"], video_id="fixture", source_languages=["English"],
                target_language_name="Vietnamese", speech_durations=durations,
            )
    worker.assert_not_called()


@pytest.mark.parametrize("provider,model", [("hymt2", "q4"), ("hymt2", "full"), ("gemini", "gemini-3.5-flash-lite")])
def test_existing_invalid_text_recovery_keeps_correct_duration_mapping(tmp_path, provider, model):
    source, output = tmp_path / "source.json", tmp_path / "translated.json"
    source.write_text(json.dumps([
        {"start": 0, "end": 3, "text": "Hello friend", "language": "en"},
        {"start": 4, "end": 5, "text": "Go now", "language": "en"},
    ]), encoding="utf-8")
    calls = []

    def generate(texts, **kwargs):
        calls.append((texts, kwargs))
        if len(calls) == 1:
            assert kwargs["speech_durations"] == [3, 1]
            return ["Chào bạn", "\ufffd"]
        if provider == "gemini":
            assert texts == ["Go now"]
            assert kwargs["speech_durations"] == [1]
            return ["Đi thôi"]
        assert kwargs["translate_indices"] == [1]
        assert kwargs["speech_durations"] == [3, 1]
        return ["Unrelated result must not overwrite", "Đi thôi"]

    module = translation if provider == "hymt2" else gemini_translation
    target = "_translate_with_hymt2_worker" if provider == "hymt2" else "translate_texts"
    with patch.object(module, target, side_effect=generate), patch.object(translation, "log_to_video"):
        result = translation.translate_segments(str(source), str(output), "fixture", provider=provider, translation_model=model)
    assert len(calls) == 2
    assert [row["text"] for row in result] == ["Chào bạn", "Đi thôi"]


def test_pipeline_sends_spoken_span_but_preserves_caption_time_range(tmp_path):
    source, output = tmp_path / "source.json", tmp_path / "translated.json"
    source.write_text(json.dumps([{
        "start": 0, "end": 8, "text": "Go now!", "language": "en", "words": [
            {"word": "Go", "start": 2, "end": 2.2}, {"word": "now!", "start": 2.3, "end": 2.8},
        ],
    }]), encoding="utf-8")
    with patch.object(translation, "_translate_with_hymt2_worker", return_value=["Đi thôi!"]) as worker, patch.object(translation, "log_to_video"):
        result = translation.translate_segments(str(source), str(output), "fixture")
    assert worker.call_args.kwargs["speech_durations"] == pytest.approx([.8])
    assert result[0]["end"] == 8


@pytest.mark.parametrize("language,target", [("vi", "vi"), ("en", "fr")])
def test_unknown_rate_or_same_language_does_not_trigger_compact_retranslation(tmp_path, language, target):
    source, output = tmp_path / "source.json", tmp_path / "translated.json"
    source.write_text(json.dumps([{"start": 0, "end": 1, "text": "A faithful original sentence.", "language": language}]), encoding="utf-8")
    text = "Một câu khá dài với rất nhiều từ để thử cơ chế không chạy lại vì đoán tốc độ."
    with patch.object(translation, "_translate_with_hymt2_worker", return_value=[text]) as worker, patch.object(translation, "log_to_video"):
        result = translation.translate_segments(str(source), str(output), "fixture", target_language=target)
    assert worker.call_count == 1
    assert result[0]["text"] == text

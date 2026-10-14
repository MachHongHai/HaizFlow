import json
from unittest.mock import Mock, patch

import pytest

from hflow.services import gemini_translation as gemini


class Response:
    def __init__(self, answer):
        self.answer = answer

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, *_args):
        return json.dumps(self.answer).encode("utf-8")


def envelope(rows, **kwargs):
    return {"candidates": [{"finishReason": "STOP", "content": {"parts": [
        {"text": json.dumps({"translations": rows})},
    ]}, **kwargs}]}


def call(chunk=None, **kwargs):
    return gemini._request_chunk(
        chunk or [(0, "Go now")], key="private-key", model="gemini-3.1-flash-lite",
        source_language="English", target_language="Vietnamese", video_id="fixture", **kwargs,
    )


def test_thought_parts_are_not_concatenated_with_translation_json():
    answer = envelope([{"id": 0, "text": "Đi thôi"}])
    parts = answer["candidates"][0]["content"]["parts"]
    parts.insert(0, {"thought": True, "text": "This is not JSON; never publish this."})
    parts.append({"thoughtSignature": "private-signature"})
    with patch.object(gemini.request, "urlopen", return_value=Response(answer)) as send:
        assert call() == ["Đi thôi"]
    assert send.call_count == 1
    config = json.loads(send.call_args.args[0].data)["generationConfig"]
    assert config["thinkingConfig"] == {"thinkingLevel": "minimal", "includeThoughts": False}


def test_split_text_parts_complete_json_fence_and_reordered_ids_are_supported():
    raw = "```json\n" + json.dumps({"translations": [
        {"id": 8, "text": "Tạm biệt"}, {"id": 3, "text": "Xin chào"},
    ]}) + "\n```"
    answer = envelope([])
    answer["candidates"][0]["content"]["parts"] = [{"text": raw[:20]}, {"text": raw[20:]}]
    with patch.object(gemini.request, "urlopen", return_value=Response(answer)) as send:
        assert call([(3, "Hello"), (8, "Goodbye")]) == ["Xin chào", "Tạm biệt"]
    assert send.call_count == 1


@pytest.mark.parametrize("bad", [
    [], {"candidates": []}, {"candidates": [{"content": {"parts": []}}]},
    {"candidates": [{"content": {"parts": [{"text": '{"translations": ['}]}}]},
    envelope([]), envelope([{"id": 0, "text": ""}]),
    envelope([{"id": 0, "text": 123}]), envelope([{"id": False, "text": "Bad ID"}]),
    envelope([{"id": "0", "text": "Bad ID"}]), envelope([{"id": 9, "text": "Wrong ID"}]),
    envelope([None]),
])
def test_invalid_answers_recover_only_the_failed_batch_with_bounded_retry(bad):
    good = envelope([{"id": 0, "text": "Đi thôi"}])
    with patch.object(gemini.request, "urlopen", side_effect=[Response(bad), Response(good)]) as send:
        assert call(speech_durations=[1]) == ["Đi thôi"]
    assert send.call_count == 2
    for invocation in send.call_args_list:
        payload = json.loads(invocation.args[0].data)
        entries = json.loads(payload["contents"][0]["parts"][0]["text"])
        assert entries[0]["id"] == 0
        assert entries[0]["speech_seconds"] == 1


def test_token_exhaustion_grows_cap_without_changing_source_or_duration():
    bad = {"candidates": [{"finishReason": "MAX_TOKENS"}], "usageMetadata": {
        "thoughtsTokenCount": 1600, "candidatesTokenCount": 448, "totalTokenCount": 2500,
    }}
    good = envelope([{"id": 0, "text": "Đi thôi"}])
    with (
        patch.object(gemini.request, "urlopen", side_effect=[Response(bad), Response(good)]) as send,
        patch.object(gemini, "log_to_video") as log,
    ):
        assert call(speech_durations=[1]) == ["Đi thôi"]
    payloads = [json.loads(invocation.args[0].data) for invocation in send.call_args_list]
    assert payloads[0]["generationConfig"]["maxOutputTokens"] >= 2048
    assert payloads[1]["generationConfig"]["maxOutputTokens"] == 8192
    assert payloads[0]["contents"] == payloads[1]["contents"]
    assert "response=token_limit" in str(log.call_args_list)
    assert "thoughtsTokenCount=1600" in str(log.call_args_list)


@pytest.mark.parametrize("answer", [
    {"promptFeedback": {"blockReason": "SAFETY"}},
    {"candidates": [{"finishReason": "SAFETY"}]},
    {"candidates": [{"finishReason": "RECITATION"}]},
])
def test_content_blocks_are_terminal_not_blindly_retried(answer):
    with patch.object(gemini.request, "urlopen", return_value=Response(answer)) as send:
        with pytest.raises(RuntimeError, match="nội dung"):
            call()
    assert send.call_count == 1


def test_permanent_malformed_response_has_three_attempt_limit_and_redacted_diagnostics():
    answer = {"candidates": [{"finishReason": "private-key", "content": {"parts": [
        {"text": "private-subtitle"}, {"thoughtSignature": "private-signature"},
    ]}}], "usageMetadata": {"totalTokenCount": "private-token"}}
    with (
        patch.object(gemini.request, "urlopen", return_value=Response(answer)) as send,
        patch.object(gemini, "log_to_video") as log,
    ):
        with pytest.raises(RuntimeError) as error:
            call()
    assert send.call_count == 1  # Unknown non-success finish cannot be accepted.
    for value in ("private-key", "private-subtitle", "private-signature", "private-token"):
        assert value not in str(log.call_args_list) + str(error.value)

    with patch.object(gemini.request, "urlopen", return_value=Response({})) as send:
        with pytest.raises(RuntimeError, match="dữ liệu dịch hợp lệ"):
            call()
    assert send.call_count == 3


def test_cancellation_after_response_prevents_retry_and_publication():
    with (
        patch.object(gemini.request, "urlopen", return_value=Response({})) as send,
        patch.object(gemini, "check_cancellation", side_effect=[None, RuntimeError("Video cancelled by user.")]),
    ):
        with pytest.raises(RuntimeError, match="cancelled"):
            call()
    assert send.call_count == 1


def test_cancellation_interrupts_retry_backoff():
    with patch.object(gemini, "check_cancellation", side_effect=RuntimeError("Video cancelled by user.")), patch.object(gemini.time, "sleep") as sleep:
        with pytest.raises(RuntimeError, match="cancelled"):
            gemini._retry_delay(8, "fixture")
    sleep.assert_not_called()


def test_successful_batches_and_resumed_cues_are_never_retranslated_on_recovery():
    requests = []

    def send(request, **_kwargs):
        payload = json.loads(request.data)
        entries = json.loads(payload["contents"][0]["parts"][0]["text"])
        requests.append([row["id"] for row in entries])
        if len(requests) == 2:
            return Response({})
        return Response(envelope([{"id": row["id"], "text": f"Câu {row['id']}"} for row in entries]))

    save = Mock()
    with patch.object(gemini, "active_key", return_value="fixture-key"), patch.object(gemini.request, "urlopen", side_effect=send):
        result = gemini.translate_texts(
            ["Short source"] * 25, model="gemini-3.1-flash-lite", source_language="English",
            target_language="Vietnamese", video_id="fixture", result_callback=save,
            initial_translations=["Giữ câu đầu"] + [None] * 24, speech_durations=[1] * 25,
        )
    assert requests == [list(range(1, 24)), [24], [24]]
    assert result[0] == "Giữ câu đầu"
    assert result[-1] == "Câu 24"
    assert save.call_count == 2


def test_duplicate_ids_cannot_overwrite_a_different_cue():
    answer = envelope([{"id": 3, "text": "One"}, {"id": 3, "text": "Two"}])
    with pytest.raises(gemini._ResponseError, match="mã câu"):
        gemini._parse_translations(answer, [(3, "One"), (4, "Two")])

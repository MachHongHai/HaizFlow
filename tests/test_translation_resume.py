import json
import io
import queue
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from haizflow.services import gemini_translation, hymt2_worker, translation
from haizflow.services.translation_progress import TranslationProgress
from haizflow.pipeline import process_video


def test_frozen_worker_request_preserves_unicode_with_windows_system_code_page():
    process = Mock()
    process.stdin = io.StringIO()
    process.poll.return_value = None
    output = queue.Queue()
    output.put(json.dumps({"event": "response", "request_id": "fixture",
                           "translations": ["Chào bạn", "Cảm ơn"]}))
    with (
        patch.object(translation, "_ensure_hymt2_worker", return_value=(process, output)),
        patch.object(translation, "_WORKER_PROCESS", process),
        patch.object(translation.uuid, "uuid4", return_value=SimpleNamespace(hex="fixture")),
        patch.object(translation, "register_process"),
        patch.object(translation, "unregister_process"),
        patch.object(translation, "_schedule_worker_idle_shutdown"),
        patch.object(translation, "log_to_video"),
    ):
        result = translation._translate_with_hymt2_worker(
            ["你好", "谢谢"], video_id="fixture", source_languages=["Chinese", "Chinese"],
            target_language_name="Vietnamese", initial_translations=["Chào bạn", None],
        )
    line = process.stdin.getvalue()
    assert line.isascii()
    decoded = json.loads(line.encode("utf-8").decode("cp1252"))["payload"]
    assert decoded["texts"] == ["你好", "谢谢"]
    assert decoded["initial_translations"] == ["Chào bạn", None]
    assert result == ["Chào bạn", "Cảm ơn"]


def test_partial_translation_survives_pause_without_publishing_and_resumes_missing_only(tmp_path):
    source = tmp_path / "source.json"
    output = tmp_path / "translated.json"
    progress = tmp_path / "stable-progress.json"
    source.write_text(json.dumps([
        {"start": 0, "end": 1, "text": "Hello friend", "language": "en"},
        {"start": 1, "end": 2, "text": "Goodbye friend", "language": "en"},
    ]), encoding="utf-8")
    output.write_text('[{"text":"previous published result"}]', encoding="utf-8")

    def interrupted(texts, **kwargs):
        kwargs["result_callback"]([0], ["Chào bạn"])
        raise RuntimeError("Video cancelled by user.")

    with patch.object(translation, "log_to_video"), patch.object(translation, "_translate_with_hymt2_worker", side_effect=interrupted):
        with pytest.raises(RuntimeError, match="cancelled"):
            translation.translate_segments(str(source), str(output), "fixture", checkpoint_path=str(progress))
    assert json.loads(output.read_text(encoding="utf-8"))[0]["text"] == "previous published result"
    assert json.loads(progress.read_text(encoding="utf-8"))["translations"] == ["Chào bạn", None]

    def resumed(texts, **kwargs):
        assert kwargs["translate_indices"] == [1]
        assert kwargs["initial_translations"] == ["Chào bạn", None]
        kwargs["result_callback"]([1], ["Tạm biệt bạn"])
        return ["Chào bạn", "Tạm biệt bạn"]

    with patch.object(translation, "log_to_video"), patch.object(translation, "_translate_with_hymt2_worker", side_effect=resumed) as worker:
        translation.translate_segments(str(source), str(output), "fixture", checkpoint_path=str(progress))
    assert worker.call_count == 1
    assert [row["text"] for row in json.loads(output.read_text(encoding="utf-8"))] == ["Chào bạn", "Tạm biệt bạn"]
    assert not progress.exists()


def test_checkpoint_never_reuses_changed_inputs_or_settings(tmp_path):
    path = tmp_path / "progress.json"
    old = TranslationProgress(path, {"text": "old", "model": "full"}, 2)
    old.save_batch([0], ["Đã dịch"])
    assert TranslationProgress(path, {"text": "old", "model": "full"}, 2).values == ["Đã dịch", None]
    assert TranslationProgress(path, {"text": "new", "model": "full"}, 2).values == [None, None]
    assert TranslationProgress(path, {"text": "old", "model": "q4"}, 2).values == [None, None]
    old.clear()
    assert TranslationProgress(path, {"text": "old", "model": "full"}, 2).values == [None, None]


def test_invalid_partial_checkpoint_is_ignored(tmp_path):
    path = tmp_path / "progress.json"
    path.write_text('{"schema":1,"translations":[42]}', encoding="utf-8")
    progress = TranslationProgress(path, {}, 1)
    assert progress.values == [None]
    with pytest.raises(ValueError):
        progress.save_batch([0], [""])


def test_gemini_resume_preserves_sentence_ids_and_saves_each_completed_batch():
    completed = Mock()
    with (
        patch.object(gemini_translation, "active_key", return_value="fixture"),
        patch.object(gemini_translation, "check_cancellation"),
        patch.object(gemini_translation, "log_to_video"),
        patch.object(gemini_translation, "_request_chunk", return_value=["Câu thứ hai", "Câu thứ ba"]) as send,
    ):
        result = gemini_translation.translate_texts(
            ["one", "two", "three"], model=next(iter(gemini_translation.MODELS)),
            source_language="English", target_language="Vietnamese", video_id="fixture",
            initial_translations=["Câu thứ nhất", None, None], result_callback=completed,
        )
    assert send.call_args.args[0] == [(1, "two"), (2, "three")]
    completed.assert_called_once_with([1, 2], ["Câu thứ hai", "Câu thứ ba"])
    assert result == ["Câu thứ nhất", "Câu thứ hai", "Câu thứ ba"]


def test_hymt2_resume_skips_completed_batches_and_reports_durable_results():
    events = []
    with (
        patch.object(hymt2_worker, "_model_runtime", return_value=(None, None, None, "cpu")),
        patch.object(hymt2_worker, "_inference_batches", return_value=[(0, 1), (1, 2)]),
        patch.object(hymt2_worker, "_translate_prompt_batch", return_value=["Tạm biệt bạn"]) as generate,
        patch.object(hymt2_worker, "_emit_event", side_effect=events.append),
    ):
        result = hymt2_worker.translate({
            "texts": ["Hello friend", "Goodbye friend"], "source_languages": ["English", "English"],
            "target_language_name": "Vietnamese", "translate_indices": [1],
            "initial_translations": ["Chào bạn", None],
        })
    assert result == ["Chào bạn", "Tạm biệt bạn"]
    assert generate.call_count == 1
    assert events[0]["event"] == "batch_started" and events[0]["start"] == 2
    assert events[-1]["indices"] == [1]
    assert events[-1]["translations"] == ["Tạm biệt bạn"]
    assert events[-1]["current"] == 2


def test_auto_resume_does_not_repeat_recognition_before_resuming_translation(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    output = tmp_path / "recognized.json"
    video = SimpleNamespace(video_id="fixture", project_type="single", files={"video_input": str(source)},
                            source_language="auto", speech_recognition_model="small", enable_audio_separation=False,
                            resume_step="", checkpoints={})
    segments = [{"start": 0, "end": 1, "text": "Hello friend", "language": "en"}]

    def recognize(*args, **kwargs):
        output.write_text(json.dumps(segments), encoding="utf-8")
        return segments, "en"

    with patch.object(process_video, "transcribe", side_effect=recognize) as asr, patch.object(process_video, "update_video"):
        first = process_video._recognize_for_translation(video, Mock(), "audio.wav", str(output))
        video.resume_step = "translating"
        second = process_video._recognize_for_translation(video, Mock(), "audio.wav", str(output))
    assert first == second
    assert asr.call_count == 1


def test_completed_translation_survives_discarded_staging_until_caller_publishes(tmp_path):
    source, output, progress = (tmp_path / name for name in ("source.json", "stage.json", "progress.json"))
    source.write_text(json.dumps([{"start": 0, "end": 1, "text": "Hello friend", "language": "en"}]))
    with (patch.object(translation, "log_to_video"),
          patch.object(translation, "_translate_with_hymt2_worker", return_value=["Chào bạn"]) as worker):
        first = translation.translate_segments(str(source), str(output), "fixture",
                    checkpoint_path=str(progress), retain_checkpoint=True)
        assert progress.exists()
        output.unlink()  # Pause after final JSON, before immutable publication
        second = translation.translate_segments(str(source), str(output), "fixture",
                    checkpoint_path=str(progress), retain_checkpoint=True)
    assert first == second
    assert worker.call_count == 1


def test_gemini_pause_during_received_response_saves_batch_before_stopping(tmp_path):
    source, output, progress = (tmp_path / name for name in ("source.json", "stage.json", "progress.json"))
    source.write_text(json.dumps([{"start": 0, "end": 1, "text": "Hello friend", "language": "en"}]))
    paused = False
    def check(_video):
        if paused:
            raise RuntimeError("Video cancelled by user.")
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def read(self, *_args):
            nonlocal paused
            paused = True
            return json.dumps({"candidates": [{"finishReason": "STOP", "content": {"parts": [
                {"text": json.dumps({"translations": [{"id": 0, "text": "Chào bạn"}]})}
            ]}}]}).encode()
    with (patch.object(translation, "log_to_video"), patch.object(gemini_translation, "log_to_video"),
          patch.object(translation, "check_cancellation", side_effect=check),
          patch.object(gemini_translation, "check_cancellation", side_effect=check),
          patch.object(gemini_translation, "is_paused", side_effect=lambda _: paused),
          patch.object(gemini_translation, "active_key", return_value="fixture"),
          patch.object(gemini_translation, "_open_request", return_value=Response()) as request):
        with pytest.raises(RuntimeError, match="cancelled"):
            translation.translate_segments(str(source), str(output), "fixture", provider="gemini",
                translation_model="gemini-3.1-flash-lite", checkpoint_path=str(progress))
        assert not output.exists()
        assert json.loads(progress.read_text())["translations"] == ["Chào bạn"]
        paused = False
        translation.translate_segments(str(source), str(output), "fixture", provider="gemini",
            translation_model="gemini-3.1-flash-lite", checkpoint_path=str(progress))
        assert request.call_count == 1


def test_gemini_cancel_does_not_save_late_response_or_start_another_batch():
    cancelled = False
    def check(_video):
        if cancelled:
            raise RuntimeError("Video cancelled by user.")
    def send(*_args, **_kwargs):
        nonlocal cancelled
        cancelled = True
        return ["Chào bạn"]
    saved = Mock()
    with (patch.object(gemini_translation, "check_cancellation", side_effect=check),
          patch.object(gemini_translation, "is_paused", return_value=False),
          patch.object(gemini_translation, "active_key", return_value="fixture"),
          patch.object(gemini_translation, "log_to_video"),
          patch.object(gemini_translation, "_request_chunk", side_effect=send) as request):
        with pytest.raises(RuntimeError, match="cancelled"):
            gemini_translation.translate_texts(["Hello"], model="gemini-3.1-flash-lite",
                source_language="English", target_language="Vietnamese", video_id="fixture", result_callback=saved)
    saved.assert_not_called()
    assert request.call_count == 1


def test_hymt2_progress_is_saved_before_pause_callback(tmp_path):
    progress = TranslationProgress(tmp_path / "progress.json", {}, 2)
    process = Mock()
    process.stdin = io.StringIO()
    process.poll.return_value = None
    output = queue.Queue()
    output.put(json.dumps({"event": "progress", "current": 1, "total": 2,
                           "indices": [0], "translations": ["Chào bạn"]}))
    with (patch.object(translation, "_ensure_hymt2_worker", return_value=(process, output)),
          patch.object(translation, "register_process"), patch.object(translation, "unregister_process"),
          patch.object(translation, "_terminate_hymt2_worker"), patch.object(translation, "log_to_video")):
        with pytest.raises(RuntimeError, match="paused"):
            translation._translate_with_hymt2_worker(["Hello", "Bye"], video_id="fixture",
                source_languages=["English", "English"], target_language_name="Vietnamese",
                result_callback=progress.save_batch,
                progress_callback=Mock(side_effect=RuntimeError("paused")))
    assert TranslationProgress(progress.path, {}, 2).values == ["Chào bạn", None]


def test_manual_translation_pause_at_publication_reuses_completed_batches(tmp_path):
    from haizflow.pipeline import manual_tools
    from haizflow.services import translation_progress

    source = tmp_path / "source.json"
    source.write_text(json.dumps([{"start": 0, "end": 1, "text": "Hello friend", "language": "en"}]))
    checkpoint = tmp_path / "translation-progress.json"
    stages = [tmp_path / "stage-1", tmp_path / "stage-2"]
    for path in stages:
        path.mkdir()
    recognition = {"artifact_id": "recognition:fixture", "resolved_outputs": {"segments": str(source)}}
    video = SimpleNamespace(video_id="fixture", target_language="vi", translation_model="auto", files={})
    with (patch.object(manual_tools, "recognition_signature", return_value="recognition"),
          patch.object(manual_tools, "translation_signature", return_value="generation-1"),
          patch.object(manual_tools.manual_artifacts, "resolve",
                       side_effect=lambda _id, kind, _sig: recognition if kind == "recognition" else None),
          patch.object(manual_tools.manual_artifacts, "create_staging_directory", side_effect=stages),
          patch.object(manual_tools.manual_artifacts, "publish", side_effect=[RuntimeError("paused"), recognition]),
          patch.object(manual_tools, "_release_recognition_runtime"),
          patch("haizflow.pipeline.omnivoice_tts.clear_runtime"),
          patch("haizflow.core.hardware.processing_device_preference", return_value="gpu"),
          patch.object(manual_tools, "_replace_subtitles_from_translation"),
          patch.object(translation_progress, "manual_progress_path", return_value=checkpoint),
          patch.object(translation, "log_to_video"),
          patch.object(translation, "_translate_with_hymt2_worker", return_value=["Chào bạn"]) as worker):
        with pytest.raises(RuntimeError, match="paused"):
            manual_tools._run_translation(video, Mock())
        assert checkpoint.exists()
        assert not stages[0].exists()
        manual_tools._run_translation(video, Mock())
        assert worker.call_count == 1
        assert not checkpoint.exists()


def test_explicit_translation_generation_never_reuses_identical_old_text(tmp_path):
    source, output, progress = (tmp_path / name for name in ("source.json", "stage.json", "progress.json"))
    source.write_text(json.dumps([{"start": 0, "end": 1, "text": "Hello friend", "language": "en"}]))
    with (patch.object(translation, "log_to_video"),
          patch.object(translation, "_translate_with_hymt2_worker", return_value=["Chào bạn"]) as worker):
        for key in ("generation-1", "generation-2"):
            translation.translate_segments(str(source), str(output), "fixture", checkpoint_path=str(progress),
                                           retain_checkpoint=True, checkpoint_key=key)
        assert worker.call_count == 2

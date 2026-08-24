import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.pipeline import tts


def _write_test_mp3(path: str) -> None:
    Path(path).write_bytes(b"\xff\xf3\x64" + b"\x00" * 700)


class TtsReliabilityTests(unittest.TestCase):
    def test_legacy_provider_aliases_migrate_to_omnivoice(self):
        self.assertEqual(tts.resolve_tts_provider("auto", "vi"), "omnivoice")
        self.assertEqual(tts.resolve_tts_provider("vieneu", "en"), "omnivoice")
        self.assertEqual(tts.resolve_tts_provider("omnivoice", "ja"), "omnivoice")

    def test_unknown_provider_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported TTS provider"):
            tts.resolve_tts_provider("unknown", "vi")

    def test_empty_transcript_is_rejected_before_reporting_tts_success(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            segments_path = Path(temp_dir) / "segments.json"
            segments_path.write_text("[]", encoding="utf-8")
            with mock.patch.object(tts, "log_to_video"):
                with self.assertRaisesRegex(RuntimeError, "at least one translated subtitle"):
                    tts.generate_voice_parts(
                        str(segments_path),
                        str(Path(temp_dir) / "voice"),
                        "voice",
                        "video",
                    )

    def test_text_normalization_removes_transport_sensitive_punctuation(self):
        normalized = tts.preprocess_text_for_tts("  Xin\u00a0chao\u200b \u2013 tu nhien\u2026  ")
        self.assertEqual(normalized, "Xin chao, tu nhien...")

    def test_long_edge_request_is_split_at_natural_boundaries(self):
        text = "Câu thứ nhất có độ dài vừa phải. " * 8 + "Câu thứ hai cũng phải được giữ nguyên từ và dấu câu. " * 5

        chunks = tts._split_edge_request(text, limit=120)

        self.assertGreater(len(chunks), 2)
        self.assertTrue(all(0 < len(chunk) <= 120 for chunk in chunks))
        self.assertEqual(
            " ".join(chunks).replace("  ", " "),
            tts.preprocess_text_for_tts(text),
        )

    def test_long_chinese_edge_request_is_split_without_losing_text(self):
        text = "这是一个很长的中文字幕片段，用于验证在线语音请求不会因为缺少空格而成为一个超长请求。" * 5

        chunks = tts._split_edge_request(text, limit=64)

        self.assertGreater(len(chunks), 2)
        self.assertTrue(all(0 < len(chunk) <= 64 for chunk in chunks))
        self.assertEqual("".join(chunks), tts.preprocess_text_for_tts(text))

    def test_segment_retry_uses_a_fresh_connection_and_atomic_valid_file(self):
        class FakeCommunicate:
            calls = 0

            def __init__(self, *_args, **_kwargs):
                type(self).calls += 1
                self.call = type(self).calls

            async def save(self, path):
                if self.call == 1:
                    raise RuntimeError("No audio was received")
                _write_test_mp3(path)

        async def no_wait(*_args, **_kwargs):
            return None

        with tempfile.TemporaryDirectory() as temp_dir:
            output = str(Path(temp_dir) / "voice.mp3")
            with (
                mock.patch.object(tts.edge_tts, "Communicate", FakeCommunicate),
                mock.patch.object(tts, "_sleep_with_cancellation", no_wait),
            ):
                attempts = asyncio.run(tts.tts_segment_with_retry("Xin chao", "voice", output, retries=2))

            self.assertEqual(attempts, 2)
            self.assertTrue(tts._is_valid_mp3(output))
            self.assertEqual(list(Path(temp_dir).glob("*.part-*")), [])

    def test_edge_request_timeout_cancels_a_stalled_connection(self):
        class StalledCommunicate:
            cancelled = False

            async def save(self, _path):
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    type(self).cancelled = True
                    raise

        clock = {"value": 0.0}

        async def fast_wait(_tasks, timeout):
            clock["value"] += float(timeout or 0)
            await asyncio.sleep(0)
            return set(), set()

        class FastLoop:
            @staticmethod
            def time():
                return clock["value"]

        async def run_timeout():
            with (
                mock.patch.object(tts.asyncio, "wait", fast_wait),
                mock.patch.object(tts.asyncio, "get_running_loop", return_value=FastLoop()),
                mock.patch.object(tts, "_EDGE_REQUEST_TIMEOUT_SECONDS", 0.5),
            ):
                await tts._save_with_cancellation(StalledCommunicate(), "unused.mp3", None)

        with self.assertRaises(TimeoutError):
            asyncio.run(run_timeout())
        self.assertTrue(StalledCommunicate.cancelled)

    def test_failed_parallel_segment_is_recovered_sequentially(self):
        calls = []

        async def fake_synthesize(text, _voice, output_path, retries=3, **_kwargs):
            calls.append((text, retries))
            if text == "second" and retries == tts._INITIAL_RETRIES:
                raise RuntimeError("No audio was received")
            _write_test_mp3(output_path)
            return 1

        async def no_wait(*_args, **_kwargs):
            return None

        with tempfile.TemporaryDirectory() as temp_dir:
            segments_path = Path(temp_dir) / "segments.json"
            segments_path.write_text(
                json.dumps([{"text": "first"}, {"text": "second"}, {"text": "third"}]),
                encoding="utf-8",
            )
            voice_dir = Path(temp_dir) / "voice"
            progress = []
            with (
                mock.patch.object(tts, "tts_segment_with_retry", fake_synthesize),
                mock.patch.object(tts, "_sleep_with_cancellation", no_wait),
                mock.patch.object(tts, "log_to_video"),
            ):
                tts.generate_voice_parts(
                    str(segments_path),
                    str(voice_dir),
                    "voice",
                    "video",
                    lambda current, total: progress.append((current, total)),
                )

            self.assertIn(("second", tts._RECOVERY_RETRIES), calls)
            self.assertEqual(progress[-1], (3, 3))
            self.assertTrue(all(tts._is_valid_mp3(str(path)) for path in voice_dir.glob("*.mp3")))

    def test_parallel_tts_logs_distinguish_segment_order_from_overall_progress(self):
        async def fake_synthesize(text, _voice, output_path, retries=3, **_kwargs):
            if text == "second":
                await asyncio.sleep(0.01)
            _write_test_mp3(output_path)
            return 1

        with tempfile.TemporaryDirectory() as temp_dir:
            segments_path = Path(temp_dir) / "segments.json"
            segments_path.write_text(
                json.dumps([{"text": "first"}, {"text": "second"}, {"text": "third"}]),
                encoding="utf-8",
            )
            logs = []
            with (
                mock.patch.object(tts, "tts_segment_with_retry", fake_synthesize),
                mock.patch.object(tts, "log_to_video", lambda _video, line: logs.append(line)),
            ):
                tts.generate_voice_parts(str(segments_path), str(Path(temp_dir) / "voice"), "voice", "video")

        self.assertTrue(any("[TTS][START] segment=1/3" in line for line in logs))
        self.assertTrue(any("[TTS][START] segment=1/3" in line and 'text="first"' in line for line in logs))
        self.assertTrue(any("[TTS][COMPLETE] segment=1/3 overall=1/3" in line for line in logs))
        self.assertTrue(all("Creating voice" not in line for line in logs))

    def test_tts_sentence_preview_is_single_line_and_bounded(self):
        preview = tts._tts_text_preview('  First line\n"second line"  ' + "x" * 300)

        self.assertNotIn("\n", preview)
        self.assertIn("First line 'second line'", preview)
        self.assertTrue(preview.endswith('..."'))
        self.assertLessEqual(len(preview), 222)

    def test_default_tts_execution_never_opens_two_edge_requests_at_once(self):
        active = 0
        maximum_active = 0

        async def measured_synthesize(_text, _voice, output_path, retries=3, **_kwargs):
            nonlocal active, maximum_active
            active += 1
            maximum_active = max(maximum_active, active)
            await asyncio.sleep(0.01)
            _write_test_mp3(output_path)
            active -= 1
            return 1

        with tempfile.TemporaryDirectory() as temp_dir:
            segments_path = Path(temp_dir) / "segments.json"
            segments_path.write_text(
                json.dumps([{"text": str(index)} for index in range(6)]),
                encoding="utf-8",
            )
            with (
                mock.patch.object(tts, "TTS_MAX_CONCURRENCY", 1),
                mock.patch.object(tts, "tts_segment_with_retry", measured_synthesize),
                mock.patch.object(tts, "log_to_video"),
            ):
                tts.generate_voice_parts(str(segments_path), str(Path(temp_dir) / "voice"), "voice", "video")

        self.assertEqual(maximum_active, 1)

    def test_tts_retry_log_contains_a_stable_error_label(self):
        async def fail_once(*_args, **kwargs):
            retry_callback = kwargs["retry_callback"]
            retry_callback(1, 3, RuntimeError("No audio was received"), 1.5)
            raise RuntimeError("No audio was received")

        async def no_wait(*_args, **_kwargs):
            return None

        with tempfile.TemporaryDirectory() as temp_dir:
            segments_path = Path(temp_dir) / "segments.json"
            segments_path.write_text(json.dumps([{"text": "failed"}]), encoding="utf-8")
            logs = []
            with (
                mock.patch.object(tts, "tts_segment_with_retry", fail_once),
                mock.patch.object(tts, "_sleep_with_cancellation", no_wait),
                mock.patch.object(tts, "log_to_video", lambda _video, line: logs.append(line)),
            ):
                with self.assertRaisesRegex(RuntimeError, "segment\\(s\\): 1"):
                    tts.generate_voice_parts(str(segments_path), str(Path(temp_dir) / "voice"), "voice", "video")

        self.assertTrue(any("[TTS][RETRY]" in line and "error=edge_no_audio" in line for line in logs))
        self.assertTrue(any("[TTS][FAILED]" in line and "error=edge_no_audio" in line for line in logs))

    def test_permanent_failure_stops_pipeline_without_silence_file(self):
        async def always_fail(*_args, **_kwargs):
            raise RuntimeError("No audio was received")

        async def no_wait(*_args, **_kwargs):
            return None

        with tempfile.TemporaryDirectory() as temp_dir:
            segments_path = Path(temp_dir) / "segments.json"
            segments_path.write_text(json.dumps([{"text": "failed"}]), encoding="utf-8")
            voice_dir = Path(temp_dir) / "voice"
            with (
                mock.patch.object(tts, "tts_segment_with_retry", always_fail),
                mock.patch.object(tts, "_sleep_with_cancellation", no_wait),
                mock.patch.object(tts, "log_to_video"),
            ):
                with self.assertRaisesRegex(RuntimeError, "segment\\(s\\): 1"):
                    tts.generate_voice_parts(str(segments_path), str(voice_dir), "voice", "video")

            output = voice_dir / "voice_0001.mp3"
            self.assertFalse(output.exists())

    def test_resume_reuses_verified_parts_and_regenerates_only_missing_audio(self):
        calls = []

        async def fake_synthesize(text, _voice, output_path, retries=3, **_kwargs):
            calls.append((text, retries))
            _write_test_mp3(output_path)
            return 1

        with tempfile.TemporaryDirectory() as temp_dir:
            segments_path = Path(temp_dir) / "segments.json"
            segments_path.write_text(
                json.dumps([{"text": "existing"}, {"text": "missing"}]),
                encoding="utf-8",
            )
            voice_dir = Path(temp_dir) / "voice"
            voice_dir.mkdir()
            _write_test_mp3(str(voice_dir / "voice_0001.mp3"))
            (voice_dir / "voice_0002.mp3").write_bytes(b"")

            with (
                mock.patch.object(tts, "tts_segment_with_retry", fake_synthesize),
                mock.patch.object(tts, "log_to_video"),
            ):
                tts.generate_voice_parts(str(segments_path), str(voice_dir), "voice", "video")

            self.assertEqual(calls, [("missing", tts._INITIAL_RETRIES)])
            self.assertTrue(tts._is_valid_mp3(str(voice_dir / "voice_0001.mp3")))
            self.assertTrue(tts._is_valid_mp3(str(voice_dir / "voice_0002.mp3")))

    def test_omnivoice_loads_once_for_all_missing_segments(self):
        from haizflow.pipeline import omnivoice_tts

        calls = []

        def synthesize_batch(items, video_id, *, language_id, speaker_mode="single", progress_callback=None):
            calls.append((items, video_id, language_id, speaker_mode))
            for completed, item in enumerate(items, 1):
                _write_test_mp3(item["output_path"])
                if progress_callback is not None:
                    progress_callback(completed, len(items), "synthesizing")

        with tempfile.TemporaryDirectory() as temp_dir:
            segments_path = Path(temp_dir) / "segments.json"
            segments_path.write_text(
                json.dumps([{"text": "Xin chào"}, {"text": "Thế giới"}]),
                encoding="utf-8",
            )
            voice_dir = Path(temp_dir) / "voice"
            with (
                mock.patch.object(omnivoice_tts, "synthesize_batch_to_mp3", side_effect=synthesize_batch),
                mock.patch.object(omnivoice_tts, "runtime_description", return_value="cpu worker"),
                mock.patch.object(tts, "log_to_video"),
            ):
                tts.generate_voice_parts(
                    str(segments_path),
                    str(voice_dir),
                    "omnivoice:female",
                    "video",
                    provider="omnivoice",
                    target_language="vi",
                )

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1:], ("video", "vi", "single"))
        self.assertEqual([item["text"] for item in calls[0][0]], ["Xin chào.", "Thế giới."])

    def test_omnivoice_multiple_speakers_follow_source_timestamps_not_list_indexes(self):
        from haizflow.pipeline import omnivoice_tts

        calls = []

        def synthesize_batch(items, video_id, *, language_id, speaker_mode="single", progress_callback=None):
            calls.append((items, video_id, language_id, speaker_mode))
            for item in items:
                _write_test_mp3(item["output_path"])

        with tempfile.TemporaryDirectory() as temp_dir:
            video_root = Path(temp_dir) / "video"
            input_path = video_root / "input" / "video.mp4"
            source_audio = video_root / "temp" / "speech.wav"
            source_segments = video_root / "temp" / "source_segments.json"
            input_path.parent.mkdir(parents=True)
            source_audio.parent.mkdir(parents=True)
            input_path.write_bytes(b"video")
            source_audio.write_bytes(b"audio")
            source_segments.write_text(
                json.dumps(
                    [
                        {"start": 0.0, "end": 2.0, "text": "first source voice"},
                        {"start": 4.0, "end": 7.0, "text": "second source voice"},
                    ]
                ),
                encoding="utf-8",
            )
            translated = video_root / "temp" / "translated.json"
            translated.write_text(
                json.dumps(
                    [
                        {"start": 5.0, "end": 6.0, "text": "Second translated line"},
                        {"start": 0.5, "end": 1.5, "text": "First translated line"},
                    ]
                ),
                encoding="utf-8",
            )
            video = SimpleNamespace(
                speaker_mode="multiple",
                files={"video_input": str(input_path), "speech_audio": str(source_audio)},
            )
            with (
                mock.patch.object(tts, "get_video", return_value=video),
                mock.patch.object(omnivoice_tts, "synthesize_batch_to_mp3", side_effect=synthesize_batch),
                mock.patch.object(omnivoice_tts, "runtime_description", return_value="cpu worker"),
                mock.patch.object(tts, "log_to_video"),
            ):
                tts.generate_voice_parts(
                    str(translated),
                    str(video_root / "temp" / "voices"),
                    "omnivoice:female",
                    "video",
                    provider="omnivoice",
                    target_language="vi",
                )

        self.assertEqual(len(calls), 1)
        items, _video_id, _language_id, speaker_mode = calls[0]
        self.assertEqual(speaker_mode, "multiple")
        self.assertEqual([item["source_text"] for item in items], [
            "second source voice",
            "first source voice",
        ])

    def test_omnivoice_cuda_engine_failure_triggers_cpu_fallback(self):
        from haizflow.pipeline.omnivoice_tts import _is_cuda_resource_failure

        self.assertTrue(
            _is_cuda_resource_failure(
                "RuntimeError: GET was unable to find an engine to execute this computation"
            )
        )

    def test_omnivoice_presets_use_the_sdk_instruction_vocabulary(self):
        from haizflow.desktop.catalog import OMNIVOICE_TTS_VOICES
        from haizflow.pipeline.omnivoice_tts import OMNIVOICE_VOICE_INSTRUCTIONS

        valid_items = {
            "male",
            "female",
            "child",
            "young adult",
            "elderly",
            "whisper",
            "low pitch",
            "moderate pitch",
            "high pitch",
            "very high pitch",
        }
        for instruction in OMNIVOICE_VOICE_INSTRUCTIONS.values():
            self.assertTrue(set(instruction.split(", ")).issubset(valid_items))
        catalog_voices = {voice for voice, _label, _category in OMNIVOICE_TTS_VOICES}
        self.assertEqual(
            catalog_voices - {"omnivoice:clone"},
            set(OMNIVOICE_VOICE_INSTRUCTIONS),
        )

    def test_omnivoice_maps_standard_arabic_to_the_sdk_language_id(self):
        from haizflow.pipeline.omnivoice_tts import _omnivoice_language_id

        self.assertEqual(_omnivoice_language_id("ar"), "arb")
        self.assertEqual(_omnivoice_language_id("vi"), "vi")

    def test_omnivoice_status_update_retries_transient_windows_lock(self):
        from haizflow.pipeline import omnivoice_tts

        with tempfile.TemporaryDirectory() as temp_dir:
            status_path = Path(temp_dir) / "status.json"
            real_replace = omnivoice_tts.os.replace
            attempts = []

            def replace_after_unlock(source, destination):
                attempts.append((source, destination))
                if len(attempts) < 3:
                    raise PermissionError(5, "Access is denied")
                return real_replace(source, destination)

            with (
                mock.patch.object(omnivoice_tts.os, "replace", side_effect=replace_after_unlock),
                mock.patch.object(omnivoice_tts.time, "sleep"),
            ):
                written = omnivoice_tts._write_status_file(
                    status_path,
                    {"completed": 6, "total": 8, "stage": "synthesizing", "current": 7},
                )

            self.assertTrue(written)
            self.assertEqual(len(attempts), 3)
            self.assertEqual(json.loads(status_path.read_text(encoding="utf-8"))["completed"], 6)
            self.assertEqual(list(Path(temp_dir).glob("*.part")), [])

    def test_omnivoice_status_failure_never_stops_synthesis_worker(self):
        from haizflow.pipeline import omnivoice_tts

        with tempfile.TemporaryDirectory() as temp_dir:
            status_path = Path(temp_dir) / "status.json"
            with (
                mock.patch.object(omnivoice_tts.os, "replace", side_effect=PermissionError(5, "Access is denied")),
                mock.patch.object(omnivoice_tts.time, "sleep"),
            ):
                written = omnivoice_tts._write_status_file(status_path, {"completed": 1})

            self.assertFalse(written)
            self.assertEqual(list(Path(temp_dir).glob("*.part")), [])

    def test_omnivoice_anchor_is_informative_without_using_longest_paragraph(self):
        from haizflow.pipeline.omnivoice_tts import _select_voice_anchor

        short = {"text": "Ồ."}
        suitable = {"text": "Một câu đủ rõ để giữ ổn định danh tính giọng đọc trong toàn bộ video."}
        huge = {"text": "Đây là một đoạn rất dài. " * 40}

        self.assertIs(_select_voice_anchor([short, huge, suitable]), suitable)

    def test_omnivoice_anchor_excerpt_keeps_one_bounded_sentence(self):
        from haizflow.pipeline.omnivoice_tts import _voice_anchor_excerpt

        paragraph = (
            "Đây là phần dẫn rất dài nhưng vẫn có dấu câu để nhận diện. "
            "Câu này cung cấp một mẫu giọng vừa đủ rõ và ổn định cho toàn bộ video. "
            "Phần còn lại không nên bị đưa vào mẫu giọng vì làm suy luận chậm hơn." * 4
        )

        excerpt = _voice_anchor_excerpt(paragraph)

        self.assertGreaterEqual(len(excerpt), 24)
        self.assertLessEqual(len(excerpt), 120)
        self.assertNotEqual(excerpt, paragraph)

    def test_omnivoice_anchor_excerpt_does_not_cut_short_text(self):
        from haizflow.pipeline.omnivoice_tts import _voice_anchor_excerpt

        text = "Một câu ngắn phù hợp để tạo mẫu giọng."
        self.assertEqual(_voice_anchor_excerpt(text), text)

    def test_omnivoice_gpu_fallback_only_matches_runtime_resource_failures(self):
        from haizflow.pipeline.omnivoice_tts import _is_cuda_resource_failure

        self.assertTrue(_is_cuda_resource_failure("CUDA out of memory"))
        self.assertTrue(_is_cuda_resource_failure("CUBLAS_STATUS_ALLOC_FAILED"))
        self.assertFalse(_is_cuda_resource_failure("Unsupported instruct items"))


if __name__ == "__main__":
    unittest.main()

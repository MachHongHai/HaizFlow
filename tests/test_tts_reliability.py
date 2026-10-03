import io
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
    def test_short_source_fragment_uses_library_reference_not_clone(self):
        from haizflow.pipeline import omnivoice_tts

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def synthesize(_path, request, _id, _callback):
                self.assertEqual(request["items"][0]["reference_path"], "")
                self.assertTrue(request["preset_reference_path"])
                Path(request["items"][0]["wav_path"]).write_bytes(b"RIFF" + bytes(256))
                return 0, ""

            with (mock.patch.object(omnivoice_tts, "_prepare_isolated_runtime"),
                  mock.patch.object(omnivoice_tts, "verify_omnivoice_model", return_value=root),
                  mock.patch.object(omnivoice_tts, "_sdk_root", return_value=root),
                  mock.patch.object(omnivoice_tts, "_run_worker_process", side_effect=synthesize),
                  mock.patch.object(omnivoice_tts, "_encode_mp3", side_effect=lambda _wav, output, _id: _write_test_mp3(str(output))),
                  mock.patch.object(omnivoice_tts, "log_to_video")):
                omnivoice_tts.synthesize_batch_to_mp3([
                    {"text": "Đây là một câu thoại ngắn.", "voice": "omnivoice:female",
                     "output_path": str(root / "voice.mp3"), "source_audio_path": "source.wav",
                     "source_start": "1", "source_end": "2.2", "source_text": "This is a short sentence."}
                ], "test", language_id="vi", speaker_mode="multiple", device="cpu")

    def test_packaged_reference_matches_preview_identity_and_transcript(self):
        from haizflow.pipeline.omnivoice_tts import _preset_reference
        path, text = _preset_reference("omnivoice:male", "en")
        self.assertTrue(Path(path).is_file())
        self.assertIn("Mạch Hồng Hải", text)
        self.assertEqual(_preset_reference("../untrusted", "en"), ("", ""))

    def test_completed_clips_are_committed_before_worker_pause(self):
        from haizflow.pipeline import omnivoice_tts
        class Paused(Exception):
            pass
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            outputs = [root / "one.mp3", root / "two.mp3"]
            def worker(_path, request, _video_id, callback):
                self.assertEqual(request["inference_steps"], 16)
                Path(request["items"][0]["wav_path"]).write_bytes(b"RIFF" + bytes(256))
                callback(1, 2, "synthesizing")
                self.assertTrue(tts._is_valid_mp3(str(outputs[0])))
                raise Paused()
            with (mock.patch.object(omnivoice_tts, "_prepare_isolated_runtime"),
                  mock.patch.object(omnivoice_tts, "verify_omnivoice_model", return_value=root),
                  mock.patch.object(omnivoice_tts, "_sdk_root", return_value=root),
                  mock.patch.object(omnivoice_tts, "_run_worker_process", side_effect=worker),
                  mock.patch.object(omnivoice_tts, "_encode_mp3", side_effect=lambda _wav, output, _id: _write_test_mp3(str(output))),
                  mock.patch.object(omnivoice_tts, "log_to_video")):
                with self.assertRaises(Paused):
                    omnivoice_tts.synthesize_batch_to_mp3(
                        [{"text": "One", "voice": "omnivoice:male", "output_path": str(outputs[0])},
                         {"text": "Two", "voice": "omnivoice:male", "output_path": str(outputs[1])}],
                        "fixture-video", language_id="en", device="cpu",
                    )
            self.assertTrue(tts._is_valid_mp3(str(outputs[0])))
            self.assertFalse(outputs[1].exists())

    def test_legacy_provider_aliases_migrate_to_omnivoice(self):
        self.assertEqual(tts.resolve_tts_provider("auto", "vi"), "omnivoice")
        self.assertEqual(tts.resolve_tts_provider("vieneu", "en"), "omnivoice")
        self.assertEqual(tts.resolve_tts_provider("edge", "vi"), "omnivoice")
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

    def test_omnivoice_loads_once_for_all_missing_segments(self):
        from haizflow.pipeline import omnivoice_tts

        calls = []

        def synthesize_batch(items, video_id, *, language_id, speaker_mode="single", progress_callback=None, device="cpu"):
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

    def test_omnivoice_server_reuses_one_runtime_across_requests(self):
        from haizflow.pipeline import omnivoice_tts

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            requests = []
            request_paths = []
            for index in range(2):
                request_path = root / f"request-{index}.json"
                response_path = root / f"response-{index}.json"
                request_path.write_text(
                    json.dumps({"response_path": str(response_path)}),
                    encoding="utf-8",
                )
                request_paths.append(request_path)

            def fake_worker(request_path, runtime):
                requests.append((request_path, runtime))
                return 0

            commands = "\n".join(str(path) for path in request_paths) + "\n__quit__\n"
            with (
                mock.patch.object(omnivoice_tts.sys, "stdin", io.StringIO(commands)),
                mock.patch.object(omnivoice_tts, "_worker_main", side_effect=fake_worker),
            ):
                self.assertEqual(omnivoice_tts._worker_server_main(), 0)

            self.assertEqual(len(requests), 2)
            self.assertIs(requests[0][1], requests[1][1])
            for index in range(2):
                response = json.loads((root / f"response-{index}.json").read_text(encoding="utf-8"))
                self.assertEqual(response, {"return_code": 0, "error": ""})

    def test_omnivoice_multiple_speakers_follow_source_timestamps_not_list_indexes(self):
        from haizflow.pipeline import omnivoice_tts

        calls = []

        def synthesize_batch(items, video_id, *, language_id, speaker_mode="single", progress_callback=None, device="cpu"):
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
                mock.patch("haizflow.pipeline.speaker_identity.prepare_speakers", side_effect=lambda audio, segments, *args: [
                    {**item, "speaker_id": f"speaker-{i}", "speaker_voice": "omnivoice:male" if i else "omnivoice:female"}
                    for i, item in enumerate(segments)]),
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
        self.assertEqual([item["voice"] for item in items], ["omnivoice:male", "omnivoice:female"])
        self.assertTrue(all(not item["source_audio_path"] for item in items))

    def test_omnivoice_cuda_engine_failure_triggers_cpu_fallback(self):
        from haizflow.pipeline.omnivoice_tts import _is_cuda_resource_failure

        self.assertTrue(
            _is_cuda_resource_failure(
                "RuntimeError: GET was unable to find an engine to execute this computation"
            )
        )

    def test_omnivoice_retries_in_isolated_worker_when_warm_channel_exits(self):
        from haizflow.pipeline import omnivoice_tts

        calls = []
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "voice.mp3"

            def failed_warm(_request_path, _request, _video_id, _progress_callback, **_kwargs):
                calls.append("warm")
                return 1, "Warm OmniVoice worker exited unexpectedly (1)."

            def successful_isolated(_request_path, request, _video_id, _progress_callback):
                calls.append("isolated")
                for item in request["items"]:
                    Path(item["wav_path"]).write_bytes(b"RIFF" + b"\x00" * 256)
                return 0, ""

            def encode(_wav_path, output_path, _video_id):
                _write_test_mp3(str(output_path))

            with (
                mock.patch.object(omnivoice_tts, "_prepare_isolated_runtime"),
                mock.patch.object(omnivoice_tts, "verify_omnivoice_model", return_value=root),
                mock.patch.object(omnivoice_tts, "_sdk_root", return_value=root),
                mock.patch.object(omnivoice_tts, "processing_device_preference", return_value="cpu"),
                mock.patch.object(omnivoice_tts, "_run_persistent_worker_process", side_effect=failed_warm),
                mock.patch.object(omnivoice_tts, "_run_worker_process", side_effect=successful_isolated),
                mock.patch.object(omnivoice_tts, "_encode_mp3", side_effect=encode),
                mock.patch.object(omnivoice_tts, "log_to_video") as log,
            ):
                omnivoice_tts.synthesize_batch_to_mp3(
                    [{"text": "Câu vừa chỉnh", "voice": "omnivoice:bright", "output_path": str(output)}],
                    "manual-video",
                    language_id="vi",
                    keep_worker_warm=True,
                )

            self.assertEqual(calls, ["warm", "isolated"])
            self.assertTrue(tts._is_valid_mp3(str(output)))
            self.assertTrue(any("isolated worker" in str(call) for call in log.call_args_list))

    def test_omnivoice_source_worker_can_import_package_without_parent_pythonpath(self):
        from haizflow.pipeline import omnivoice_tts

        with (
            mock.patch.dict(omnivoice_tts.os.environ, {}, clear=True),
            mock.patch.object(omnivoice_tts.sys, "frozen", False, create=True),
        ):
            environment = omnivoice_tts._worker_environment()

        paths = [Path(value).resolve() for value in environment["PYTHONPATH"].split(omnivoice_tts.os.pathsep)]
        self.assertIn(SRC.resolve(), paths)
        self.assertEqual(environment["PYTHONUTF8"], "1")
        self.assertEqual(environment["HF_HUB_OFFLINE"], "1")
        self.assertEqual(environment["OMP_NUM_THREADS"], "1")
        self.assertEqual(environment["MKL_NUM_THREADS"], "1")

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

    def test_omnivoice_latency_diagnostics_accept_only_bounded_numeric_fields(self):
        from haizflow.pipeline.omnivoice_tts import _timing_detail

        self.assertEqual(_timing_detail({}), "")
        self.assertEqual(_timing_detail({"timing_seconds": {"model_load": 12.345}}), " model_load=12.35s")
        self.assertEqual(_timing_detail({"timing_seconds": {
            "model_load": "not a duration", "runtime_imports": float("inf"),
            "reference_encoding": -1, "synthesis": float("nan"),
        }}), "")

    def test_source_reference_bounds_support_chinese_without_spaces(self):
        from haizflow.pipeline.omnivoice_tts import _usable_source_reference

        self.assertTrue(_usable_source_reference(1, 5, "我们现在可以开始了。"))
        self.assertTrue(_usable_source_reference(1, 5, "Now we can begin."))
        self.assertFalse(_usable_source_reference(1, 2.2, "Now we can begin."))
        self.assertFalse(_usable_source_reference(1, 5, "Go!"))
        self.assertFalse(_usable_source_reference(1, 20, "Now we can begin."))

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

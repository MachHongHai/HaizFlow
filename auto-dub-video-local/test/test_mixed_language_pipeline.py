import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autodub.pipeline import transcribe
from autodub.schemas.job import JobConfig
from autodub.services import hymt2_worker, job_store, translation
from autodub.services.hymt2_worker import (
    _build_prompt,
    _build_translation_prompts,
    _clean_single_translation,
    _context_after_end,
    _context_before_start,
    _context_indices,
    _inference_batches,
)


class _LanguageModel:
    def __init__(self, languages):
        self.languages = iter(languages)
        self.clip_lengths = []

    def detect_language(self, **kwargs):
        self.clip_lengths.append(len(kwargs["audio"]))
        language, confidence = next(self.languages)
        return language, confidence, [(language, confidence)]


class _AsrModel:
    def __init__(self, languages):
        self.model = _LanguageModel(languages)


class MixedLanguagePipelineTests(unittest.TestCase):
    def test_segment_language_detection_and_alignment_mapping(self):
        original_log = transcribe.log_to_job
        transcribe.log_to_job = lambda *_args, **_kwargs: None
        try:
            segments = [
                {"start": 0.0, "end": 1.0, "text": "Hello"},
                {"start": 2.0, "end": 3.5, "text": "Xin chao"},
            ]
            model = _AsrModel([("en", 0.98), ("vi", 0.92)])
            detected = transcribe._detect_segment_languages(
                model,
                np.zeros(16_000 * 5, dtype=np.float32),
                segments,
                "en",
                "test-job",
            )
        finally:
            transcribe.log_to_job = original_log

        self.assertEqual([segment["language"] for segment in detected], ["en", "vi"])
        self.assertEqual(model.model.clip_lengths, [16_000, 24_000])
        language, confidence = transcribe._language_for_aligned_segment(
            {"start": 2.1, "end": 3.2}, detected, "en"
        )
        self.assertEqual(language, "vi")
        self.assertEqual(confidence, 0.92)

    def test_translation_uses_the_language_from_each_segment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "source.json"
            output_path = Path(temp_dir) / "translated.json"
            input_path.write_text(
                json.dumps(
                    [
                        {"start": 0, "end": 1, "text": "Hello", "language": "en"},
                        {"start": 1, "end": 2, "text": "Xin chao", "language": "vi"},
                    ]
                ),
                encoding="utf-8",
            )
            captured = {}
            original_worker = translation._translate_with_hymt2_worker
            original_log = translation.log_to_job
            translation._translate_with_hymt2_worker = lambda texts, **kwargs: captured.update(kwargs) or ["Bonjour", "Hello"]
            translation.log_to_job = lambda *_args, **_kwargs: None
            try:
                translated = translation.translate_segments(
                    str(input_path), str(output_path), "test-job", target_language="fr", source_language="en"
                )
            finally:
                translation._translate_with_hymt2_worker = original_worker
                translation.log_to_job = original_log

        self.assertEqual(captured["source_languages"], ["English", "Vietnamese"])
        self.assertEqual([segment["source_language"] for segment in translated], ["en", "vi"])

    def test_alignment_uses_a_model_per_detected_language(self):
        loaded_languages = []
        original_load = transcribe.whisperx.load_align_model
        original_align = transcribe.whisperx.align
        original_log = transcribe.log_to_job
        transcribe.whisperx.load_align_model = lambda language_code, device: (loaded_languages.append(language_code) or object(), {})
        transcribe.whisperx.align = lambda segments, *_args, **_kwargs: {"segments": segments}
        transcribe.log_to_job = lambda *_args, **_kwargs: None
        try:
            aligned = transcribe._align_segments_by_language(
                np.zeros(16_000 * 4, dtype=np.float32),
                [
                    {"start": 2, "end": 3, "text": "Konnichiwa", "language": "ja"},
                    {"start": 0, "end": 1, "text": "Hello", "language": "en"},
                ],
                "cpu",
                "test-job",
            )
        finally:
            transcribe.whisperx.load_align_model = original_load
            transcribe.whisperx.align = original_align
            transcribe.log_to_job = original_log

        self.assertEqual(loaded_languages, ["ja", "en"])
        self.assertEqual([segment["text"] for segment in aligned], ["Hello", "Konnichiwa"])

    def test_hymt2_prompt_batches_preserve_order_and_context(self):
        texts = ["Hello", "How are you?", "Fine.", "Thanks", "Bye"]
        self.assertEqual(list(_inference_batches(texts, batch_size=4)), [(0, 4), (4, 5)])
        self.assertEqual(_context_before_start(["A" * 1300, "B"], 2), 1)
        self.assertEqual(_context_after_end(["A", "B" * 1300], 1), 1)

        prompt = _build_prompt(
            ["Hello", "How are you?", "Fine."],
            ["English", "English", "English"],
            1,
            "Vietnamese",
        )
        self.assertIn("[Background Information]", prompt)
        self.assertIn("reference only and is not text to translate", prompt)
        self.assertIn("- [English] Hello", prompt)
        self.assertIn("- [English] Fine.", prompt)
        self.assertIn("[Source Text]\nHow are you?", prompt)
        self.assertIn(
            "Please translate only the following [Source Text] into Vietnamese",
            prompt,
        )
        self.assertIn("ONLY output the translated result", prompt)
        self.assertNotIn("JSON", prompt)

        prompts = _build_translation_prompts(
            texts,
            ["English"] * len(texts),
            0,
            4,
            "Vietnamese",
        )
        self.assertEqual(len(prompts), 4)
        self.assertIn("[Source Text]\nHello", prompts[0])
        self.assertIn("[Source Text]\nThanks", prompts[3])

        focused_prompt = _build_prompt(
            ["Earlier context", "Honey details", "Top 20%.", "Banana details", "Top 10%.", "Later context"],
            ["English"] * 6,
            3,
            "Vietnamese",
        )
        self.assertIn("- [English] Honey details", focused_prompt)
        self.assertIn("- [English] Top 20%.", focused_prompt)
        self.assertNotIn("Top 10%.", focused_prompt)
        self.assertNotIn("Later context", focused_prompt)
        self.assertLess(focused_prompt.index("[Background Information]"), focused_prompt.rindex("[Source Text]\nBanana details"))

        wide_prompt = _build_prompt(
            [f"Line {number}" for number in range(9)],
            ["English"] * 9,
            4,
            "Vietnamese",
        )
        for number in (0, 1, 2):
            self.assertIn(f"Line {number}", wide_prompt)
        for number in (3, 5, 6, 7, 8):
            self.assertNotIn(f"Line {number}", wide_prompt)

        long_texts = [f"Line {number} " + ("A" * 450) for number in range(20)]
        long_context_indices = _context_indices(long_texts, 10)
        self.assertIn(0, long_context_indices)
        self.assertIn(9, long_context_indices)
        self.assertNotIn(11, long_context_indices)
        self.assertNotIn(19, long_context_indices)
        self.assertLessEqual(
            sum(len(long_texts[context_index]) for context_index in long_context_indices),
            2400,
        )

        mixed_prompt = _build_prompt(
            ["Hello", "今日は特別なメニューがあります。", "¿Puedes hacerlo sin gluten?"],
            ["English", "Japanese", "Spanish"],
            1,
            "Vietnamese",
        )
        self.assertIn("Source language: Japanese", mixed_prompt)
        self.assertIn("- [English] Hello", mixed_prompt)
        self.assertIn("- [Spanish] ¿Puedes hacerlo sin gluten?", mixed_prompt)

        shake_texts = [
            "If you only drink a protein shake after training, you are in the top 50%.",
            "Add creatine for strength and recovery.",
            "Add honey to deliver nutrients faster.",
            "Add a banana to replenish glycogen.",
            "Top 10%.",
            "No gas in, no underfueling, just a shake that actually works.",
        ]
        shake_prompt = _build_prompt(
            shake_texts,
            ["English"] * len(shake_texts),
            len(shake_texts) - 1,
            "Vietnamese",
        )
        self.assertIn("- [English] If you only drink a protein shake", shake_prompt)
        self.assertIn("[Source Text]\nNo gas in, no underfueling, just a shake", shake_prompt)

        fruit_texts = [
            "for fat loss.",
            "S tier, elite for fat loss.",
            "Easy to digest, high in fiber, low calorie and great for cravings.",
            "Dry fruit.",
            "F tier, basically fruit with the water removed.",
            "Tiny portion, high calorie density, easy to destroy your deficit without noticing.",
        ]
        fruit_prompt = _build_prompt(
            fruit_texts,
            ["English"] * len(fruit_texts),
            4,
            "Vietnamese",
        )
        self.assertIn("[Source Text]\nF tier, basically fruit with the water removed.", fruit_prompt)
        self.assertNotIn("Tiny portion", fruit_prompt)
        self.assertNotIn("N1", fruit_prompt)

        kiwi_prompt = _build_prompt(
            fruit_texts + ["Mango.", "C tier.", "Easy to overeat.", "Kiwi."],
            ["English"] * 10,
            9,
            "Vietnamese",
        )
        self.assertIn("[Source Text]\nKiwi.", kiwi_prompt)
        self.assertIn("standalone label", kiwi_prompt)
        self.assertIn("more specific subtype", kiwi_prompt)
        self.assertNotIn("Mango.", kiwi_prompt)
        self.assertNotIn("Easy to overeat.", kiwi_prompt)

        default_prompt = _build_prompt(
            ["Hello"],
            ["English"],
            0,
            "Vietnamese",
            include_context=False,
        )
        self.assertEqual(
            default_prompt,
            "Translate the following text into Vietnamese. Note that you should only output "
            "the translated result without any additional explanation:\n\nHello",
        )

    def test_hymt2_mixed_language_batch_keeps_target_language_segments(self):
        captured_source_texts = []
        original_runtime = hymt2_worker._model_runtime
        original_runtime_profile = hymt2_worker.runtime_profile
        original_translate_batch = hymt2_worker._translate_prompt_batch
        original_emit = hymt2_worker._emit_event
        hymt2_worker._model_runtime = lambda: (object(), object(), object(), "cpu")
        hymt2_worker.runtime_profile = lambda: SimpleNamespace(is_cpu_only=False)
        hymt2_worker._translate_prompt_batch = (
            lambda _model, _tokenizer, _torch, _device, _prompts, source_texts: (
                captured_source_texts.extend(source_texts) or ["Xin chào", "Không gluten"]
            )
        )
        hymt2_worker._emit_event = lambda _payload: None
        try:
            translated = hymt2_worker.translate(
                {
                    "texts": ["Hello", "Đã sẵn sàng", "Sin gluten"],
                    "source_languages": ["English", "Vietnamese", "Spanish"],
                    "target_language_name": "Vietnamese",
                }
            )
        finally:
            hymt2_worker._model_runtime = original_runtime
            hymt2_worker.runtime_profile = original_runtime_profile
            hymt2_worker._translate_prompt_batch = original_translate_batch
            hymt2_worker._emit_event = original_emit

        self.assertEqual(captured_source_texts, ["Hello", "Sin gluten"])
        self.assertEqual(translated, ["Xin chào", "Đã sẵn sàng", "Không gluten"])

    def test_hymt2_worker_writes_response_and_progress_sidecar(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            request_path = Path(temp_dir) / "request.json"
            response_path = Path(temp_dir) / "response.json"
            progress_path = Path(temp_dir) / "progress.jsonl"
            request_path.write_text(
                json.dumps(
                    {
                        "texts": ["Hello"],
                        "source_languages": ["English"],
                        "target_language_name": "Vietnamese",
                    }
                ),
                encoding="utf-8",
            )
            original_translate = hymt2_worker.translate
            hymt2_worker.translate = lambda _payload: ["Xin chao"]
            try:
                exit_code = hymt2_worker.main(
                    [
                        "--request",
                        str(request_path),
                        "--response",
                        str(response_path),
                        "--progress",
                        str(progress_path),
                    ]
                )
            finally:
                hymt2_worker.translate = original_translate

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(response_path.read_text(encoding="utf-8")), {"translations": ["Xin chao"]})
            self.assertTrue(progress_path.is_file())

    def test_hymt2_single_fallback_accepts_plain_and_json_text(self):
        self.assertEqual(_clean_single_translation("Xin chao"), "Xin chao")
        self.assertEqual(_clean_single_translation('"Xin chao"'), "Xin chao")
        self.assertEqual(_clean_single_translation('["Xin chao"]'), "Xin chao")

    def test_hymt2_server_protocol_starts_and_stops_without_loading_the_model(self):
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(SRC) + os.pathsep + environment.get("PYTHONPATH", "")
        process = subprocess.Popen(
            [sys.executable, "-m", "autodub.services.hymt2_worker", "--server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=environment,
        )
        try:
            assert process.stdin is not None
            assert process.stdout is not None
            process.stdin.write('{"request_id":"ping-1","command":"ping"}\n')
            process.stdin.flush()
            self.assertEqual(json.loads(process.stdout.readline()), {"event": "response", "request_id": "ping-1", "ready": True})
            process.stdin.write('{"request_id":"stop-1","command":"shutdown"}\n')
            process.stdin.flush()
            self.assertEqual(json.loads(process.stdout.readline()), {"event": "response", "request_id": "stop-1", "stopped": True})
            process.stdin.close()
            self.assertEqual(process.wait(timeout=5), 0)
        finally:
            if process.poll() is None:
                process.kill()
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()

    def test_job_store_serializes_concurrent_updates_and_recovers_backup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            original_jobs_dir = job_store.JOBS_DIR
            job_store.JOBS_DIR = temp_dir
            try:
                job = job_store.create_job("job-store-test", "input.mp4", JobConfig())
                failures = []

                def update_progress(offset):
                    try:
                        for value in range(offset, 100, 10):
                            job_store.update_job(job.job_id, progress=value, step="processing")
                            self.assertIsNotNone(job_store.get_job(job.job_id))
                    except Exception as exc:  # pragma: no cover - assertion is reported below.
                        failures.append(exc)

                threads = [threading.Thread(target=update_progress, args=(offset,)) for offset in range(5)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()

                self.assertEqual(failures, [])
                path = Path(job_store.get_job_json_path(job.job_id))
                self.assertIsNotNone(job_store.get_job(job.job_id))
                self.assertTrue(Path(str(path) + ".bak").exists())

                path.write_text("{", encoding="utf-8")
                recovered = job_store.get_job(job.job_id)
                self.assertIsNotNone(recovered)
                self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["job_id"], job.job_id)
            finally:
                job_store.JOBS_DIR = original_jobs_dir


if __name__ == "__main__":
    unittest.main()

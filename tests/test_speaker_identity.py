"""Speaker regression fixtures are synthetic and never require user media."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from haizflow.pipeline import speaker_identity as identity


class SpeakerIdentityTests(unittest.TestCase):
    def test_conflicting_voice_for_one_speaker_is_rejected(self):
        segments = [{"start": i, "end": i + 1, "text": "Neutral."} for i in range(2)]
        mapped = [{**item, "speaker_id": "speaker-1", "speaker_voice": voice}
                  for item, voice in zip(segments, ["omnivoice:male", "omnivoice:female"])]
        self.assertFalse(identity._valid_map(mapped, segments))
        mapped[1]["speaker_voice"] = "omnivoice:male"
        self.assertTrue(identity._valid_map(mapped, segments))

    def test_reliable_anchors_keep_their_cluster_identity(self):
        vectors = np.array([[1, 0], [.7, .7], [.9, .1]], dtype=np.float32)
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        labels, scores = identity._assign_identities(vectors, [0, 1], [0, 1])
        self.assertEqual(labels[:2], [0, 1])
        self.assertEqual(labels[2], 0)
        self.assertEqual(scores.shape, (3, 2))
        self.assertTrue(np.isfinite(scores).all())

    def test_clone_and_multiple_modes_are_not_silently_combined(self):
        from types import SimpleNamespace
        from haizflow.pipeline import tts

        with tempfile.TemporaryDirectory() as directory:
            transcript = Path(directory) / "translated.json"
            transcript.write_text(json.dumps([{"text": "Một câu thoại trung lập."}]), encoding="utf-8")
            with (
                patch.object(tts, "get_video", return_value=SimpleNamespace(speaker_mode="multiple", files={})),
                patch.object(tts, "log_to_video"),
            ):
                with self.assertRaisesRegex(ValueError, "không dùng cả hai"):
                    tts.generate_voice_parts(
                        str(transcript), str(Path(directory) / "voice"), "omnivoice:clone", "fixture"
                    )

    def test_complete_link_separates_speakers_without_modifying_embeddings(self):
        embeddings = np.array([[1, 0, 0], [0.98, 0.03, 0], [0, 1, 0], [0, 0.98, 0.03]], dtype=np.float32)
        original = embeddings.copy()
        self.assertEqual(identity._cluster(embeddings), [0, 0, 1, 1])
        np.testing.assert_array_equal(embeddings, original)
        self.assertEqual(identity._cluster([]), [])

    def test_chaining_does_not_merge_unrelated_speakers(self):
        # A/B and B/C are similar, but A/C are not the same identity.
        embeddings = [[1, 0], [0.7, 0.7], [0, 1]]
        labels = identity._cluster(embeddings, threshold=0.6)
        self.assertNotEqual(labels[0], labels[2])

    def test_invalid_embedding_is_rejected(self):
        with self.assertRaises(ValueError):
            identity._cluster([[float("nan"), 1]])

    def test_filterbank_shape_and_mean_normalization(self):
        audio = 1000 * np.sin(2 * np.pi * 220 * np.arange(16000) / 16000)
        features = identity._features(audio)
        self.assertEqual(features.shape, (98, 80))
        self.assertTrue(np.isfinite(features).all())
        np.testing.assert_allclose(features.mean(axis=0), 0, atol=2e-5)

    def test_identity_map_cache_reuses_source_but_invalidates_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "speech.wav"
            audio.write_bytes(b"synthetic audio fixture")
            segments = [{"start": 0.0, "end": 2.0, "text": "A neutral sentence."}]

            def engine(_capability, _operation, payload, *_args, **_kwargs):
                return {
                    "segments": [
                        {**item, "speaker_id": "speaker-1", "speaker_voice": "omnivoice:male"}
                        for item in payload["segments"]
                    ]
                }

            pool = Mock()
            with (
                patch.object(identity, "verify_model"),
                patch("haizflow.services.external_tasks.run_external_task", side_effect=engine) as task,
                patch("haizflow.services.external_engine.shared_external_engine_pool", return_value=pool),
            ):
                first = identity.prepare_speakers(str(audio), segments, "fixture")
                self.assertEqual(identity.prepare_speakers(str(audio), segments, "fixture"), first)
                self.assertEqual(task.call_count, 1)
                edited = [{**segments[0], "end": 1.5}]
                identity.prepare_speakers(str(audio), edited, "fixture")
                self.assertEqual(task.call_count, 2)
                self.assertEqual(len(list(Path(directory).glob("speaker-map-*.json"))), 2)
                for cache in Path(directory).glob("speaker-map-*.json"):
                    self.assertIsInstance(json.loads(cache.read_text(encoding="utf-8")), list)
            pool.release.assert_called_with({"speaker"})

    def test_invalid_engine_result_never_enters_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "speech.wav"
            audio.write_bytes(b"fixture")
            with (
                patch.object(identity, "verify_model"),
                patch("haizflow.services.external_tasks.run_external_task", return_value={"segments": []}),
                patch("haizflow.services.external_engine.shared_external_engine_pool") as pool,
            ):
                with self.assertRaisesRegex(RuntimeError, "invalid identity map"):
                    identity.prepare_speakers(str(audio), [{"start": 0, "end": 2, "text": "hello"}], "fixture")
            pool.return_value.release.assert_called_once_with({"speaker"})
            self.assertFalse(list(Path(directory).glob("speaker-map-*.json")))

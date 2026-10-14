"""Speaker regression fixtures are synthetic and never require user media."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from hflow.pipeline import speaker_identity as identity


class SpeakerIdentityTests(unittest.TestCase):
    def test_pitch_keeps_male_fundamental_with_a_stronger_second_harmonic(self):
        time = np.arange(16000) / 16000
        audio = 2000 * (0.35 * np.sin(2 * np.pi * 120 * time) + np.sin(2 * np.pi * 240 * time))
        samples = identity._pitch_samples(audio)
        self.assertGreater(len(samples), 8)
        self.assertAlmostEqual(float(np.median(samples)), 120, delta=2)
        self.assertEqual(identity._voice_pitch_profile(samples)[0], "male")

    def test_clear_female_register_is_retained(self):
        audio = 2000 * np.sin(2 * np.pi * 260 * np.arange(32000) / 16000)
        samples = identity._pitch_samples(audio)
        self.assertAlmostEqual(float(np.median(samples)), 260, delta=2)
        self.assertEqual(identity._voice_pitch_profile(samples)[:2], ("female", False))

    def test_shouting_does_not_replace_the_habitual_register(self):
        kind, uncertain, _ = identity._voice_pitch_profile([140] * 30 + [240] * 70)
        self.assertEqual(kind, "male")
        self.assertTrue(uncertain)

    def test_sustained_quiet_register_survives_majority_shouted_frames(self):
        turns = [[330] * 30, [350] * 30, [120, 125, 118, 122, 119, 121, 123, 124] + [320] * 20]
        self.assertEqual(identity._voice_pitch_profile([v for turn in turns for v in turn])[0], "female")
        kind, uncertain, _ = identity._speaker_voice_profile(turns)
        self.assertEqual(kind, "male")
        self.assertTrue(uncertain)

    def test_female_profile_and_isolated_subharmonics_are_not_overridden(self):
        self.assertEqual(identity._speaker_voice_profile([[260] * 40, [280] * 30])[:2], ("female", False))
        self.assertEqual(identity._speaker_voice_profile([[260] * 40 + [120] * 7])[0], "female")
        self.assertEqual(identity._speaker_voice_profile([[260] * 40 + [120, 260] * 6])[0], "female")

    def test_low_register_evidence_does_not_cross_turn_or_invalid_boundaries(self):
        turns = [[260] * 30 + [120] * 4, [120] * 4 + [260] * 30]
        self.assertEqual(identity._speaker_voice_profile(turns)[0], "female")
        self.assertEqual(identity._speaker_voice_profile([[260] * 40 + [120] * 4 + [float("nan")] * 4 + [120] * 4])[0], "female")

    def test_normal_unvoiced_consonant_gaps_are_allowed_but_pitch_order_is_kept(self):
        quiet = [120, 125, float("nan"), 122, 118, float("nan"), 119, 123, 121, 124]
        self.assertEqual(identity._speaker_voice_profile([[340] * 80, quiet])[0], "male")
        time = np.arange(16000) / 16000
        audio = 2000 * np.sin(2 * np.pi * 120 * time)
        audio[5000:11000] = 0
        frames = identity._pitch_samples(audio, preserve_gaps=True)
        self.assertTrue(np.lib.stride_tricks.sliding_window_view(~np.isfinite(frames), 4).all(axis=1).any())
        self.assertTrue(np.isfinite(identity._pitch_samples(audio)).all())

    def test_reconciliation_does_not_reassign_established_short_turns(self):
        vectors = np.eye(4, dtype=np.float32)
        segments = [{"start": i * 3, "end": i * 3 + 2} for i in range(4)]
        reconciled = [0, 0, 1, 1]
        with (patch.object(identity, "_cluster", return_value=[0, 1, 2, 2]),
              patch.object(identity, "_reconcile_expressive_groups", return_value=reconciled),
              patch.object(identity, "_assign_identities", side_effect=[([0, 1, 2, 2], np.zeros((4, 3))),
                                                                       ([0, 0, 0, 0], np.zeros((4, 2)))])):
            labels, scores = identity._label_turns(vectors, list(range(4)), segments)
        self.assertEqual(labels, reconciled)
        self.assertEqual(scores.shape, (4, 2))

    def test_expressive_groups_need_independent_support_on_both_sides(self):
        vectors = np.array([[1, 0, 0], [.99, .01, 0], [.77, .64, 0], [.76, .65, 0], [0, 0, 1]], dtype=np.float32)
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        labels = identity._reconcile_expressive_groups(vectors, [0, 0, 1, 1, 2])
        self.assertEqual(labels, [0, 0, 0, 0, 1])
        self.assertEqual(identity._reconcile_expressive_groups(vectors[[0, 2, 4]], [0, 1, 2]), [0, 1, 2])

    def test_one_similar_exemplar_cannot_merge_unrelated_speakers(self):
        vectors = np.array([[1, 0], [1, 0], [1, 0], [0, 1]], dtype=np.float32)
        self.assertEqual(identity._reconcile_expressive_groups(vectors, [0, 0, 1, 1]), [0, 0, 1, 1])

    def test_ambiguous_competing_groups_are_not_merged(self):
        angles = np.deg2rad([0, 0, 30, 30, 60, 60])
        vectors = np.column_stack([np.cos(angles), np.sin(angles)]).astype(np.float32)
        self.assertEqual(identity._reconcile_expressive_groups(vectors, [0, 0, 1, 1, 2, 2]), [0, 0, 1, 1, 2, 2])

    def test_expressive_reconciliation_is_bounded_and_deterministic(self):
        vectors = np.tile([[1, 0], [.77, .64]], (1000, 1)).astype(np.float32)
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        labels = [i % 2 for i in range(len(vectors))]
        first = identity._reconcile_expressive_groups(vectors, labels)
        self.assertEqual(first, [0] * len(vectors))
        self.assertEqual(identity._reconcile_expressive_groups(vectors, labels), first)

    def test_noise_silence_and_unknown_pitch_are_not_confident_gender_evidence(self):
        self.assertEqual(identity._pitch_samples(np.zeros(16000)), [])
        self.assertEqual(identity._pitch_samples(np.full(16000, np.nan)), [])
        self.assertEqual(identity._pitch_samples(np.random.default_rng(7).normal(0, 2000, 16000)), [])
        self.assertEqual(identity._voice_pitch_profile([])[:2], ("male", True))
        self.assertTrue(identity._voice_pitch_profile([180] * 30)[1])

    def test_short_only_dialogue_is_not_forced_to_one_person(self):
        vectors = np.array([[1, 0], [0, 1], [.99, .02], [.01, .99]], dtype=np.float32)
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        segments = [{"start": i, "end": i + .9} for i in range(4)]
        labels, _scores = identity._label_turns(vectors, list(range(4)), segments)
        self.assertEqual(labels, [0, 1, 0, 1])

    def test_short_turns_match_existing_reliable_speakers(self):
        vectors = np.array([[1, 0], [0, 1], [.99, .02]], dtype=np.float32)
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        segments = [{"start": 0, "end": 3}, {"start": 3, "end": 6}, {"start": 6, "end": 6.7}]
        labels, _scores = identity._label_turns(vectors, list(range(3)), segments)
        self.assertEqual(labels, [0, 1, 0])

    def test_male_source_profile_reaches_tts_despite_default_female_preset(self):
        from types import SimpleNamespace
        from hflow.pipeline import tts

        kind, uncertain, pitch = identity._voice_pitch_profile([120] * 30 + [240] * 50)
        self.assertEqual(kind, "male")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            segments = [{"start": 11.184, "end": 12.744, "text": "A translated line."}]
            transcript = root / "translated.json"
            transcript.write_text(json.dumps(segments), encoding="utf-8")
            audio = root / "source.wav"
            audio.touch()
            mapped = [{**segments[0], "speaker_id": "speaker-3", "speaker_voice": "omnivoice:male",
                       "speaker_pitch_hz": pitch, "speaker_voice_uncertain": uncertain}]
            video = SimpleNamespace(speaker_mode="multiple", files={"source_segments": str(transcript),
                                                                      "speech_audio": str(audio)})
            def synthesize(items, *_args, **_kwargs):
                for item in items:
                    Path(item["output_path"]).write_bytes(b"ID3" + bytes(600))
            with (patch.object(tts, "get_video", return_value=video), patch.object(tts, "log_to_video"),
                  patch.object(identity, "prepare_speakers", return_value=mapped),
                  patch("hflow.pipeline.omnivoice_tts.synthesize_batch_to_mp3", side_effect=synthesize) as worker):
                tts.generate_voice_parts(str(transcript), str(root / "parts"), "omnivoice:female", "fixture")
            self.assertEqual(worker.call_args.args[0][0]["voice"], "omnivoice:male")

    def test_multiple_speaker_logs_match_voices_sent_to_worker(self):
        from types import SimpleNamespace
        from hflow.pipeline import tts

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            segments = [{"start": i * 3, "end": i * 3 + 3, "text": "A sentence."} for i in range(2)]
            transcript = root / "translated.json"
            source = root / "source.json"
            for path in (transcript, source):
                path.write_text(json.dumps(segments), encoding="utf-8")
            audio = root / "audio.wav"
            audio.touch()
            mapped = [{**item, "speaker_id": f"speaker-{i + 1}", "speaker_voice": voice}
                      for i, (item, voice) in enumerate(zip(segments, ["omnivoice:male", "omnivoice:female"]))]
            video = SimpleNamespace(speaker_mode="multiple", files={"source_segments": str(source),
                                    "speech_audio": str(audio)})
            def synthesize(items, *_args, **_kwargs):
                for item in items:
                    Path(item["output_path"]).write_bytes(b"ID3" + bytes(600))
            with patch.object(tts, "get_video", return_value=video), patch.object(tts, "log_to_video") as log, \
                 patch.object(identity, "prepare_speakers", return_value=mapped), \
                 patch("hflow.pipeline.omnivoice_tts.synthesize_batch_to_mp3", side_effect=synthesize) as worker:
                tts.generate_voice_parts(str(transcript), str(root / "parts"), "omnivoice:female", "fixture")
            self.assertEqual([item["voice"] for item in worker.call_args.args[0]],
                             ["omnivoice:male", "omnivoice:female"])
            messages = [call.args[1] for call in log.call_args_list]
            session = next(message for message in messages if "SESSION_START" in message)
            self.assertIn("speaker_mode=multiple voice=per-speaker", session)
            queued = [message for message in messages if "QUEUED" in message]
            self.assertIn("voice=omnivoice:male speaker=speaker-1", queued[0])
            self.assertIn("voice=omnivoice:female speaker=speaker-2", queued[1])

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
        from hflow.pipeline import tts

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
                patch("hflow.services.external_tasks.run_external_task", side_effect=engine) as task,
                patch("hflow.services.external_engine.shared_external_engine_pool", return_value=pool),
            ):
                first = identity.prepare_speakers(str(audio), segments, "fixture")
                self.assertEqual(identity.prepare_speakers(str(audio), segments, "fixture"), first)
                self.assertEqual(task.call_count, 1)
                edited = [{**segments[0], "end": 1.5}]
                identity.prepare_speakers(str(audio), edited, "fixture")
                self.assertEqual(task.call_count, 2)
                self.assertEqual(task.call_args.kwargs["context"]["device"],
                                 task.call_args.args[2]["device"])
                self.assertEqual(task.call_args.args[2]["device"], "cpu")
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
                patch("hflow.services.external_tasks.run_external_task", return_value={"segments": []}),
                patch("hflow.services.external_engine.shared_external_engine_pool") as pool,
            ):
                with self.assertRaisesRegex(RuntimeError, "invalid identity map"):
                    identity.prepare_speakers(str(audio), [{"start": 0, "end": 2, "text": "hello"}], "fixture")
            pool.return_value.release.assert_called_once_with({"speaker"})
            self.assertFalse(list(Path(directory).glob("speaker-map-*.json")))

    def test_new_policy_recomputes_old_maps_then_reuses_unchanged_source_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "speech.wav"
            audio.write_bytes(b"unchanged source audio")
            segments = [{"start": 55.0, "end": 56.2, "text": "Source speech."}]
            def engine(_capability, _operation, payload, *_args, **_kwargs):
                return {"segments": [{**item, "speaker_id": "speaker-1", "speaker_voice": "omnivoice:male"}
                                     for item in payload["segments"]]}
            with (patch.object(identity, "verify_model"),
                  patch("hflow.services.external_tasks.run_external_task", side_effect=engine) as task,
                  patch("hflow.services.external_engine.shared_external_engine_pool")):
                with patch.object(identity, "IDENTITY_VERSION", "previous-policy"):
                    identity.prepare_speakers(str(audio), segments, "fixture")
                current = identity.prepare_speakers(str(audio), segments, "fixture")
                self.assertEqual(task.call_count, 2)
                self.assertEqual(identity.prepare_speakers(str(audio), segments, "fixture"), current)
                self.assertEqual(task.call_count, 2)
                self.assertEqual(len(list(Path(directory).glob("speaker-map-*.json"))), 2)

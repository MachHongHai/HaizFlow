import hashlib
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pytest

from hflow.core import bundled_models, voice_profile_model
from hflow.core.model_integrity import ModelIntegrityError
from hflow.pipeline import speaker_identity as identity
from hflow.pipeline.speaker_runtime import VoiceProfileSession


def test_acoustic_consensus_handles_high_male_and_one_outlier():
    turns = [[300] * 30, [320] * 100, [330] * 30]
    assert identity._acoustic_voice_profile(turns, [.98, .92, .01])[0] == "male"
    assert identity._acoustic_voice_profile(turns, [.02, .08, .99])[0] == "female"
    assert identity._acoustic_voice_profile(turns[:2], [.99, .01])[0] == "unknown"
    assert identity.FALLBACK_VOICE == "omnivoice:female_gentle"


def test_habitual_register_is_retained_when_model_misses_stylized_male_voice():
    quiet = [120, 125, float("nan"), 122, 118, float("nan"), 119, 123, 121, 124]
    assert identity._acoustic_voice_profile([[340] * 80, quiet], [.01, .01])[0] == "male"
    assert identity._acoustic_voice_profile([[260] * 30, [270] * 30], [.01, .02])[0] == "female"
    assert identity._acoustic_voice_profile([[]], [None])[0] == "unknown"


def test_a_short_unrepresented_actor_is_not_forced_into_only_long_actor():
    vectors = np.array([[1, 0], [0, 1], [.02, .9998], [.9998, .02]], dtype=np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    segments = [{"start": i * 3, "end": i * 3 + length} for i, length in enumerate([3, 1, 1, 1])]
    labels, _ = identity._label_turns(vectors, list(range(4)), segments)
    assert labels[0] == labels[3]
    assert labels[1] == labels[2] != labels[0]


def test_subsecond_turn_can_get_an_independent_identity_without_moving_long_turns():
    vectors = np.array([[1, 0], [0, 1], [.9998, .02]], dtype=np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    segments = [{"start": 0, "end": 3}, {"start": 4, "end": 4.62}, {"start": 5, "end": 8}]
    labels, _ = identity._label_turns(vectors, [0, 1, 2], segments)
    assert labels[0] == labels[2] != labels[1]


def test_sparse_pitch_in_short_voice_needs_extremely_confident_independent_timbre():
    samples = [[float("nan")] * 10]
    assert identity._acoustic_voice_profile(samples, [.004])[0] == "female"
    assert identity._acoustic_voice_profile(samples, [.995])[0] == "male"
    assert identity._acoustic_voice_profile(samples, [.20])[0] == "unknown"
    assert identity._acoustic_voice_profile([[float("nan")] * 3], [.004])[0] == "unknown"


def test_timbre_inheritance_requires_independent_samples_not_just_pitch_or_adjacency():
    vectors = np.array([[1, 0, 0], [.99, .01, 0], [.8, .6, 0], [.8, .59, .01], [0, 0, 1]], dtype=np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    profiles = {0: ("male", False, 300, .98), 1: ("unknown", True, 310, .5),
                2: ("female", False, 300, .01)}
    labels = [0, 0, 1, 1, 2]
    resolved = identity._resolve_voice_families(vectors, labels, profiles)
    assert resolved[1][:2] == ("male", True)
    assert labels == [0, 0, 1, 1, 2]  # Family inheritance never changes identity.
    assert identity._resolve_voice_families(vectors[[0, 2, 4]], [0, 1, 2], profiles)[1][0] == "unknown"
    assert resolved[2] == profiles[2]


def test_profile_classifier_uses_correct_pcm_scale_and_cpu_only():
    model = Mock()
    model.run.return_value = [np.array([[3., -3.]], dtype=np.float32)]
    with patch("onnxruntime.InferenceSession", return_value=model) as session:
        profile = VoiceProfileSession("fixture.onnx")
    assert session.call_args.kwargs["providers"] == ["CPUExecutionProvider"]
    assert profile.male_probability(np.array([16384., -16384.], dtype=np.float32)) > .99
    np.testing.assert_array_equal(model.run.call_args.args[1]["input_values"], [[.5, -.5]])
    profile.male_probability(np.array([65536.,-32768.],dtype=np.float32))
    np.testing.assert_array_equal(model.run.call_args.args[1]["input_values"],[[2.,-1.]])
    model.run.return_value = [np.array([[float("nan"), 0.]])]
    with pytest.raises(RuntimeError, match="invalid logits"):
        profile.male_probability(np.zeros(16000))


def test_core_accepts_only_verified_profile_and_still_accepts_old_core(tmp_path):
    folder = tmp_path / "speaker-identification"
    folder.mkdir()
    (folder / bundled_models.MODEL_FILE).write_bytes(b"legacy speaker")
    profile = folder / voice_profile_model.MODEL_FILE
    with patch.object(bundled_models, "verify_speaker"):
        assert bundled_models.verify_core_models(tmp_path, required=True)
        profile.write_bytes(b"profile")
        with (patch.object(voice_profile_model, "MODEL_SIZE", 7),
              patch.object(voice_profile_model, "MODEL_SHA256", hashlib.sha256(b"profile").hexdigest())):
            assert bundled_models.verify_core_models(tmp_path, required=True)
            profile.write_bytes(b"changed")
            with pytest.raises(ModelIntegrityError, match="checksum"):
                bundled_models.verify_core_models(tmp_path, required=True)


def test_no_usable_speech_falls_back_without_default_voice_or_failing_task(tmp_path):
    def decoded_audio(_video, process, **kwargs):
        Path(process.args[-1]).write_bytes(np.zeros(16000,dtype='<f4').tobytes())
        return "", ""
    def process(args, **kwargs):
        return Mock(args=args, returncode=0)
    segments = [{"start": 0, "end": 1, "text": "Some subtitle."}]
    with (patch.object(identity, "verify_model", return_value=tmp_path / "speaker.onnx"),
          patch("hflow.pipeline.speaker_runtime.SpeakerSession"),
          patch.object(identity, "TMP_DIR", str(tmp_path)),
          patch.object(identity.subprocess, "Popen", side_effect=process),
          patch.object(identity, "communicate_process", side_effect=decoded_audio)):
        result = identity.identify("fixture.wav", segments, "fixture")
    assert identity._valid_map(result, segments)
    assert result[0]["speaker_voice"] == "omnivoice:female_gentle"
    assert result[0]["speaker_voice_fallback"] and result[0]["speaker_uncertain"]

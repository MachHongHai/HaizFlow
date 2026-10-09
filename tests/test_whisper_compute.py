import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from haizflow.core.whisper_compute import whisper_compute_type


@pytest.mark.parametrize("device,supported,expected", [
    ("cuda", {"int8_float32", "float32"}, "int8_float32"),
    ("cuda", {"float16", "int8_float16", "float32"}, "float16"),
    ("cuda", {"float32"}, "float32"),
    ("cpu", {"int8", "int8_float32", "float32"}, "int8"),
])
def test_backend_capabilities_preserve_modern_gpu_and_cpu_modes(device, supported, expected):
    query = Mock(return_value=supported)
    with patch.dict(sys.modules, {"ctranslate2": SimpleNamespace(get_supported_compute_types=query)}):
        assert whisper_compute_type(device) == expected
    query.assert_called_once_with(device, device_index=0)


def test_unknown_capabilities_do_not_downgrade_gpu():
    query = Mock(side_effect=RuntimeError("driver unavailable"))
    with patch.dict(sys.modules, {"ctranslate2": SimpleNamespace(get_supported_compute_types=query)}):
        assert whisper_compute_type("cuda") == "float16"


def test_known_unusable_backend_is_not_accepted():
    with patch.dict(sys.modules, {"ctranslate2": SimpleNamespace(get_supported_compute_types=lambda *a, **k: set())}):
        with pytest.raises(RuntimeError, match="Whisper"):
            whisper_compute_type("cuda")


def test_clone_reference_uses_same_legacy_gpu_policy():
    from haizflow.pipeline.voice_reference import recognize_reference

    model = Mock()
    model.transcribe.return_value = ([SimpleNamespace(text="voice")], None)
    constructor = Mock(return_value=model)
    with (
        patch.dict(sys.modules, {"faster_whisper": SimpleNamespace(WhisperModel=constructor),
                                "ctranslate2": SimpleNamespace(get_supported_compute_types=lambda *a, **k:
                                                               {"int8_float32", "float32"})}),
    ):
        assert recognize_reference("reference.wav", "model", device="gpu") == "voice"
    assert constructor.call_args.kwargs["device"] == "cuda"
    assert constructor.call_args.kwargs["compute_type"] == "int8_float32"


@pytest.mark.parametrize("supported,expected", [
    ({"int8_float32", "float32"}, "int8_float32"),
    ({"float16", "float32"}, "float16"),
])
@pytest.mark.parametrize("warm", [False, True])
def test_warm_and_cold_whisper_load_select_same_capability_mode(supported, expected, warm):
    from haizflow.pipeline import transcribe

    profile = SimpleNamespace(cuda_available=True, cpu_threads=4, whisper_batch_size=8)
    with (
        patch.dict(sys.modules, {"ctranslate2": SimpleNamespace(get_supported_compute_types=lambda *a, **k: supported)}),
        patch.object(transcribe, "runtime_profile", return_value=profile),
        patch("haizflow.core.hardware.cpu_runtime_profile", return_value=profile),
        patch.object(transcribe, "_WARM_ASR_MODEL", None),
        patch.object(transcribe, "_WARM_DEVICE", None),
        patch.object(transcribe, "_WARM_MODEL_NAME", None),
        patch.object(transcribe, "_load_whisper_model", return_value=Mock()) as load,
        patch.object(transcribe, "log_to_video"),
        patch.object(transcribe, "_release_cuda"),
        patch.object(transcribe.whisperx, "load_audio", side_effect=RuntimeError("stop before inference")),
    ):
        if warm:
            assert transcribe.warm_whisperx_model(device_preference="gpu")
            assert transcribe.warm_whisperx_model(device_preference="gpu")
        else:
            with pytest.raises(RuntimeError, match="stop before inference"):
                transcribe.transcribe("sample.wav", "result.json", "auto", "video", device_preference="gpu")
        load.assert_called_once_with("cuda", expected, 4, "small")

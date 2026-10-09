"""Clone sample ASR must follow the selected TTS device, not a hard-coded CPU."""
import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from haizflow.pipeline import omnivoice_tts, voice_reference


def test_cancelled_reference_does_not_return_a_cached_transcript(tmp_path):
    import hashlib
    sample = tmp_path / "sample.wav"
    sample.write_bytes(b"authorized-sample")
    cache = tmp_path / "voice-reference-transcripts" / f"{hashlib.sha256(sample.read_bytes()).hexdigest()}.json"
    cache.parent.mkdir()
    cache.write_text(json.dumps({"text": "sample text"}), encoding="utf-8")
    with patch.object(voice_reference, "TMP_DIR", str(tmp_path)), \
         patch.object(voice_reference, "check_cancellation", side_effect=RuntimeError("cancelled")):
        with pytest.raises(RuntimeError, match="cancelled"):
            voice_reference.transcribe_reference(str(sample), "video", device="cpu")


@pytest.mark.parametrize("device, compute", [("gpu", "float16"), ("cpu", "int8")])
def test_reference_recognition_uses_selected_device(device, compute):
    model = Mock()
    model.transcribe.return_value = ([SimpleNamespace(text=" Spoken sample ")], None)
    factory = Mock(return_value=model)
    with patch.dict(sys.modules, {"faster_whisper": SimpleNamespace(WhisperModel=factory)}):
        assert voice_reference.recognize_reference("sample.wav", "model", device=device) == "Spoken sample"
    assert factory.call_args.kwargs["device"] == ("cuda" if device == "gpu" else "cpu")
    assert factory.call_args.kwargs["compute_type"] == compute


def test_only_gpu_resource_failure_allows_explicit_cpu_retry(capsys):
    model = Mock()
    model.transcribe.return_value = ([SimpleNamespace(text="sample")], None)
    factory = Mock(side_effect=[RuntimeError("CUDA out of memory"), model])
    with patch.dict(sys.modules, {"faster_whisper": SimpleNamespace(WhisperModel=factory)}):
        assert voice_reference.recognize_reference("sample", "model", device="gpu") == "sample"
    assert [call.kwargs["device"] for call in factory.call_args_list] == ["cuda", "cpu"]
    assert "[CLONE-ASR][WARN]" in capsys.readouterr().err
    factory = Mock(side_effect=RuntimeError("corrupt model"))
    with patch.dict(sys.modules, {"faster_whisper": SimpleNamespace(WhisperModel=factory)}):
        with pytest.raises(RuntimeError, match="corrupt model"):
            voice_reference.recognize_reference("sample", "model", device="gpu")
    assert factory.call_count == 1


@pytest.mark.parametrize("device", ["cpu", "gpu"])
def test_parent_request_and_resource_pack_are_device_consistent(tmp_path, device):
    sample = tmp_path / "sample.wav"
    sample.write_bytes(b"authorized-sample")
    requests = []
    process = Mock(returncode=0)

    def communicate(_id, _process, **_kwargs):
        request_path = next(tmp_path.glob("clone-asr-*/request.json"))
        request = json.loads(request_path.read_text())
        requests.append(request)
        from pathlib import Path
        Path(request["response_path"]).write_text(json.dumps({"ok": True, "result": {"text": "sample text"}}))
        return "", ""

    with patch.object(voice_reference, "TMP_DIR", str(tmp_path)), \
         patch.object(voice_reference, "verify_whisper_model", return_value=tmp_path), \
         patch.object(voice_reference, "check_cancellation"), \
         patch.object(voice_reference, "log_to_video"), \
         patch.object(voice_reference.subprocess, "Popen", return_value=process), \
         patch.object(voice_reference, "communicate_process", side_effect=communicate), \
         patch("haizflow.core.memory.require_cpu_memory"), \
         patch("haizflow.services.resource_packs.installed_engine_command", return_value=["engine"]) as command, \
         patch("haizflow.core.paths.engine_environment", return_value={"HAIZFLOW_ENGINE_APP_ROOT": "D:/Installed"}) as env:
        assert voice_reference.transcribe_reference(str(sample), "video", device=device) == "sample text"
        assert voice_reference.transcribe_reference(str(sample), "video", device=device) == "sample text"
        assert voice_reference.subprocess.Popen.call_args.kwargs["env"]["HAIZFLOW_ENGINE_APP_ROOT"] == "D:/Installed"
    assert len(requests) == 1
    assert requests[0]["payload"]["device"] == device
    assert command.call_args.args[2]["device"] == device
    env.assert_called_once()


def test_shared_clone_sample_is_prepared_once_before_tts_load():
    items = [{"reference_path": "same.wav", "reference_text": "", "text": str(i)} for i in range(12)]
    with patch.object(voice_reference, "transcribe_reference", return_value="sample") as asr, \
         patch.object(omnivoice_tts, "_prepare_isolated_runtime", side_effect=RuntimeError("after-asr")), \
         patch.object(omnivoice_tts, "check_cancellation"), patch.object(omnivoice_tts, "log_to_video"):
        with pytest.raises(RuntimeError, match="after-asr"):
            omnivoice_tts.synthesize_batch_to_mp3(items, "video", language_id="vi", device="gpu")
    asr.assert_called_once_with("same.wav", "video", process_registry_id="video", device="gpu")


@pytest.mark.parametrize("response, expected", [(None, "mã 1"),
    ({"ok": False, "error": "engine root missing"}, "engine root missing")])
def test_reference_failure_preserves_engine_error_even_with_empty_stderr(tmp_path, response, expected):
    sample = tmp_path / "sample.wav"
    sample.write_bytes(b"sample")
    def communicate(*_args, **_kwargs):
        if response is not None:
            request = json.loads(next(tmp_path.glob("clone-asr-*/request.json")).read_text())
            from pathlib import Path
            Path(request["response_path"]).write_text(json.dumps(response))
        return "", ""
    with patch.object(voice_reference, "TMP_DIR", str(tmp_path)), \
         patch.object(voice_reference, "verify_whisper_model", return_value=tmp_path), \
         patch.object(voice_reference, "check_cancellation"), \
         patch.object(voice_reference, "log_to_video"), \
         patch.object(voice_reference.subprocess, "Popen", return_value=Mock(returncode=1)), \
         patch.object(voice_reference, "communicate_process", side_effect=communicate), \
         patch("haizflow.services.resource_packs.installed_engine_command", return_value=["engine"]):
        with pytest.raises(RuntimeError, match=expected):
            voice_reference.transcribe_reference(str(sample), "video", device="gpu")

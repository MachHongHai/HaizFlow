"""Real decoder/Unicode regression tests without loading AI models or librosa."""
import contextlib
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
import soundfile as sf

from haizflow.pipeline import clone_audio, omnivoice_tts
from haizflow.utils.ffmpeg import _binary


@pytest.mark.parametrize("sample_rate,max_seconds", [(24000, None), (48000, 8)])
def test_aac_unicode_reference_becomes_sdk_readable_pcm_without_librosa(
        tmp_path, monkeypatch, sample_rate, max_seconds):
    import sys

    folder = tmp_path / "Mẫu giọng 中文 한국어"
    folder.mkdir()
    source = folder / "giọng thu.m4a"
    subprocess.run([_binary("ffmpeg"), "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i",
        "sine=frequency=440:sample_rate=44100:duration=0.4", "-ac", "2", "-c:a", "aac", str(source)],
        check=True, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    original = source.read_bytes()
    with pytest.raises(RuntimeError):
        sf.read(str(source))  # Reproduce the SDK's failed primary decoder.
    monkeypatch.setitem(sys.modules, "librosa", None)
    target = folder / "prepared.wav"
    assert clone_audio.prepare_reference(str(source), target, "", sample_rate=sample_rate,
                                         max_seconds=max_seconds) == str(target.resolve())
    audio, rate = sf.read(str(target), always_2d=True)
    assert rate == sample_rate and audio.shape[1] == 1 and audio.size > 0
    assert source.read_bytes() == original
    if sample_rate == 24000:
        model = SimpleNamespace(create_voice_clone_prompt=Mock(return_value="tokens"))
        torch = SimpleNamespace(inference_mode=contextlib.nullcontext)
        assert omnivoice_tts._encode_voice_reference(model, torch, str(target), "Sample.") == "tokens"
        samples, rate = model.create_voice_clone_prompt.call_args.kwargs["ref_audio"]
        assert isinstance(samples, np.ndarray) and samples.shape[0] == 1 and rate == 24000


@pytest.mark.parametrize("kind", ["missing", "directory", "empty", "invalid"])
def test_bad_reference_stops_without_returning_a_default_voice(tmp_path, kind):
    source = tmp_path / "sample.m4a"
    if kind == "directory":
        source.mkdir()
    elif kind == "empty":
        source.touch()
    elif kind == "invalid":
        source.write_bytes(b"not audio")
    with pytest.raises(ValueError, match="mẫu giọng"):
        clone_audio.prepare_reference(str(source), tmp_path / "reference.wav", "", sample_rate=24000)


def test_reference_never_overwrites_original(tmp_path):
    source = tmp_path / "sample.wav"
    source.write_bytes(b"original")
    with pytest.raises(ValueError, match="ghi đè"):
        clone_audio.prepare_reference(str(source), source, "", sample_rate=24000)
    assert source.read_bytes() == b"original"


def test_omnivoice_decodes_shared_sample_once_and_preserves_warm_cache_identity(tmp_path, monkeypatch):
    source = tmp_path / "Mẫu gốc.wav"
    sf.write(str(source), np.full(2400, .1, dtype=np.float32), 24000)
    original = source.read_bytes()
    monkeypatch.setattr(omnivoice_tts, "_prepare_isolated_runtime", Mock())
    monkeypatch.setattr(omnivoice_tts, "verify_omnivoice_model", lambda root: tmp_path)
    monkeypatch.setattr(omnivoice_tts, "_sdk_root", lambda: tmp_path)
    monkeypatch.setattr(omnivoice_tts, "TMP_DIR", str(tmp_path))
    monkeypatch.setattr(omnivoice_tts, "log_to_video", Mock())
    monkeypatch.setattr(omnivoice_tts, "_preset_reference", lambda *args: ("", ""))
    prepare = Mock(wraps=clone_audio.prepare_reference)
    monkeypatch.setattr(clone_audio, "prepare_reference", prepare)
    captured = []

    class StopBeforeModel(Exception):
        pass

    def worker(_path, request, *args, **kwargs):
        items = request["items"]
        assert items[0]["reference_path"] == items[1]["reference_path"] != str(source)
        assert all(item["reference_text"] == "Bản chép lời đầy đủ." for item in items)
        info = sf.info(items[0]["reference_path"])
        assert info.samplerate == 24000 and info.channels == 1 and info.frames == 2400
        captured.append((items[0]["reference_path"], items[0]["reference_identity"]))
        raise StopBeforeModel

    monkeypatch.setattr(omnivoice_tts, "_run_worker_process", worker)
    for _ in range(2):
        with pytest.raises(StopBeforeModel):
            omnivoice_tts.synthesize_batch_to_mp3([
                {"text": text, "voice": "omnivoice:clone", "reference_path": str(source),
                 "reference_text": "Bản chép lời đầy đủ.", "output_path": str(tmp_path / f"{index}.mp3")}
                for index, text in enumerate(["Câu thứ nhất.", "Câu thứ hai."])], "probe",
                device="cpu", language_id="vi", keep_worker_warm=False)
    assert prepare.call_count == 2  # One decode per request, not per sentence.
    assert captured[0][0] != captured[1][0]  # Each request owns its temp files.
    assert captured[0][1] == captured[1][1] and captured[0][1]
    assert source.read_bytes() == original

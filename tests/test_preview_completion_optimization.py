from concurrent.futures import CancelledError, ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import wave

import numpy as np
import pytest
from PySide6.QtGui import QGuiApplication

from haizflow.desktop.manual_preview_audio_controller import ManualPreviewAudioController
from haizflow.utils import ffmpeg


_APP = None


@pytest.fixture
def audio():
    global _APP
    _APP = QGuiApplication.instance() or QGuiApplication([])
    controller = ManualPreviewAudioController()
    yield controller
    controller.close()


def speech_wav(path, rate, channels, seconds):
    samples = np.arange(round(rate * seconds))
    tone = (np.sin(samples * (2 * np.pi * 219 / rate)) * 8000).astype("<i2")
    tone[:rate // 20] = 0
    tone[-rate // 10:] = 0
    pcm = tone if channels == 1 else np.column_stack((tone, tone // 2))
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(pcm.tobytes())


def test_batched_voice_is_byte_identical_to_existing_decoder_and_starts_one_process(audio, tmp_path):
    requests = []
    for index, (rate, channels, seconds, slot) in enumerate([
        (24000, 1, .37, 1300), (48000, 2, .91, 1600),
        (22050, 1, 1.75, 500), (44100, 2, 1.9, 160),
        (24000, 1, 1.2, 1900), (16000, 1, .13, 700),
        (48000, 1, .57, 200), (24000, 2, .8, 1200),
    ]):
        source = tmp_path / f"câu-{index}.wav"
        speech_wav(source, rate, channels, seconds)
        requests.append((str(source), slot, bool(index % 2), str(index)))
    expected = [audio._decode(path, duration, fit, content_signature=signature).tobytes()
                for path, duration, fit, signature in requests]
    audio._cache.clear()
    with patch.object(audio, "_run_decode_process", wraps=audio._run_decode_process) as run:
        audio._prefetch_voice_pcm(requests, audio._generation)
        assert run.call_count == 1
        actual = [audio._decode(path, duration, fit, content_signature=signature).tobytes()
                  for path, duration, fit, signature in requests]
        assert actual == expected
        audio._prefetch_voice_pcm(requests, audio._generation)
        assert run.call_count == 1  # Warm requests never restart decoding.


def test_old_path_key_pcm_remains_reusable_without_redecode(audio, tmp_path):
    source = tmp_path / "voice.wav"
    speech_wav(source, 24000, 1, .4)
    audio._pcm_cache_directory = tmp_path / "pcm"
    audio._pcm_cache_directory.mkdir()
    old_key = audio._pcm_key(source, 1000, False, "")
    cache = audio._pcm_cache_path(old_key)
    expected = np.arange(80, dtype="<i2").reshape(-1, 2)
    cache.write_bytes(expected.tobytes())
    with patch.object(audio, "_run_decode_process", side_effect=AssertionError("Old cache must be reused")):
        result = audio._decode(source, 1000, False, content_signature="immutable-voice")
    np.testing.assert_array_equal(result, expected)
    assert cache.exists()
    source.write_bytes(source.read_bytes() + b"changed")
    with patch.object(audio, "_decode_to_pcm", return_value=expected) as decode:
        audio._decode(source, 1000, False, content_signature="immutable-voice")
        decode.assert_called_once()  # Compatibility does not ignore source mutation.


def test_cancelled_batch_cannot_publish_partial_pcm(audio, tmp_path):
    requests = []
    for index in range(2):
        source = tmp_path / f"{index}.wav"
        speech_wav(source, 24000, 1, .3)
        requests.append((str(source), 1000, False, str(index)))
    audio._pcm_cache_directory = tmp_path / "pcm"
    audio._pcm_cache_directory.mkdir()
    with patch.object(audio, "_run_decode_process", side_effect=CancelledError):
        with pytest.raises(CancelledError):
            audio._prefetch_voice_pcm(requests, audio._generation)
    assert not audio._cache
    assert not list(audio._pcm_cache_directory.iterdir())
    assert not list(Path(audio._pcm_directory.name).iterdir())


def test_failed_batch_keeps_single_decoder_fallback(audio, tmp_path):
    source = tmp_path / "voice.wav"
    speech_wav(source, 24000, 1, .4)
    with patch.object(audio, "_decode_voice_batch", side_effect=RuntimeError("unsupported")):
        audio._prefetch_voice_pcm([(str(source), 1000, False, "a"),
                                   (str(source), 500, False, "b")], audio._generation)
    assert not audio._cache
    assert len(audio._decode(source, 1000, content_signature="a")) > 0


def test_cancel_during_batch_publication_releases_temporary_windows_mappings(audio, tmp_path, monkeypatch):
    batch = []
    for index in range(2):
        source = tmp_path / f"cancel-{index}.wav"
        speech_wav(source, 24000, 1, .3)
        key = audio._pcm_key(source, 1000, False, str(index))
        batch.append((str(source), 1000, False, str(index), key))

    def cancel_before_remember(*_args, **_kwargs):
        raise CancelledError()

    monkeypatch.setattr(audio, "_remember_pcm", cancel_before_remember)
    with pytest.raises(CancelledError):
        audio._decode_voice_batch(batch, audio._generation)
    assert not audio._cache
    assert not list(Path(audio._pcm_directory.name).iterdir())


def test_batch_pcm_is_atomically_reusable_after_memory_cache_is_cleared(audio, tmp_path):
    audio._pcm_cache_directory = tmp_path / "pcm"
    audio._pcm_cache_directory.mkdir()
    requests = []
    for index in range(2):
        source = tmp_path / f"persistent-{index}.wav"
        speech_wav(source, 24000, 1, .3)
        requests.append((str(source), 1000, False, str(index)))
    audio._prefetch_voice_pcm(requests, audio._generation)
    expected = [audio._decode(path, slot, fit, content_signature=signature).tobytes()
                for path, slot, fit, signature in requests]
    assert len(list(audio._pcm_cache_directory.glob("*.pcm"))) == 2
    assert not list(audio._pcm_cache_directory.glob("*.partial"))
    audio._cache.clear()
    with patch.object(audio, "_run_decode_process", side_effect=AssertionError("Must reuse published PCM")):
        for index, (path, slot, fit, signature) in enumerate(requests):
            assert audio._decode(path, slot, fit, content_signature=signature).tobytes() == expected[index]


def test_voice_decode_batch_has_a_fixed_input_bound(audio, tmp_path):
    source = tmp_path / "voice.wav"
    speech_wav(source, 24000, 1, .3)
    requests = [(str(source), 1000, False, str(index)) for index in range(20)]
    with patch.object(audio, "_decode_voice_batch") as decode:
        audio._prefetch_voice_pcm(requests, audio._generation)
    assert [len(call.args[0]) for call in decode.call_args_list] == [8, 8, 4]


def test_cached_voice_is_returned_for_direct_consumption_without_second_lookup(audio, tmp_path):
    source = tmp_path / "ready.wav"
    speech_wav(source, 24000, 1, .3)
    requests = [(str(source), 1000, False, "one"), (str(source), 500, False, "two")]
    cold = audio._prefetch_voice_pcm(requests, audio._generation)
    assert set(cold) == set(requests)
    with patch.object(audio, "_run_decode_process", side_effect=AssertionError("Warm PCM")), \
         patch.object(audio, "_pcm_key", wraps=audio._pcm_key) as identities:
        warm = audio._prefetch_voice_pcm(requests, audio._generation)
    assert identities.call_count == len(requests)
    for request in requests:
        assert warm[request] is cold[request]


def test_native_payload_copy_keeps_nested_clip_and_caption_data_detached(audio, monkeypatch):
    from haizflow.desktop.manual_editor_document_model import ManualEditorDocumentModel, _copy_payload
    from haizflow.schemas.editor import EditorClip, EditorDocument

    nested = {"words": [{"text": "你好 / 안녕 / Xin chào", "start": .123456789}],
              "position": (1, {"colors": ["red", "blue"]})}
    detached = _copy_payload(nested)
    assert isinstance(detached["position"], tuple)
    detached["position"][1]["colors"].append("other")
    assert nested["position"][1]["colors"] == ["red", "blue"]
    document = EditorDocument(video_id="native-copy", clips=[EditorClip(
        clip_id="caption", track_id="subtitles", segment_id="one", kind="subtitle", name="Xin chào",
        duration_ms=1000, metadata={"segment_payload": {"text": "Xin chào", "start": 0, "end": 1, **nested}})])
    model = ManualEditorDocumentModel()
    monkeypatch.setattr(model, "_schedule_waveforms", lambda: None)
    try:
        model.set_document(document)
        for _ in range(2):
            clip = model.clips[0]
            clip["metadata"]["segment_payload"]["words"][0]["text"] = "mutated"
            caption = model.subtitleSegments[0]
            caption["words"][0]["text"] = "mutated"
            assert model.clips[0]["metadata"]["segment_payload"]["words"][0]["text"] == nested["words"][0]["text"]
            assert model.subtitleSegments[0]["words"][0]["text"] == nested["words"][0]["text"]
    finally:
        model.close()


def test_warm_editor_requests_audio_without_repeating_cold_start_delay():
    from haizflow.desktop.qml_controller import HaizFlowController
    selected = SimpleNamespace(video_id="warm", project_type="manual")
    host = SimpleNamespace(_project_import=None, _selected_video_id="warm", _manual_voice_video_id="warm",
        _selected_video=lambda: selected, _manual_editor_warm_identity="same",
        _manual_editor_document=SimpleNamespace(video_id="warm", set_document=Mock()),
        _manual_subtitles=SimpleNamespace(video_id="warm", load=Mock()),
        refreshManualPreviewAudio=Mock(), _schedule_manual_cache_migration=Mock())
    with patch.object(HaizFlowController, "_editor_warm_identity", return_value="same"), \
         patch("haizflow.desktop.qml_controller.QTimer.singleShot") as schedule:
        HaizFlowController.loadManualSubtitles(host)
    assert [call.args[0] for call in schedule.call_args_list] == [0, 950]
    host._manual_editor_document.set_document.assert_not_called()
    host._manual_subtitles.load.assert_not_called()
    refresh = schedule.call_args_list[0].args[1]
    refresh()
    host.refreshManualPreviewAudio.assert_called_once()
    host._selected_video_id = "other"
    refresh()
    host.refreshManualPreviewAudio.assert_called_once()


def test_probe_batch_reuses_only_successful_unchanged_files_and_clears_after_exit(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    with patch.object(ffmpeg.subprocess, "run", return_value=SimpleNamespace(stdout="12")) as run:
        with ffmpeg.media_probe_batch():
            assert ffmpeg.get_video_duration(str(source)) == 12
            assert ffmpeg.get_video_duration(str(source)) == 12
            assert run.call_count == 1
            source.write_bytes(b"new source")
            ffmpeg.get_video_duration(str(source))
            assert run.call_count == 2
        ffmpeg.get_video_duration(str(source))
        assert run.call_count == 3
    with patch.object(ffmpeg.subprocess, "run", side_effect=[OSError("probe failed"), SimpleNamespace(stdout="9")]) as run:
        with ffmpeg.media_probe_batch():
            assert ffmpeg.get_video_duration(str(source)) == 0
            assert ffmpeg.get_video_duration(str(source)) == 9
        assert run.call_count == 2


def test_probe_batch_is_thread_local_and_nested_context_keeps_outer_cache(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"media")
    probe = Mock(return_value=SimpleNamespace(stdout="640,360"))
    with patch.object(ffmpeg.subprocess, "run", probe):
        with ffmpeg.media_probe_batch():
            assert ffmpeg.get_video_dimensions(str(source)) == (640, 360)
            with ffmpeg.media_probe_batch():
                ffmpeg.get_video_dimensions(str(source))
            assert probe.call_count == 1
            with ThreadPoolExecutor(max_workers=1) as pool:
                assert pool.submit(ffmpeg.get_video_dimensions, str(source)).result() == (640, 360)
            assert probe.call_count == 2


def test_atomic_publication_reuses_probe_but_replacing_file_does_not(tmp_path):
    staged, output = tmp_path / "rendering.mp4", tmp_path / "preview.mp4"
    staged.write_bytes(b"complete video")
    with patch.object(ffmpeg.subprocess, "run", return_value=SimpleNamespace(stdout="5")) as probe:
        with ffmpeg.media_probe_batch():
            before = staged.stat()
            ffmpeg.get_video_duration(str(staged))
            staged.replace(output)
            after = output.stat()
            ffmpeg.get_video_duration(str(output))
            same_identity = (before.st_ino and before.st_ino == after.st_ino
                             and before.st_ctime_ns == after.st_ctime_ns)
            assert probe.call_count == (1 if same_identity else 2)
            replacement = tmp_path / "new.mp4"
            replacement.write_bytes(b"new generation")
            replacement.replace(output)
            ffmpeg.get_video_duration(str(output))
            assert probe.call_count == (2 if same_identity else 3)

"""Long timeline, Unicode subprocess and voice batch regressions (no models)."""
import json
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pytest
from PySide6.QtGui import QGuiApplication

from haizflow.desktop.editor_preview_controller import EditorPreviewController
from haizflow.pipeline import omnivoice_tts as voice
from haizflow.utils import ffmpeg

_GUI = None


@pytest.fixture(scope="module", autouse=True)
def gui():
    global _GUI
    _GUI = QGuiApplication.instance() or QGuiApplication([])
    yield _GUI


def test_small_asr_tail_does_not_materialize_thirty_minute_source():
    sequence = {"duration_ms": 1674115, "edit_decisions": [{
        "source_start_ms": 0, "source_end_ms": 1674067, "sequence_start_ms": 0,
    }]}
    assert EditorPreviewController._contiguous_source_window(sequence) == (0, 1674.115)
    sequence["duration_ms"] += 500
    assert EditorPreviewController._contiguous_source_window(sequence) is None
    sequence["duration_ms"] = 1674000
    assert EditorPreviewController._contiguous_source_window(sequence) is None


def test_plain_long_source_uses_streaming_audio_without_full_pcm_decode(tmp_path):
    from haizflow.desktop.manual_preview_audio_controller import ManualPreviewAudioController
    source = tmp_path / "long.mp4"
    source.write_bytes(b"media")
    video = SimpleNamespace(video_id="long", project_type="manual", files={"video_input": str(source)},
                            original_video_volume=60)
    controller = ManualPreviewAudioController()
    player, output = Mock(), Mock()
    player.position.return_value = 0
    controller._native_player, controller._native_output = player, output
    try:
        with (patch("haizflow.services.editor_documents.load", return_value=None),
              patch("haizflow.pipeline.manual_tools.published_voice_record", return_value=None),
              patch("haizflow.services.video_store.get_video_dir", return_value=str(tmp_path)),
              patch.object(controller, "_decode") as decode):
            controller.request(video, [])
            assert not controller.busy and controller._native_source == str(source)
            source_updates = player.setSource.call_count
            controller.synchronize(1200, True, False)
            controller.synchronize(1200, False, False)
            controller.synchronize(1200, True, False)
            controller.request(video, [{"text": "Caption only", "start": 1, "end": 2}])
            decode.assert_not_called()
        assert not controller._timer.isActive()
        assert player.setSource.call_count == source_updates
        assert player.play.call_count == 2
        controller.release()
        assert not controller._native_source
    finally:
        controller.close()


def test_edited_or_mixed_audio_cannot_use_plain_source_fast_path(tmp_path):
    from haizflow.desktop.manual_preview_audio_controller import ManualPreviewAudioController
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    video = SimpleNamespace(files={"video_input": str(source)})
    check = ManualPreviewAudioController._streamable_source
    assert check(video, None, None) == str(source)
    assert not check(video, None, {"signature": "voice"})
    video.files["background_music"] = str(source)
    assert not check(video, None, None)
    del video.files["background_music"]
    document = SimpleNamespace(sequence=SimpleNamespace(edit_decisions=[]))
    assert not check(video, document, None)


def test_streamed_source_replacement_at_same_path_reloads_native_decoder(tmp_path):
    from haizflow.desktop.manual_preview_audio_controller import ManualPreviewAudioController
    source = tmp_path / "input.mp4"
    source.write_bytes(b"old")
    video = SimpleNamespace(files={"video_input": str(source)}, original_video_volume=60)
    audio = ManualPreviewAudioController()
    audio._native_player, audio._native_output = Mock(), Mock()
    audio._native_player.position.return_value = 0
    try:
        audio._use_streaming_source(str(source), video, None)
        before = audio._native_player.setSource.call_count
        source.write_bytes(b"new longer media")
        audio._use_streaming_source(str(source), video, None)
        assert audio._native_player.setSource.call_count == before + 2  # detach, reload
        assert audio._native_identity[1] == source.stat().st_size
    finally:
        audio.close()


def test_native_audio_steady_playback_does_not_restart_or_seek_each_video_tick(tmp_path):
    from haizflow.desktop.manual_preview_audio_controller import ManualPreviewAudioController
    source = tmp_path / "source.mp4"
    source.write_bytes(b"media")
    audio = ManualPreviewAudioController()
    player, output = Mock(), Mock()
    audio._native_player, audio._native_output = player, output
    try:
        audio._use_streaming_source(str(source), SimpleNamespace(original_video_volume=60), None)
        player.position.return_value = 0
        audio.synchronize(0, True, False)
        for tick in range(1, 30):
            # Coarse video notifications may lead by 200 ms without real drift.
            player.position.return_value = tick * 100 - 200
            audio.synchronize(tick / 10, True, False)
        assert player.play.call_count == 1
        assert player.setPosition.call_count == 1
        audio.synchronize(3, False, False)
        audio.synchronize(3, False, False)
        assert player.pause.call_count == 1
        audio.synchronize(3, True, False)
        assert player.play.call_count == 2
    finally:
        audio.close()


def test_native_proxy_uses_embedded_audio_only_for_the_same_physical_source(tmp_path):
    import os
    from PySide6.QtCore import QUrl
    from haizflow.desktop.manual_preview_audio_controller import ManualPreviewAudioController
    source, native, rendered = (tmp_path / name for name in ("source.mp4", "native.mp4", "rendered.mp4"))
    source.write_bytes(b"original")
    os.link(source, native)
    rendered.write_bytes(b"silent rendered proxy")
    audio = ManualPreviewAudioController()
    player, output = Mock(), Mock()
    player.position.return_value = 0
    audio._native_player, audio._native_output = player, output
    try:
        audio._use_streaming_source(str(source), SimpleNamespace(original_video_volume=60), None)
        assert audio.canPlayEmbeddedSource(QUrl.fromLocalFile(str(native)))
        assert not audio.canPlayEmbeddedSource(QUrl.fromLocalFile(str(rendered)))
        assert not audio.canPlayEmbeddedSource(QUrl("https://example.com/video.mp4"))
        audio.synchronize(1, True, False, True)
        audio.synchronize(2, True, False, True)
        audio.seek(10)
        player.play.assert_not_called()
        player.setPosition.assert_not_called()
        assert output.setMuted.call_args.args == (True,)
        # Switching to a silent visual proxy reactivates the separate source.
        audio.synchronize(10, True, False, False)
        player.play.assert_called_once()
        assert player.setPosition.call_args.args == (10000,)
        audio.setVolumes(35, 100, 30)
        assert audio.nativeVolume == .35
    finally:
        audio.close()


def test_preview_clock_resync_requires_sustained_drift_and_has_a_cooldown():
    from haizflow.desktop.manual_preview_audio_controller import ManualPreviewAudioController
    audio = ManualPreviewAudioController()
    try:
        with patch("haizflow.desktop.manual_preview_audio_controller.time.monotonic") as clock:
            clock.return_value = 10
            assert not audio._needs_clock_resync(1, 0)
            clock.return_value = 10.2
            assert not audio._needs_clock_resync(1.2, .2)
            assert not audio._needs_clock_resync(1.2, 1)  # recovered transient
            clock.return_value = 11
            assert not audio._needs_clock_resync(2, 1)
            clock.return_value = 11.8
            assert audio._needs_clock_resync(2.8, 1.8)
            audio.seek(2.8)
            clock.return_value = 12.2
            assert not audio._needs_clock_resync(3.2, 2.2)
            assert audio.positionSeconds == 2.8
    finally:
        audio.close()


def test_pcm_refills_buffer_after_delayed_gui_ticks_without_dropping_samples():
    from haizflow.desktop.manual_preview_audio_controller import ManualPreviewAudioController, RATE, PCM_BUFFER_FRAMES
    queued = 0
    chunks = []
    def write(data):
        nonlocal queued
        queued += len(data) // 4
        chunks.append(data)
        return len(data)
    sink = Mock()
    sink.bufferSize.return_value = PCM_BUFFER_FRAMES * 4
    sink.bytesFree.side_effect = lambda: (PCM_BUFFER_FRAMES - queued) * 4
    sink.start.return_value = SimpleNamespace(write=write)
    audio = ManualPreviewAudioController()
    audio._sink = sink
    audio._playing = True
    samples = np.arange(RATE * 2, dtype=np.int16).reshape(-1, 1).repeat(2, axis=1)
    audio._tracks = [{"id": "source", "kind": "source", "start": 0, "samples": samples}]
    audio.setVolumes(100, 100, 30)
    try:
        audio._pump()
        for _ in range(10):
            consumed = round(RATE * .06)
            assert queued >= consumed
            queued -= consumed
            audio._pump()
        written = np.frombuffer(b"".join(chunks), dtype="<i2").reshape(-1, 2)
        np.testing.assert_array_equal(written, samples[:len(written)])
        assert queued == PCM_BUFFER_FRAMES
        assert audio._cursor == len(written)
        sink.reset.assert_not_called()
    finally:
        audio.close()


def test_leaving_project_releases_pcm_handles_but_keeps_completed_disk_cache(tmp_path):
    from haizflow.desktop.manual_preview_audio_controller import ManualPreviewAudioController
    path = tmp_path / "cached.pcm"
    path.write_bytes(bytes(400))
    audio = ManualPreviewAudioController()
    try:
        mapping = audio._map_pcm(path, persistent=True)
        audio._remember_pcm("source", mapping, generation=audio._generation)
        audio._tracks = [{"id": "source", "kind": "source", "samples": mapping}]
        old_generation = audio._generation
        del mapping
        audio.release()
        assert not audio._cache and path.is_file()
        path.unlink()  # Real Windows test: a mapped file would fail with WinError 32.
        with pytest.raises(Exception) as error:
            audio._remember_pcm("stale", np.zeros((1, 2)), generation=old_generation)
        from concurrent.futures import CancelledError
        assert isinstance(error.value, CancelledError)
        assert not audio._cache
    finally:
        audio.close()


def test_owned_download_input_is_linked_atomically_but_local_source_is_copied(tmp_path):
    from haizflow.services.desktop_videos import _copy_file_atomically
    source, destination = tmp_path / "download.mp4", tmp_path / "project" / "input.mp4"
    source.write_bytes(b"complete media")
    with patch("haizflow.services.desktop_videos.shutil.copyfile") as copy:
        _copy_file_atomically(str(source), str(destination), link_source=True)
        copy.assert_not_called()
    assert source.exists() and destination.read_bytes() == source.read_bytes()
    destination.unlink()
    with patch("haizflow.services.desktop_videos.os.link") as link:
        _copy_file_atomically(str(source), str(destination))
        link.assert_not_called()
    assert destination.read_bytes() == b"complete media"


def test_cross_volume_owned_download_still_copies_on_link_failure(tmp_path):
    from haizflow.services.desktop_videos import _copy_file_atomically
    source, destination = tmp_path / "source.mp4", tmp_path / "input.mp4"
    source.write_bytes(b"safe input")
    with patch("haizflow.services.desktop_videos.os.link", side_effect=OSError("cross-volume")):
        _copy_file_atomically(str(source), str(destination), link_source=True)
    assert source.exists() and destination.read_bytes() == b"safe input"


def test_current_early_return_cannot_leave_preview_loading(tmp_path):
    host = SimpleNamespace(editorPreviewChanged=Mock())
    controller = EditorPreviewController(host)
    controller._generation = 3
    controller._active_process_id = "current"
    controller._busy = True
    with patch.object(controller, "_render_current"):
        controller._render(3, "current", None, {}, tmp_path)
    assert not controller.busy
    assert controller.error
    host.editorPreviewChanged.emit.assert_called_once()


def test_obsolete_render_cannot_clear_new_request(tmp_path):
    controller = EditorPreviewController(SimpleNamespace(editorPreviewChanged=Mock()))
    controller._generation = 4
    controller._active_process_id = "new"
    controller._busy = True
    controller._render(3, "old", None, {}, tmp_path)
    assert controller.busy
    assert controller._active_process_id == "new"


@pytest.mark.parametrize("probe", [ffmpeg.get_video_duration, ffmpeg.get_video_dimensions, ffmpeg.get_media_stream_types])
def test_unicode_probe_never_uses_windows_ansi_decoding(probe):
    with patch.object(ffmpeg.subprocess, "run", return_value=SimpleNamespace(
        stdout='2' if probe is ffmpeg.get_video_duration else '64,64' if probe is ffmpeg.get_video_dimensions
        else '{"streams":[{"codec_type":"video"}]}',
    )) as run:
        probe("D:/中文/视频.mp4")
    assert run.call_args.kwargs["encoding"] == "utf-8"
    assert run.call_args.kwargs["errors"] == "replace"
    assert run.call_args.kwargs["timeout"] <= 15


def test_invalid_pair_falls_back_to_single_without_publishing_bad_waveforms():
    torch = SimpleNamespace(Tensor=type("Tensor", (), {}), OutOfMemoryError=type("OOM", (RuntimeError,), {}),
                            cuda=SimpleNamespace(empty_cache=Mock()))
    entries = [{"text": "A"}, {"text": "B"}]
    calls = []

    def generate(batch):
        calls.append(len(batch))
        audio = [np.zeros(480), np.full(480, np.nan)] if len(batch) > 1 else [np.zeros(480)]
        return voice._validated_waveforms(audio, len(batch), np, torch)

    waves, used, retries = voice._generate_bounded_batch(generate, entries, torch, "cuda:0")
    assert calls == [2, 1]
    assert used == entries[:1] and retries == 1
    assert len(waves) == 1 and np.isfinite(waves[0]).all()
    with pytest.raises(voice._InvalidSynthesisAudio):
        voice._generate_bounded_batch(lambda _: voice._validated_waveforms([np.zeros(1)], 1, np, torch),
                                      entries[:1], torch, "cuda:0")


def test_real_thirty_minute_unicode_source_is_reusable_without_render(tmp_path):
    source = tmp_path / "视频源.mp4"
    subprocess.run([
        ffmpeg._binary("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i",
        "color=c=black:s=64x64:r=1:d=1800", "-c:v", "libx264",
        "-pix_fmt", "yuv420p", str(source),
    ], check=True, capture_output=True, timeout=30)
    assert ffmpeg.get_video_duration(str(source)) == 1800
    settings = dict(source_path=str(source), output_format="keep_ratio", crop={},
                    remove_original_subtitles=True, ocr_region={},
                    editor_sequence={"duration_ms": 1800048, "edit_decisions": [{
                        "decision_id": "source", "source_start_ms": 0,
                        "source_end_ms": 1800000, "sequence_start_ms": 0,
                    }]})
    assert EditorPreviewController._can_reuse_native_source(settings, 0)
    assert not EditorPreviewController._can_reuse_native_source({**settings, "ocr_region": {"y": 80}}, 0)
    assert not EditorPreviewController._can_reuse_native_source({**settings, "crop": {"zoom_percent": 120}}, 0)
    assert not EditorPreviewController._can_reuse_native_source(settings, 1)
    settings.update(video_id="native-long", source_identity={}, segments=[], subtitle_style={},
                    subtitle_layout_override=False, removal_mode="patch", watermark_text="",
                    watermark_scale_percent=100, original_subtitle_intervals=[],
                    preview_encoding="test", independent_manual_preview=True,
                    original_video_volume=60, background_music_volume=30, tts_volume=100,
                    voice_state={}, audio_inputs={}, request_fingerprint="native")
    controller = EditorPreviewController(SimpleNamespace(editorPreviewChanged=Mock()))
    controller._generation = 1
    controller._video_id = "native-long"
    controller._request_fingerprint = "native"
    controller._active_process_id = "native-job"
    controller._busy = True
    with (patch.object(controller, "_render_proxy_layer", side_effect=AssertionError("No full encode")),
          patch.object(controller, "_materialize_preview_sequence", side_effect=AssertionError("No sequence encode")),
          patch("haizflow.desktop.editor_preview_controller.video_store.get_video", return_value=None)):
        controller._render_current(1, "native-job", SimpleNamespace(video_id="native-long"), settings, tmp_path / "preview")
    assert not controller.busy and not controller.error and controller.source


@pytest.mark.parametrize("pixel_format,allowed", [("yuv420p", True), ("yuv420p10le", False)])
def test_hevc_native_preview_accepts_sdr_without_unconditionally_converting_long_clip(pixel_format, allowed):
    settings = dict(source_path="long-hevc.mp4", output_format="keep_ratio", crop={},
                    remove_original_subtitles=True, ocr_region={})
    response = SimpleNamespace(stdout=json.dumps({"streams": [{"codec_name": "hevc", "pix_fmt": pixel_format}]}))
    with patch("haizflow.desktop.editor_preview_controller.subprocess.run", return_value=response):
        assert EditorPreviewController._can_reuse_native_source(settings, 0) == allowed


def test_disk_cache_hydration_finishes_without_probe(tmp_path):
    fingerprint = "a" * 64
    base = tmp_path / f"base-{fingerprint[:20]}"
    base.mkdir()
    output = base / "preview.mp4"
    output.write_bytes(b"intact cached long proxy")
    (base / "preview.complete.json").write_text(json.dumps({
        "version": 1, "duration": 1800, "size": output.stat().st_size,
    }), encoding="utf-8")
    controller = EditorPreviewController(SimpleNamespace())
    with patch("haizflow.desktop.editor_preview_controller.get_video_duration") as probe:
        controller._restore_manual_disk_cache(tmp_path, fingerprint)
    assert controller._completed_requests[fingerprint][3] == 1800
    probe.assert_not_called()


def test_preview_pcm_is_reused_after_project_reopen_and_invalidated_by_source_change(tmp_path):
    import wave
    from haizflow.desktop.manual_preview_audio_controller import ManualPreviewAudioController

    source = tmp_path / "音频.wav"
    with wave.open(str(source), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(48000)
        output.writeframes(np.full((4800, 2), 1234, dtype="<i2").tobytes())
    cache = tmp_path / "pcm-cache"
    cache.mkdir()
    first = ManualPreviewAudioController()
    try:
        first._pcm_cache_directory = cache
        samples = first._decode(source)
        assert samples.shape == (4800, 2)
        assert samples[0, 0] == 1234
    finally:
        first.close()
    assert len(list(cache.glob("*.pcm"))) == 1
    second = ManualPreviewAudioController()
    try:
        second._pcm_cache_directory = cache
        with patch.object(second, "_decode_to_pcm", side_effect=AssertionError("Must reuse PCM")):
            assert second._decode(source)[0, 0] == 1234
        source.touch()
        with patch.object(second, "_decode_to_pcm", return_value=np.zeros((10, 2), dtype="<i2")) as decode:
            second._decode(source)
        decode.assert_called_once()
    finally:
        second.close()


def test_cancelled_pcm_decode_never_publishes_cache(tmp_path):
    from concurrent.futures import CancelledError
    from haizflow.desktop.manual_preview_audio_controller import ManualPreviewAudioController
    audio = ManualPreviewAudioController()
    try:
        target = tmp_path / "cancelled.pcm"
        with pytest.raises(CancelledError):
            audio._decode_to_pcm(["not-launched"], audio._generation - 1, target)
        assert not target.exists()
        assert not target.with_suffix(".partial").exists()
    finally:
        audio.close()


def test_long_caption_index_keeps_overlap_and_gap_behavior_without_hot_hashing():
    from haizflow.desktop.subtitle_overlay_renderer import SubtitleOverlayRenderer
    renderer = SubtitleOverlayRenderer()
    renderer._events = [dict(start=i * 2, end=i * 2 + 1, body=str(i)) for i in range(1500)]
    renderer._events[100]["end"] = 205
    try:
        renderer._ensure_event_index()
        for index in (100, 102, 1499):
            renderer._cache[renderer._event_keys[index]] = {"normal": f"{index}.png"}
        with patch.object(renderer, "_event_key", side_effect=AssertionError("Hot seek must use index")), \
                patch.object(renderer, "_request_frame"):
            renderer.seek(202.5)
            assert renderer.frame["normal"] == "100.png"
            renderer.seek(205)
            assert not renderer.frame
            renderer.seek(2998.5)
            assert renderer.frame["normal"] == "1499.png"
            renderer.seek(2999)
            assert not renderer.frame
        renderer.release()
        assert renderer._indexed_events is None and not renderer._event_keys
    finally:
        renderer.close()


def test_waveform_disk_cache_skips_decode_and_isolated_by_fingerprint(tmp_path):
    from haizflow.desktop.manual_editor_document_model import ManualEditorDocumentModel
    payload = {"durationMs": 1800000, "peaks": [0.5] * 96}
    with patch("haizflow.services.desktop_videos.analyze_voice_reference", return_value=payload) as analyze:
        assert ManualEditorDocumentModel._cached_waveform("source.mp4", "first", tmp_path)["peaks"] == payload["peaks"]
        assert ManualEditorDocumentModel._cached_waveform("source.mp4", "first", tmp_path)["peaks"] == payload["peaks"]
        analyze.assert_called_once()
        ManualEditorDocumentModel._cached_waveform("source.mp4", "changed-source", tmp_path)
        assert analyze.call_count == 2
    assert len(list(tmp_path.glob("*.json"))) == 2
    assert not list(tmp_path.glob("*.tmp"))


def test_old_waveform_delivery_cannot_clear_new_project_pending_request():
    from concurrent.futures import Future
    from haizflow.desktop.manual_editor_document_model import ManualEditorDocumentModel
    model = ManualEditorDocumentModel()
    old, current = Future(), Future()
    try:
        model._waveform_futures["shared"] = old
        model._waveform_pending.add("shared")
        model._cancel_waveforms()
        assert old.cancelled() and not model._waveform_pending
        model._waveform_futures["shared"] = current
        model._waveform_pending.add("shared")
        model._accept_waveform("old-project", "shared", (old, {"peaks": []}))
        assert model._waveform_futures["shared"] is current
        assert "shared" in model._waveform_pending
        model._accept_waveform("new-project", "shared", (current, {"peaks": [0.5] * 96}))
        assert "shared" not in model._waveform_pending
    finally:
        model.close()


@pytest.mark.parametrize("change_voice", [False, True])
def test_reordered_multispeaker_clips_reuse_only_matching_voice_configuration(tmp_path, change_voice):
    from haizflow.pipeline import manual_tools
    from haizflow.services import manual_artifacts
    video = SimpleNamespace(video_id="reordered", project_type="manual", speaker_mode="multiple",
                            tts_provider="edge", tts_voice="vi-VN-NamMinhNeural", target_language="vi",
                            files={}, active_artifacts={})
    original = [dict(segment_id="a", start=0, end=1, text="Một"),
                dict(segment_id="b", start=1, end=2, text="Hai")]
    current = [dict(original[1], start=3, end=4), dict(original[0], start=5, end=6)]
    stage = tmp_path / "stage"
    stage.mkdir()
    audio = []
    for index in range(2):
        path = tmp_path / f"old-{index}.mp3"
        path.write_bytes(b"ID3" + bytes([index]) * 100)
        audio.append(path)
    subtitle = {"artifact_id": "subtitle_document:current", "resolved_outputs": {"segments": "current.json"}}
    with patch.object(manual_tools, "recognition_signature", return_value="same-source"), \
            patch.object(manual_tools, "_voice_cache_version", return_value="stable-version"):
        signatures = manual_tools._voice_clip_signatures(video, original)
        if change_voice:
            video.tts_voice = "vi-VN-HoaiMyNeural"
        expected = manual_artifacts.signature(manual_tools._voice_clip_signatures(video, current), "stable-version")

        def resolve(_id, kind, signature):
            if kind == "tts_clip" and signature in signatures:
                return {"resolved_outputs": {"audio": str(audio[signatures.index(signature)])}}
            return None

        def publish(*_args, **_kwargs):
            manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
            assert len(manifest["clips"]) == 2
            if not change_voice:
                assert (stage / "parts/voice_0001.mp3").read_bytes() == audio[1].read_bytes()
                assert (stage / "parts/voice_0002.mp3").read_bytes() == audio[0].read_bytes()
            return {"resolved_outputs": {"manifest": str(stage / "manifest.json")}}

        with (
            patch.object(manual_tools, "_load_segments", return_value=current),
            patch.object(manual_tools, "_current_subtitle_record", return_value=subtitle),
            patch.object(manual_tools, "ensure_narrator_anchor", return_value=""),
            patch.object(manual_tools.video_store, "get_video", return_value=video),
            patch.object(manual_tools, "published_voice_record", return_value={"signature": "old"}),
            patch.object(manual_tools, "published_voice_source_segments", return_value=original),
            patch.object(manual_tools, "_voice_manifest_payload", return_value={"clips": signatures}),
            patch.object(manual_tools.manual_artifacts, "resolve", side_effect=resolve),
            patch.object(manual_tools.manual_artifacts, "create_staging_directory", return_value=stage),
            patch.object(manual_tools.manual_artifacts, "publish", side_effect=publish),
            patch.object(manual_tools.manual_artifacts, "activate"),
            patch.object(manual_tools, "_publish_completed_voice_clips") as completed,
            patch.object(manual_tools, "generate_voice_parts") as generate,
            patch.object(manual_tools, "voice_signature", return_value=expected),
            patch.object(manual_tools, "_update_files"),
            patch.object(manual_tools.editor_documents, "mark_voice_clips_ready") as ready,
        ):
            manual_tools._run_voice(video, SimpleNamespace(update=Mock()))
        if change_voice:
            assert generate.call_args.kwargs["segment_indices"] == [1, 2]
        else:
            generate.assert_not_called()
        assert completed.call_count == 2
        ready.assert_called_once()


def test_multispeaker_published_voice_stays_active_after_timing_only_reorder():
    from haizflow.pipeline import manual_tools
    video = SimpleNamespace(video_id="retimed", active_artifacts={"subtitle_document": "current"})
    voice = {"signature": "voice", "inputs": ["subtitle_document:original"]}
    original = [dict(segment_id="a", start=0, end=1, text="Một"),
                dict(segment_id="b", start=1, end=2, text="Hai")]
    current = [dict(original[1], start=4, end=6), dict(original[0], start=8, end=10)]
    with (
        patch.object(manual_tools, "published_voice_record", return_value=voice),
        patch.object(manual_tools.manual_artifacts, "peek", side_effect=lambda _id, _kind, key: {"rows": current if key == "current" else original}),
        patch.object(manual_tools, "_record_segments", side_effect=lambda record: record["rows"]),
    ):
        assert manual_tools.active_voice_record(video) is voice
        current[0]["text"] = "Đã đổi nội dung"
        assert manual_tools.active_voice_record(video) is None


@pytest.mark.parametrize("single_fails", [False, True])
def test_old_engine_invalid_batch_recovers_only_missing_clips_and_stops_on_single_failure(tmp_path, single_fails):
    outputs = [tmp_path / f"{index}.mp3" for index in range(3)]
    calls = []
    settings = []
    encoded = []
    progress = []

    def worker(path, request, _id, callback, **kwargs):
        assert json.loads(path.read_text(encoding="utf-8"))["items"] == request["items"]
        calls.append([item["text"] for item in request["items"]])
        settings.append((request["voice_seed"], request["inference_steps"], request["device"]))
        if len(request["items"]) > 1:
            Path(request["items"][0]["wav_path"]).write_bytes(b"RIFF" + bytes(256))
            callback(1, 3, "synthesizing")
            return 1, "RuntimeError: OmniVoice returned empty or invalid audio."
        if single_fails:
            return 1, "RuntimeError: OmniVoice returned empty or invalid audio."
        Path(request["items"][0]["wav_path"]).write_bytes(b"RIFF" + bytes(256))
        callback(1, 1, "synthesizing")
        return 0, ""

    def encode(_wav, output, _id):
        encoded.append(output)
        output.write_bytes(b"valid-mp3")

    from pathlib import Path
    with (
        patch.object(voice, "_prepare_isolated_runtime"),
        patch.object(voice, "verify_omnivoice_model", return_value=tmp_path),
        patch.object(voice, "_sdk_root", return_value=tmp_path),
        patch.object(voice, "_run_persistent_worker_process", side_effect=worker),
        patch.object(voice, "_run_worker_process", side_effect=AssertionError("No broad retry")),
        patch.object(voice, "_encode_mp3", side_effect=encode),
        patch.object(voice, "log_to_video"),
    ):
        args = [dict(text=str(index), voice="omnivoice:bright", output_path=str(output))
                for index, output in enumerate(outputs)]
        kwargs = dict(language_id="vi", device="gpu", inference_steps=32, keep_worker_warm=True,
                      progress_callback=lambda completed, total, stage: progress.append((completed, total)))
        if single_fails:
            with pytest.raises(RuntimeError, match="empty or invalid audio"):
                voice.synthesize_batch_to_mp3(args, "old-pack", **kwargs)
        else:
            voice.synthesize_batch_to_mp3(args, "old-pack", **kwargs)
    assert calls == [["0", "1", "2"], ["1"]] + ([] if single_fails else [["2"]])
    assert len(set(settings)) == 1
    assert settings[0][1:] == (32, "cuda:0")
    assert encoded == outputs[:1] if single_fails else encoded == outputs
    assert all(total == 3 for _, total in progress)
    assert progress[-1][0] == (1 if single_fails else 3)

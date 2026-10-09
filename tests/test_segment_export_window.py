"""Bounded render integration: never materialize the complete editor sequence."""

import json
import subprocess
import threading
import wave
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from haizflow.pipeline import audio_timeline, manual_tools, render, segment_export
from haizflow.schemas.editor import EditorAsset, EditorClip, EditorDocument, EditorSequence, EditorTrack, SourceEditDecision
from haizflow.schemas.video import VideoConfig
from haizflow.services import editor_documents, video_export, video_store
from haizflow.utils.ffmpeg import _binary, get_video_duration, get_media_stream_types


def document_for(duration=4000):
    return EditorDocument(video_id="bounded-export", sequence=EditorSequence(duration_ms=duration,
        edit_decisions=[SourceEditDecision(decision_id="source", source_start_ms=0,
                                          source_end_ms=duration, sequence_start_ms=0)]),
        tracks=[EditorTrack(track_id="source-video", kind="source_video", name="Nguồn"),
                EditorTrack(track_id="source-audio", kind="source_audio", name="Âm thanh")],
        clips=[EditorClip(clip_id="source", track_id="source-video", kind="source_video", duration_ms=duration),
               EditorClip(clip_id="audio", track_id="source-audio", kind="audio", duration_ms=duration)])


def test_intersection_keeps_original_coordinates_and_does_not_change_document():
    document = document_for(1800000)
    before = document.model_dump()
    assert segment_export.source_spans(document, 1200000, 1380000) == [(1200000, 1380000, 1200000)]
    assert document.model_dump() == before
    document.sequence.edit_decisions = [
        SourceEditDecision(decision_id="first", source_start_ms=3000, source_end_ms=5000, sequence_start_ms=0),
        SourceEditDecision(decision_id="second", source_start_ms=7000, source_end_ms=10000, sequence_start_ms=3000)]
    assert segment_export.source_spans(document, 1500, 4500) == [(1500, 2000, 4500), (2000, 3000, None), (3000, 4500, 7000)]


@pytest.mark.parametrize("edited", [False, True])
@pytest.mark.parametrize("window", [(0, 1500), (1500, 3000)])
def test_real_bounded_render_without_any_full_export_or_audio_cache(tmp_path, monkeypatch, edited, window):
    source = tmp_path / "source.mp4"
    subprocess.run([_binary("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i",
        "testsrc2=size=64x64:rate=20:duration=4", "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(source)], check=True, capture_output=True)
    config = VideoConfig()
    video = SimpleNamespace(**{name: getattr(config, name) for name in VideoConfig.model_fields},
        video_id="bounded-export", files={"video_input": str(source)}, active_artifacts={}, export_history=[],
        export_preset="source")
    video.project_type = "manual"
    document = document_for()
    if edited:
        document.sequence.edit_decisions = [
            SourceEditDecision(decision_id="first", source_start_ms=2000, source_end_ms=4000, sequence_start_ms=0),
            SourceEditDecision(decision_id="second", source_start_ms=0, source_end_ms=2000, sequence_start_ms=2000)]
    document.tracks += [EditorTrack(track_id="subtitles", kind="subtitle", name="Phụ đề"),
                        EditorTrack(track_id="overlays", kind="overlay", name="Hình ảnh")]
    document.assets += [EditorAsset(asset_id="source", kind="source", width=64, height=64, path=str(source)),
                        EditorAsset(asset_id="overlay", kind="video", width=64, height=64, path=str(source))]
    document.clips += [EditorClip(clip_id="cue", track_id="subtitles", kind="subtitle", name="Hello",
                                  start_ms=1000, duration_ms=2500),
                       EditorClip(clip_id="overlay", track_id="overlays", kind="video", asset_id="overlay",
                                  start_ms=1000, duration_ms=2500, fade_in_ms=200, fade_out_ms=200),
                       EditorClip(clip_id="outside", track_id="overlays", kind="video", asset_id="overlay",
                                  start_ms=3500, duration_ms=500)]
    before = document.model_dump()
    monkeypatch.setattr(video_store, "get_video_dir", lambda _id: str(tmp_path))
    monkeypatch.setattr(manual_tools.manual_artifacts, "resolve", lambda *_args: None)
    monkeypatch.setattr(manual_tools, "published_voice_record", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(manual_tools, "_audio_background", lambda _video, **_kwargs: (str(source), "", []))
    monkeypatch.setattr(manual_tools, "audio_signature", lambda _video: "missing-mix")
    monkeypatch.setattr(manual_tools, "_ocr_region", lambda _video: None)
    whole_render = Mock(side_effect=AssertionError("Whole export must not run"))
    monkeypatch.setattr(manual_tools, "_run_export", whole_render)
    monkeypatch.setattr(render, "preferred_video_encoder", lambda *_args: (
        "libx264", ["-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p"]))
    original = manual_tools.render_video
    calls = []

    def capture(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(manual_tools, "render_video", capture)
    progress = []
    output = tmp_path / "result.mp4"
    segment_export.render_segment(video, document, window, output, threading.Event(), progress.append)
    assert abs(get_video_duration(str(output)) - 1.5) < .1
    assert set(get_media_stream_types(str(output))) >= {"video", "audio"}
    expected_source_start = (2 if window[0] == 0 else 0) if edited else window[0] / 1000
    assert calls[0]["source_start_seconds"] == expected_source_start
    assert calls[0]["source_duration_seconds"] == 1.5
    assert calls[0]["subtitle_timeline_offset_seconds"] == window[0] / 1000
    assert progress == sorted(progress) and progress[-1] == 98
    assert document.model_dump() == before
    whole_render.assert_not_called()


def test_audio_cut_keeps_full_voice_slot_then_crops_audio_instead_of_refitting(tmp_path, monkeypatch):
    from haizflow.utils.audio import AudioSegment

    path = tmp_path / "segments.json"
    path.write_text(json.dumps([{"start": 1, "end": 3, "_voice_enabled": True}]))
    parts = tmp_path / "parts"
    parts.mkdir()
    (parts / "voice_0001.mp3").write_bytes(b"mock")
    monkeypatch.setattr(audio_timeline, "get_video_duration", lambda _path: 30 * 60)
    sound = AudioSegment.silent(duration=2000, frame_rate=48000).set_channels(2)
    monkeypatch.setattr(AudioSegment, "from_file", lambda *_args, **_kwargs: sound)
    monkeypatch.setattr(audio_timeline, "trim_silence", lambda value: value)
    fitter = Mock(side_effect=AssertionError("Must not squeeze the full line into the cut"))
    monkeypatch.setattr(audio_timeline, "compress_to_fit", fitter)
    output = tmp_path / "cut.wav"
    audio_timeline.build_audio_timeline(str(path), str(parts), "source.mp4", str(output), "audio-window",
        range_ms=(1500, 2500), timeline_duration_ms=1800000, require_background_audio=False)
    with wave.open(str(output)) as reader:
        assert round(reader.getnframes() * 1000 / reader.getframerate()) == 1000
    fitter.assert_not_called()


def test_atomic_segment_export_without_full_render_releases_pins_on_cancel(tmp_path, monkeypatch):
    document = document_for()
    video = SimpleNamespace(video_id="bounded-export", active_artifacts={}, export_history=[])
    target = tmp_path / "result.mp4"
    target.write_bytes(b"old output")
    monkeypatch.setattr(video_export, "validate_export_destination", lambda value: target)
    monkeypatch.setattr(editor_documents, "load", lambda _id: document)
    monkeypatch.setattr(video_export, "render_revision", lambda _video: "unchanged")
    monkeypatch.setattr(video_export, "current_render", lambda *_args, **_kwargs: None)
    pinned, released = Mock(), Mock()
    monkeypatch.setattr(video_export.manual_artifacts, "pin_workspace", pinned)
    monkeypatch.setattr(video_export.manual_artifacts, "unpin", released)
    token = threading.Event()

    def cancelled(*_args):
        token.set()
        raise video_export.ExportCancelled()

    monkeypatch.setattr(segment_export, "render_segment", cancelled)
    with pytest.raises(video_export.ExportCancelled):
        video_export._export_editor_range(video, target, (1000, 2500), overwrite=True,
                                          cancel=token, progress=None, expected_target=None)
    assert target.read_bytes() == b"old output"
    pinned.assert_called_once()
    released.assert_called_once()
    assert not list(tmp_path.glob(".haizflow-segment-*"))

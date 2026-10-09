"""Result ranges never retime media, rerun inference, or invalidate its cache."""
import hashlib
import json
import subprocess
import threading
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.schemas.editor import EditorClip, EditorDocument, EditorSequence, EditorTrack
from haizflow.services import editor_documents, result_segments, video_export
from haizflow.utils.ffmpeg import _binary, get_video_duration, get_media_stream_types


def make_document():
    document = EditorDocument(video_id="result-test", sequence=EditorSequence(duration_ms=4000),
        tracks=[EditorTrack(track_id="voice", kind="voice", name="Giọng đọc")],
        clips=[EditorClip(clip_id="voice-1", track_id="voice", kind="voice",
                         start_ms=750, duration_ms=2000, asset_id="published-voice")])
    result_segments.ensure(document)
    return document


def host_for(document):
    host = SimpleNamespace(_manual_editor_document=SimpleNamespace(document_object=document, clearSelection=Mock()),
                           _editor_track_locked=lambda *_args: False)

    def mutate(_label, callback, **_kwargs):
        before = document.model_dump()
        callback(document)
        document.revision += int(before != document.model_dump())
        return before != document.model_dump()

    host._apply_editor_mutation = mutate
    return host


def test_split_trim_delete_keep_other_tracks_clock_and_render_identity():
    document = make_document()
    before = result_segments.render_payload(document)
    voice = document.clips[0].model_dump()
    host = host_for(document)
    assert HaizFlowController.splitResultClip(host, "result-1", 2000)
    assert not HaizFlowController.splitResultClip(host, "result-1", 40)
    ranges = result_segments.ranges(document)
    assert [(item["startMs"], item["endMs"]) for item in ranges] == [(0, 2000), (2000, 4000)]
    second = ranges[1]["id"]
    assert HaizFlowController.trimClip(host, second, "left", 2500)
    assert HaizFlowController.trimClip(host, "result-1", "right", 1500)
    assert not HaizFlowController.moveClip(host, second, 0)
    assert not HaizFlowController.trimClip(host, second, "right", 10000)  # Already at its bounded end.
    assert result_segments.ranges(document)[1]["endMs"] == 4000
    assert document.sequence.duration_ms == 4000
    assert document.clips[0].model_dump() == voice
    assert result_segments.render_payload(document) == before
    assert HaizFlowController.removeClips(host, [second], False)
    assert result_segments.render_payload(document) == before
    assert len(result_segments.ranges(document)) == 1


def test_ranges_survive_save_reload_and_empty_track_is_not_recreated(tmp_path, monkeypatch):
    document = make_document()
    assert result_segments.split(document, "result-1", 1500, "second")
    path = tmp_path / "document.json"
    monkeypatch.setattr(editor_documents, "document_path", lambda _id: path)
    monkeypatch.setattr(editor_documents.video_store, "update_video", Mock())
    video = SimpleNamespace(video_id=document.video_id)
    editor_documents.save(video, document)
    loaded = editor_documents.load(video.video_id)
    assert result_segments.ranges(loaded) == result_segments.ranges(document)
    loaded.clips = [clip for clip in loaded.clips if clip.kind != "result"]
    assert not result_segments.ensure(loaded)
    assert result_segments.ranges(loaded) == []


@pytest.fixture
def composed_source(tmp_path):
    source = tmp_path / "composed.mp4"
    subprocess.run([_binary("ffmpeg"), "-y", "-v", "error",
        "-f", "lavfi", "-i", "color=c=red:s=64x64:r=20:d=2",
        "-f", "lavfi", "-i", "color=c=blue:s=64x64:r=20:d=2",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=4",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
        "-map", "[v]", "-map", "2:a", "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac", str(source)], check=True, capture_output=True)
    return source


def test_segment_export_is_frame_accurate_atomic_and_keeps_render(composed_source, tmp_path, monkeypatch):
    source = composed_source
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    marker = tmp_path / "complete.json"
    marker.write_text(json.dumps({"outputs": {"video": {"sha256": digest}}}))
    video = SimpleNamespace(video_id="segment-export", export_preset="source", export_history=[])
    record = {"signature": "render", "resolved_outputs": {"video": str(source)}}

    @contextmanager
    def lease(_video):
        yield record

    monkeypatch.setattr(video_export, "render_lease", lease)
    monkeypatch.setattr(video_export, "validate_export_destination", lambda value: tmp_path / str(value))
    monkeypatch.setattr(video_export, "current_render", lambda _video: record)
    monkeypatch.setattr(video_export.manual_artifacts, "artifact_directory", lambda *_args: tmp_path)
    updates = Mock()
    monkeypatch.setattr(video_export.video_store, "update_video", updates)
    target = tmp_path / "segment.mp4"
    progress = []
    video_export.export_video(video, target, range_ms=(1500, 3000), progress=progress.append)
    assert abs(get_video_duration(str(target)) - 1.5) < .1
    assert set(get_media_stream_types(str(target))) >= {"video", "audio"}
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
    assert progress[-1] == 100 and progress == sorted(progress)
    history = updates.call_args.kwargs["export_history"][-1]
    assert history["range_ms"] == [1500, 3000]

    def pixel(time):
        return subprocess.run([_binary("ffmpeg"), "-v", "error", "-ss", str(time), "-i", str(target),
            "-frames:v", "1", "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
            check=True, capture_output=True).stdout

    assert pixel(.1)[0] > 200 and pixel(.1)[2] < 30
    assert pixel(1.3)[2] > 200 and pixel(1.3)[0] < 30
    old = target.read_bytes()
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(video_export.ExportCancelled):
        video_export.export_video(video, target, overwrite=True, range_ms=(0, 2000), cancel=cancelled)
    assert target.read_bytes() == old
    with pytest.raises(ValueError):
        video_export.export_video(video, tmp_path / "invalid.mp4", range_ms=(0, 10000))
    assert not list(tmp_path.glob(".haizflow-export-*"))


def test_undo_payload_restores_result_ranges_without_retouching_other_clips():
    document = make_document()
    before = deepcopy(document.model_dump())
    result_segments.split(document, "result-1", 2000, "second")
    restored = EditorDocument.model_validate(before)
    assert result_segments.ranges(restored) == [{"id": "result-1", "startMs": 0, "endMs": 4000}]
    assert restored.clips[0].model_dump() == document.clips[0].model_dump()

"""A cached render's clock must be mapped from the unchanged editor clock."""

import subprocess
import threading
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest

import test_render_export_storage as storage_tests
from hflow.pipeline import segment_export
from hflow.schemas.editor import EditorDocument, EditorSequence
from hflow.services import editor_documents, manual_artifacts, video_export, video_store
from hflow.utils.ffmpeg import _binary, get_video_duration


@pytest.fixture
def storage():
    fixture = storage_tests.RenderExportStorageTests()
    fixture.setUpClass()
    fixture.setUp()
    try:
        yield fixture
    finally:
        fixture.tearDown()


@pytest.mark.parametrize("speed", [.5, 1, 2, 3])
def test_cached_export_original_40_to_50_is_red_and_has_scaled_duration(storage, monkeypatch, speed):
    _, video = storage.make_video(kind="manual")
    source = Path(video.files["video_input"])
    subprocess.run([_binary("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i",
        "color=blue:size=96x64:rate=10:duration=60,drawbox=color=red:t=fill:enable='gte(t,40)*lt(t,50)'",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=60",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(source)], check=True, capture_output=True)
    video = video_store.update_video(video.video_id, output_speed=speed)
    expected = video_export.render_revision(video)
    staging = manual_artifacts.create_staging_directory(video.video_id, "export")
    composed = staging / "video.mp4"
    subprocess.run([_binary("ffmpeg"), "-y", "-v", "error", "-i", str(source),
        "-vf", f"setpts=(PTS-STARTPTS)/{speed}", "-af", f"atempo={speed}", "-t", str(60 / speed),
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(composed)], check=True, capture_output=True)
    record = manual_artifacts.publish(video.video_id, "export", expected, staging,
                                     {"video": "video.mp4"}, config_fingerprint=expected)
    video = video_store.get_video(video.video_id)
    document = EditorDocument(video_id=video.video_id, sequence=EditorSequence(duration_ms=60000))
    monkeypatch.setattr(editor_documents, "load", lambda _: document)
    monkeypatch.setattr(video_export, "render_revision", lambda _: expected)
    monkeypatch.setattr(segment_export, "render_segment", Mock(side_effect=AssertionError("Must reuse full render cache")))
    before = Path(record["resolved_outputs"]["video"]).read_bytes()
    output = storage.external / "range.mp4"
    progress = []
    video_export.export_video(video, output, range_ms=(40000, 50000), cancel=threading.Event(), progress=progress.append)
    assert get_video_duration(str(output)) == pytest.approx(10 / speed, abs=.15)
    pixels = subprocess.check_output([_binary("ffmpeg"), "-v", "error", "-ss", str(3 / speed),
        "-i", str(output), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
    frame = np.frombuffer(pixels, np.uint8).reshape(64, 96, 3)
    assert frame[:, :, 0].mean() > 200 and frame[:, :, 2].mean() < 25
    assert progress == sorted(progress) and progress[-1] == 100
    saved = video_store.get_video(video.video_id)
    assert saved.export_history[-1]["range_ms"] == [40000, 50000]
    assert Path(record["resolved_outputs"]["video"]).read_bytes() == before
    assert not manual_artifacts._RUNTIME_PINS


@pytest.mark.parametrize("speed", [0, -1, float("nan"), float("inf"), 4])
def test_invalid_cached_clock_never_starts_encoder(monkeypatch, speed):
    launch = Mock(side_effect=AssertionError("No encoder for invalid speed"))
    monkeypatch.setattr(video_export.subprocess, "Popen", launch)
    with pytest.raises(ValueError, match="Output speed"):
        video_export._render_range(Path("missing.mp4"), Path("unused.mp4"), (40000, 50000),
                                  "source", threading.Event(), None, timeline_speed=speed)

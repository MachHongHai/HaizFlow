"""Preview refreshes retain independent caption and narration caches."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pytest
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from haizflow.desktop import subtitle_overlay_renderer as caption_renderer
from haizflow.desktop.manual_preview_audio_controller import ManualPreviewAudioController
from haizflow.desktop.subtitle_overlay_renderer import SubtitleOverlayRenderer, rasterize, sprite_key
from haizflow.schemas.editor import EditorClip, EditorDocument, EditorTrack


@pytest.fixture(scope="module", autouse=True)
def gui():
    app = QGuiApplication.instance() or QGuiApplication([])
    yield app


def test_same_caption_cache_survives_reconfigure_and_project_reopen():
    renderer = SubtitleOverlayRenderer()
    event = dict(start=1, end=4, body="Caption", header="header", layout={"fontSize": 60})
    key = renderer._event_key(event)
    renderer._cache[key] = {"normal": "cached.png"}
    try:
        with patch.object(renderer, "_submit") as submit:
            for generation in range(1, 4):
                renderer.release()
                renderer._time = 2
                renderer._accept(("events", renderer._generation, "header", [event]))
                assert renderer.frame["normal"] == "cached.png"
                renderer.seek(3.99)
                assert renderer.frame["text"] == "Caption"
                submit.assert_not_called()
                renderer.seek(4)
                assert not renderer.frame
    finally:
        renderer.close()


def test_real_renderer_refresh_reuses_warm_captions_without_another_raster_job(tmp_path):
    renderer = SubtitleOverlayRenderer()
    renderer._root = tmp_path
    layout = dict(outputWidth=360, outputHeight=640, layoutWidth=300, layoutHeight=90,
                  fontSize=32, outline=2, positionXPercent=50, positionYPercent=80,
                  fontFamily="Bangers")
    segments = [dict(start=0, end=2, text="Xin chào!"), dict(start=2, end=4, text="Hẹn gặp lại!")]

    def wait_until(predicate):
        for _ in range(500):
            if predicate():
                return
            QTest.qWait(10)
        pytest.fail("Caption worker did not finish")

    try:
        with patch.object(caption_renderer, "rasterize", wraps=rasterize) as raster:
            renderer.configure(json.dumps(segments), json.dumps(layout), True)
            wait_until(lambda: renderer.frame and not renderer._pending)
            count = raster.call_count
            assert count >= 2, renderer._events
            # A fresh document revision with the same caption content must not
            # launch another FFmpeg process. Both cached cues remain visible.
            for segment in segments:
                segment["revision"] = 2
            generation = renderer._generation
            renderer.configure(json.dumps(segments), json.dumps(layout), True)
            assert renderer._generation == generation
            assert renderer.frame["normal"]
            renderer.release()
            renderer.configure(json.dumps(segments), json.dumps(layout), True)
            wait_until(lambda: not renderer._reconfiguring)
            for seconds in (0.1, 1.99, 2.01, 3.99, 0.5):
                renderer.seek(seconds)
                assert renderer.frame["normal"]
            assert raster.call_count == count
    finally:
        renderer.close()


def test_stale_caption_job_cannot_replace_current_cue_or_poison_cache():
    renderer = SubtitleOverlayRenderer()
    old = dict(start=0, end=3, body="old", header="header", layout={})
    new = dict(old, body="new")
    try:
        renderer._generation = 2
        renderer._events = [new]
        renderer._cache[renderer._event_key(new)] = {"normal": "new.png"}
        with patch.object(renderer, "_submit") as submit:
            renderer.seek(1)
            renderer._accept(("frame", (1, renderer._event_key(old)), {"normal": "old.png"}))
            assert renderer.frame["normal"] == "new.png"
            submit.assert_not_called()
        assert renderer._event_key(old) != renderer._event_key(new)
        assert sprite_key("header", "new", {"fontSize": 60}) != sprite_key(
            "header", "new", {"fontSize": 80})
    finally:
        renderer.close()


def test_short_cues_prefetch_bounded_horizon_not_only_two_cues():
    renderer = SubtitleOverlayRenderer()
    renderer._events = [dict(start=i * .25, end=(i + 1) * .25, body=str(i)) for i in range(80)]
    renderer._cache[renderer._event_key(renderer._events[0])] = {"normal": "cached.png"}
    try:
        with patch.object(renderer, "_request_frame") as request:
            renderer.seek(.1)
            assert request.call_count == 12
            assert all(call.args[0]["start"] <= 8.1 for call in request.call_args_list)
    finally:
        renderer.close()


def test_seek_cancels_obsolete_queued_caption_prefetch():
    renderer = SubtitleOverlayRenderer()
    renderer._events = [dict(start=100, end=104, body="current")]
    obsolete = Mock()
    obsolete.cancel.return_value = True
    renderer._frame_futures[(0, "obsolete")] = obsolete
    renderer._pending.add((0, "obsolete"))
    try:
        with patch.object(renderer, "_request_frame") as request:
            renderer.seek(101)
            obsolete.cancel.assert_called_once()
            assert (0, "obsolete") not in renderer._pending
            request.assert_called_once_with(renderer._events[0])
    finally:
        renderer.close()


def test_corrupt_caption_marker_is_rebuilt_instead_of_hiding_cue(tmp_path):
    layout = dict(outputWidth=320, outputHeight=240, layoutWidth=240, layoutHeight=40,
                  fontSize=24, outline=2, positionXPercent=50, positionYPercent=80)
    # Minimal ASS is sufficient here: FFmpeg itself is stubbed, image creation
    # still exercises the real cache publication/metadata path.
    directory = tmp_path / sprite_key("header", "body", layout)[:24]
    directory.mkdir()
    (directory / "complete.json").write_text('{"normal":', encoding="utf-8")

    def output(*args, **kwargs):
        from PIL import Image, ImageDraw
        for name in ("normal", "karaoke"):
            image = Image.new("RGBA", (320, 240))
            ImageDraw.Draw(image).rectangle((10, 10, 50, 25), fill="white")
            image.save(directory / f"{name}.png")

    with patch("haizflow.desktop.subtitle_overlay_renderer.subprocess.run", side_effect=output):
        frame = rasterize("header", "body", layout, tmp_path)
    assert frame["width"] > 0
    assert json.loads((directory / "complete.json").read_text())["normal"] == frame["normal"]


def test_visual_refresh_keeps_published_voice_pcm_without_restart():
    segment = dict(segment_id="a", text="Xin chào", start=1, end=3)
    document = EditorDocument(video_id="video", tracks=[
        EditorTrack(track_id="voice", kind="voice", name="Voice"),
    ], clips=[
        EditorClip(clip_id="sub-a", track_id="subtitles", kind="subtitle", segment_id="a",
                   name="Xin chào", start_ms=1000, duration_ms=2000,
                   metadata={"segment_payload": dict(segment)}),
        EditorClip(clip_id="voice-a", track_id="voice", kind="voice", segment_id="a",
                   start_ms=1000, duration_ms=2000),
    ])
    video = SimpleNamespace(video_id="video", project_type="manual", enable_audio_separation=False,
                            files={}, active_artifacts={})
    audio = ManualPreviewAudioController()
    future = Mock()
    future.cancel.return_value = True
    try:
        with (
            patch("haizflow.services.editor_documents.load", return_value=document),
            patch("haizflow.pipeline.manual_tools.published_voice_record", return_value={
                "signature": "published", "resolved_outputs": {},
            }),
            patch.object(audio._executor, "submit", return_value=future) as submit,
        ):
            audio.request(video, [segment])
            tracks = [dict(id="a", kind="voice", text="Xin chào", signature="published",
                           start=48000, samples=np.ones((100, 2), dtype=np.int16))]
            audio._accept((audio._generation, tracks, ""))
            generation = audio._generation
            document.revision += 1
            document.clips[0].metadata["segment_payload"].update(
                _style={"font_size": 90}, revision=7, ocr_region={"x": 10})
            document.clips[1].transform.position_x_percent = 70
            document.clips[1].metadata["last_preview_refresh"] = "ocr"
            document.tracks[0].locked = True
            video.files["ocr_region"] = "new-region.json"
            audio.request(video, [segment])
            assert audio._generation == generation
            assert not audio.busy
            assert audio._tracks is tracks
            assert not audio._muted_ids
            submit.assert_called_once()
            # An actual audio timeline edit still invalidates the mix.
            document.clips[1].start_ms = 1500
            audio.request(video, [segment])
            assert audio._generation == generation + 1
            assert submit.call_count == 2
    finally:
        audio.close()


def test_replaced_audio_at_same_path_refreshes_pcm_identity(tmp_path):
    source = tmp_path / "source.wav"
    source.write_bytes(b"old")
    video = SimpleNamespace(video_id="video", project_type="manual", enable_audio_separation=False,
                            files={"source_audio": str(source)}, active_artifacts={})
    audio = ManualPreviewAudioController()
    try:
        with (
            patch("haizflow.services.editor_documents.load", return_value=None),
            patch("haizflow.pipeline.manual_tools.published_voice_record", return_value=None),
            patch.object(audio._executor, "submit") as submit,
        ):
            audio.request(video, [])
            source.write_bytes(b"new longer audio")
            audio.request(video, [])
            assert submit.call_count == 2
    finally:
        audio.close()


def test_caption_visibility_uses_timeline_and_already_mapped_audio_clock():
    workspace = (Path(__file__).parents[1] / "src/haizflow/desktop/qml/ManualWorkspace.qml").read_text(
        encoding="utf-8")
    assert "Math.min(segment.end, timing.end)" not in workspace
    assert "subtitleOverlayRenderer.seek(AppController.manualPreviewAudio.positionSeconds)" in workspace

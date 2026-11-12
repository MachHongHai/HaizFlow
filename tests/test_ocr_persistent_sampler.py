import subprocess
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest
from PIL import Image

from haizflow.pipeline import subtitle_ocr
from haizflow.pipeline.process_registry import clean_video, cancel_video
from haizflow.utils.ffmpeg import _binary, get_video_duration


def ffmpeg(*args):
    return subprocess.run([_binary("ffmpeg"), "-y", "-v", "error", *map(str, args)],
                          check=True, capture_output=True, timeout=45)


@pytest.fixture
def media(tmp_path):
    source = tmp_path / "video.mp4"
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=20:duration=3",
           "-c:v", "libx264", "-g", "20", "-bf", "2", source)
    return source


@pytest.mark.parametrize("offset", [0, 3])
def test_reusable_decoder_matches_accurate_ffmpeg_seeks(media, tmp_path, offset):
    source = media
    if offset:
        source = tmp_path / "offset.mp4"
        ffmpeg("-i", media, "-c", "copy", "-output_ts_offset", offset, source)
    original = source.read_bytes()
    samples = subtitle_ocr._sample_frames_with_av(str(source), str(tmp_path), "native-sampling",
        duration=3, ocr_width=160, ocr_height=90, sample_count=6)
    assert len(samples) == 6
    for index, sample in enumerate(samples):
        reference = tmp_path / f"reference-{index}.jpg"
        ffmpeg("-ss", f"{(index + .5) * 3 / 6:.6f}", "-threads", "2", "-i", source,
               "-vf", "scale=160:90", "-frames:v", "1", "-q:v", "4", reference)
        with Image.open(sample) as image, Image.open(reference) as expected:
            assert image.size == (160, 90)
            difference = np.abs(np.asarray(image, dtype=np.float32) - np.asarray(expected, dtype=np.float32))
        assert np.mean(difference) < 6, (index, offset, np.mean(difference))
    assert source.read_bytes() == original
    # Closing the container releases Windows handles, not only decoder memory.
    moved = source.with_suffix(".moved")
    source.rename(moved)
    moved.rename(source)


def test_long_sampler_uses_one_container_and_no_ffmpeg_process(media, tmp_path, monkeypatch):
    import av
    opened = Mock(wraps=av.open)
    monkeypatch.setattr(av, "open", opened)
    monkeypatch.setattr(subtitle_ocr, "OCR_SEEK_MIN_DURATION", 0)
    monkeypatch.setattr(subtitle_ocr, "log_to_video", Mock())
    launch = Mock(wraps=subprocess.Popen)
    monkeypatch.setattr(subtitle_ocr.subprocess, "Popen", launch)
    frames = subtitle_ocr._sample_frames(str(media), str(tmp_path), "reuse", duration=3,
        source_width=320, source_height=180, ocr_width=160, ocr_height=90, sample_count=12)
    assert len(frames) == 12
    assert opened.call_count == 1 and launch.call_count == 1
    assert "ffprobe" in Path(launch.call_args.args[0][0]).name
    assert not list(tmp_path.glob(".seek-*"))


def test_unicode_source_and_frame_paths_release_cleanly(media, tmp_path):
    folder = tmp_path / "Video tiếng Việt 日本語"
    folder.mkdir()
    source = folder / "phụ đề 中文.mp4"
    media.rename(source)
    frames = subtitle_ocr._sample_frames_with_av(str(source), str(folder), "unicode",
        duration=3, ocr_width=160, ocr_height=90, sample_count=6)
    assert len(frames) == 6
    for path in frames:
        with Image.open(path) as image:
            image.verify()
    source.rename(media)


def test_audio_tail_does_not_create_repeated_fake_frames(media, tmp_path):
    source = tmp_path / "audio-tail.mp4"
    ffmpeg("-i", media, "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo:d=6",
           "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", source)
    assert get_video_duration(str(source)) > 5
    frames = subtitle_ocr._sample_frames_with_av(str(source), str(tmp_path), "tail",
        duration=6, ocr_width=160, ocr_height=90, sample_count=12)
    assert len(frames) == 6
    assert [item.name for item in frames] == [f"frame-{i:03d}.jpg" for i in range(1, 7)]


def test_variable_frame_rate_preserves_presentation_time_sampling(media, tmp_path):
    source = tmp_path / "variable.mp4"
    ffmpeg("-i", media, "-vf", "select='lt(n,20)+gte(n,20)*not(mod(n,3))'",
           "-fps_mode", "vfr", "-c:v", "libx264", "-g", "20", source)
    paths = subtitle_ocr._sample_frames_with_av(str(source), str(tmp_path), "variable",
        duration=3, ocr_width=160, ocr_height=90, sample_count=6)
    assert len(paths) == 6
    for index, path in enumerate(paths):
        expected = tmp_path / f"expected-{index}.jpg"
        ffmpeg("-ss", f"{(index + .5) * .5:.6f}", "-i", source,
               "-vf", "scale=160:90", "-frames:v", "1", "-q:v", "4", expected)
        with Image.open(path) as observed, Image.open(expected) as reference:
            delta = np.abs(np.asarray(observed, dtype=np.float32) - np.asarray(reference, dtype=np.float32))
        assert np.mean(delta) < 6


def test_rotated_source_preserves_ffmpeg_autorotation_fallback(media, tmp_path, monkeypatch):
    source = tmp_path / "rotated.mp4"
    ffmpeg("-display_rotation:v:0", "90", "-i", media, "-c", "copy", source)
    with pytest.raises(subtitle_ocr._SamplingUnavailable, match="transform"):
        subtitle_ocr._sample_frames_with_av(str(source), str(tmp_path), "rotation",
            duration=3, ocr_width=90, ocr_height=160, sample_count=6)
    monkeypatch.setattr(subtitle_ocr, "OCR_SEEK_MIN_DURATION", 0)
    monkeypatch.setattr(subtitle_ocr, "log_to_video", Mock())
    target = tmp_path / "compatible"
    target.mkdir()
    frames = subtitle_ocr._sample_frames(str(source), str(target), "rotation", duration=3,
        source_width=1280, source_height=720, ocr_width=90, ocr_height=160, sample_count=6)
    assert len(frames) == 6
    assert not list(target.glob(".seek-*"))
    with Image.open(frames[0]) as image:
        assert image.size == (90, 160)


def test_cancellation_inside_native_decoder_never_enters_fallback(media, tmp_path, monkeypatch):
    import av
    identifier = "native-cancel"
    checks = [0]
    def checkpoint(key):
        checks[0] += 1
        if checks[0] == 5:
            cancel_video(key)
        from haizflow.pipeline.process_registry import check_cancellation
        check_cancellation(key)
    monkeypatch.setattr(subtitle_ocr, "check_cancellation", checkpoint)
    monkeypatch.setattr(subtitle_ocr, "OCR_SEEK_MIN_DURATION", 0)
    launch = Mock(wraps=subprocess.Popen)
    monkeypatch.setattr(subtitle_ocr.subprocess, "Popen", launch)
    try:
        with pytest.raises(RuntimeError, match="cancelled"):
            subtitle_ocr._sample_frames(str(media), str(tmp_path), identifier, duration=3,
                source_width=320, source_height=180, ocr_width=160, ocr_height=90, sample_count=12)
        assert launch.call_count == 1
        assert "ffprobe" in Path(launch.call_args.args[0][0]).name
        assert not list(tmp_path.glob(".seek-*"))
        renamed = media.with_suffix(".renamed")
        media.rename(renamed)
        renamed.rename(media)
    finally:
        clean_video(identifier)


def test_identical_images_reuse_inference_but_keep_temporal_observations(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    frames = []
    for index, content in enumerate((b"frame-a", b"frame-a", b"frame-b", b"frame-a")):
        path = tmp_path / f"sample-{index}.jpg"
        path.write_bytes(content)
        frames.append(path)
    monkeypatch.setattr(subtitle_ocr, "get_video_duration", lambda _: 60)
    monkeypatch.setattr(subtitle_ocr, "get_video_dimensions", lambda _: (1280, 720))
    monkeypatch.setattr(subtitle_ocr, "_sample_frames", lambda *_a, **_kw: frames)
    monkeypatch.setattr(subtitle_ocr, "log_to_video", Mock())
    inference = Mock(side_effect=lambda path, index, *_: [subtitle_ocr.TextCandidate(
        index, 25, 75, 50, 5, path.read_text(), .95)])
    monkeypatch.setattr(subtitle_ocr, "_ocr_candidates", inference)
    region = dict(x_percent=25, y_percent=75, width_percent=50, height_percent=5)
    select = Mock(return_value=region)
    monkeypatch.setattr(subtitle_ocr, "select_subtitle_region", select)
    progress = []
    assert subtitle_ocr.detect_original_subtitle_region(str(source), str(tmp_path), "duplicate",
                                                       lambda *args: progress.append(args)) == region
    assert inference.call_count == 2
    candidates = select.call_args.args[0]
    assert [item.frame for item in candidates] == [1, 2, 3, 4]
    assert [item.text for item in candidates] == ["frame-a", "frame-a", "frame-b", "frame-a"]
    assert progress[-1] == (4, 4)
    assert not list(tmp_path.glob("*.tmp"))
    # The valid persisted cache still bypasses sampling and model startup.
    inference.reset_mock()
    assert subtitle_ocr.detect_original_subtitle_region(str(source), str(tmp_path), "duplicate") == region
    inference.assert_not_called()


def test_failed_native_attempt_does_not_mix_partial_frames_into_fallback(media, tmp_path, monkeypatch):
    def fail(_source, destination, *_args, **_kwargs):
        (Path(destination) / "frame-001.jpg").write_bytes(b"wrong partial")
        raise subtitle_ocr._SamplingUnavailable("unsupported stream")
    monkeypatch.setattr(subtitle_ocr, "_sample_frames_with_av", fail)
    monkeypatch.setattr(subtitle_ocr, "OCR_SEEK_MIN_DURATION", 0)
    monkeypatch.setattr(subtitle_ocr, "log_to_video", Mock())
    target = tmp_path / "fallback"
    target.mkdir()
    frames = subtitle_ocr._sample_frames(str(media), str(target), "fallback", duration=3,
        source_width=1280, source_height=720, ocr_width=160, ocr_height=90, sample_count=6)
    assert len(frames) == 6
    assert not list(target.glob(".seek-*"))
    for frame in frames:
        with Image.open(frame) as image:
            image.verify()


@pytest.mark.parametrize("reason", ["cancel", "replace"])
def test_interrupted_scan_does_not_replace_an_older_cache(tmp_path, monkeypatch, reason):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    cache = tmp_path / "original_subtitle_region.json"
    cache.write_text('{"version": 0, "region": {"old": true}}')
    before = cache.read_bytes()
    identifier = f"ocr-interruption-{reason}"
    monkeypatch.setattr(subtitle_ocr, "get_video_duration", lambda _: 60)
    monkeypatch.setattr(subtitle_ocr, "get_video_dimensions", lambda _: (1280, 720))
    monkeypatch.setattr(subtitle_ocr, "log_to_video", Mock())
    def sample(_source, output, *_args, **_kwargs):
        frame = Path(output) / "frame-001.jpg"
        frame.write_bytes(b"image")
        return [frame]
    monkeypatch.setattr(subtitle_ocr, "_sample_frames", sample)
    def infer(*_):
        if reason == "cancel":
            cancel_video(identifier)
        else:
            source.write_bytes(b"replaced source")
        return []
    monkeypatch.setattr(subtitle_ocr, "_ocr_candidates", infer)
    try:
        with pytest.raises(RuntimeError, match="cancelled|changed"):
            subtitle_ocr.detect_original_subtitle_region(str(source), str(tmp_path), identifier)
        assert cache.read_bytes() == before
        assert not list(tmp_path.glob("subtitle-ocr-*"))
        assert not list(tmp_path.glob("*.tmp"))
    finally:
        clean_video(identifier)

"""Long-video OCR cold start must not decode the complete source."""

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from hflow.pipeline import subtitle_ocr


@pytest.mark.parametrize("duration,width,height,seeks", [
    (1800, 3840, 2160, True), (300, 1280, 720, True),
    (60, 3840, 2160, False), (1800, 320, 180, False),
])
def test_uniform_sampling_uses_bounded_serial_seeks_only_when_worthwhile(tmp_path, monkeypatch, duration, width, height, seeks):
    commands = []

    def launch(command, **_kwargs):
        commands.append(command)
        count = int(command[command.index("-frames:v") + 1])
        for index in range(count):
            Path(command[-1].replace("%03d", f"{index + 1:03d}")).write_bytes(b"frame")
        return Mock(returncode=0)

    monkeypatch.setattr(subtitle_ocr.subprocess, "Popen", launch)
    monkeypatch.setattr(subtitle_ocr, "communicate_process", Mock(return_value=("", "")))
    frames = subtitle_ocr._sample_frames("video.mp4", str(tmp_path), "sample-test", duration=duration,
        source_width=width, source_height=height, ocr_width=720, ocr_height=404, sample_count=36)
    assert len(frames) == 36
    assert len(commands) == (36 if seeks else 1)
    if seeks:
        times = [float(command[command.index("-ss") + 1]) for command in commands]
        assert times == sorted(times) and times[0] > 0 and times[-1] < duration
        assert times == pytest.approx([(index + .5) * duration / 36 for index in range(36)], abs=1e-5)
        for command in commands:
            assert command.index("-ss") < command.index("-i")
            assert command[command.index("-threads") + 1] == "2"
            assert command[command.index("-frames:v") + 1] == "1"
            assert "fps=" not in command[command.index("-vf") + 1]


def test_existing_cache_returns_without_decoder_or_ocr(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"existing long video")
    region = {"x_percent": 10, "y_percent": 80, "width_percent": 80, "height_percent": 10}
    cache = tmp_path / "original_subtitle_region.json"
    cache.write_text(json.dumps({"version": subtitle_ocr.DETECTOR_CACHE_VERSION,
                                "source": subtitle_ocr._source_state(str(source)), "region": region}))
    before = cache.read_bytes()
    sample = Mock(side_effect=AssertionError("Must reuse OCR cache"))
    monkeypatch.setattr(subtitle_ocr, "_sample_frames", sample)
    monkeypatch.setattr(subtitle_ocr, "_ocr_candidates", Mock(side_effect=AssertionError("No OCR inference")))
    assert subtitle_ocr.detect_original_subtitle_region(str(source), str(tmp_path), "cached-test") == region
    assert cache.read_bytes() == before
    assert sample.call_count == 0


def test_cancel_between_seek_samples_never_starts_next_decoder(tmp_path, monkeypatch):
    checks = Mock(side_effect=[None, RuntimeError("cancelled")])
    monkeypatch.setattr(subtitle_ocr, "check_cancellation", checks)
    launch = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr(subtitle_ocr.subprocess, "Popen", launch)
    monkeypatch.setattr(subtitle_ocr, "communicate_process", Mock(return_value=("", "")))
    with pytest.raises(RuntimeError, match="cancelled"):
        subtitle_ocr._sample_frames("source.mp4", str(tmp_path), "cancel-test", duration=1800,
            source_width=1920, source_height=1080, ocr_width=720, ocr_height=404, sample_count=36)
    assert launch.call_count == 1


def test_missing_near_eof_frames_keep_successful_samples(tmp_path, monkeypatch):
    calls = 0

    def launch(command, **_kwargs):
        nonlocal calls
        calls += 1
        if calls <= 30:
            Path(command[-1]).write_bytes(b"available video frame")
        return Mock(returncode=0)

    monkeypatch.setattr(subtitle_ocr.subprocess, "Popen", launch)
    monkeypatch.setattr(subtitle_ocr, "communicate_process", Mock(return_value=("", "")))
    frames = subtitle_ocr._sample_frames("audio-tail.mp4", str(tmp_path), "tail-test", duration=1800,
        source_width=1920, source_height=1080, ocr_width=720, ocr_height=404, sample_count=36)
    assert len(frames) == 30 and calls == 36


def test_real_seek_sampler_produces_uniform_valid_images_and_keeps_source(tmp_path, monkeypatch):
    from PIL import Image
    from hflow.utils.ffmpeg import _binary

    source = tmp_path / "source.mp4"
    subprocess.run([_binary("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i",
        "testsrc2=size=1280x720:rate=20:duration=2", "-c:v", "libx264", "-preset", "ultrafast",
        str(source)], check=True, capture_output=True)
    original = source.read_bytes()
    frame_dir = tmp_path / "frames"
    frame_dir.mkdir()
    monkeypatch.setattr(subtitle_ocr, "OCR_SEEK_MIN_DURATION", 0)
    paths = subtitle_ocr._sample_frames(str(source), str(frame_dir), "real-sampler", duration=2,
        source_width=1280, source_height=720, ocr_width=160, ocr_height=90, sample_count=6)
    assert len(paths) == 6
    for path in paths:
        with Image.open(path) as image:
            assert image.size == (160, 90)
            image.verify()
    assert paths[0].read_bytes() != paths[-1].read_bytes()
    assert source.read_bytes() == original

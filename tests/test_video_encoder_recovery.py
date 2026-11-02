"""A busy GPU must not turn into a permanent CPU-only choice for the session."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from haizflow.utils import ffmpeg


@pytest.fixture(autouse=True)
def probes(monkeypatch):
    ffmpeg._encoder_works.cache_clear()
    monkeypatch.setattr(ffmpeg, "available_video_encoders", lambda: {"h264_nvenc"})
    yield
    ffmpeg._encoder_works.cache_clear()


def test_failed_gpu_probe_is_retried_after_short_cooldown(monkeypatch):
    clock = Mock(return_value=100.0)
    monkeypatch.setattr(ffmpeg, "monotonic", clock, raising=False)
    probe = Mock(side_effect=[SimpleNamespace(returncode=1), SimpleNamespace(returncode=0)])
    monkeypatch.setattr(ffmpeg.subprocess, "run", probe)
    assert ffmpeg.preferred_video_encoder()[0] == "libx264"
    clock.return_value = 110.0
    assert ffmpeg.preferred_video_encoder()[0] == "libx264"
    assert probe.call_count == 1  # Do not repeatedly initialize a busy GPU.
    clock.return_value = 131.0
    assert ffmpeg.preferred_video_encoder()[0] == "h264_nvenc"
    assert probe.call_count == 2


def test_successful_gpu_probe_is_reused(monkeypatch):
    clock = Mock(return_value=100.0)
    monkeypatch.setattr(ffmpeg, "monotonic", clock, raising=False)
    probe = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(ffmpeg.subprocess, "run", probe)
    assert ffmpeg.preferred_video_encoder()[0] == "h264_nvenc"
    clock.return_value = 10000.0
    assert ffmpeg.preferred_video_encoder()[0] == "h264_nvenc"
    assert probe.call_count == 1


def test_render_failure_cools_gpu_then_recovers_without_restarting_app(monkeypatch):
    clock = Mock(return_value=100.0)
    monkeypatch.setattr(ffmpeg, "monotonic", clock)
    probe = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(ffmpeg.subprocess, "run", probe)
    assert ffmpeg.preferred_video_encoder()[0] == "h264_nvenc"
    ffmpeg.mark_video_encoder_failed("h264_nvenc")
    assert ffmpeg.preferred_video_encoder()[0] == "libx264"
    assert probe.call_count == 1
    clock.return_value = 131.0
    assert ffmpeg.preferred_video_encoder()[0] == "h264_nvenc"
    assert probe.call_count == 2

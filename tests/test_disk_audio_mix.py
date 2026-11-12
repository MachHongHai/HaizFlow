from pathlib import Path
from unittest.mock import Mock

import pytest
from pydub import AudioSegment
from pydub.generators import Sine

from haizflow.pipeline.disk_audio_mix import DiskAudioMix
from haizflow.pipeline import audio_timeline


@pytest.mark.parametrize("width", [2, 4])
@pytest.mark.parametrize("rate", [24000, 48000, 96000])
def test_disk_overlay_matches_pydub_saturation_and_format_promotion(tmp_path, width, rate):
    base = Sine(300, sample_rate=48000).to_audio_segment(duration=2300).set_channels(2)
    voice = Sine(700, sample_rate=rate).to_audio_segment(duration=400).set_sample_width(width)
    expected = base.overlay(voice, position=155).overlay(voice + 8, position=162)
    with DiskAudioMix(base, tmp_path, "disk-mix") as disk:
        disk.overlay(voice, position=155).overlay(voice + 8, position=162)
        disk._stream.flush()
        assert disk.path.read_bytes() == expected.raw_data
    assert not list(tmp_path.iterdir())


def test_disk_mix_failure_cleans_private_pcm(tmp_path):
    base = AudioSegment.silent(duration=200).set_channels(2)
    with pytest.raises(RuntimeError):
        with DiskAudioMix(base, tmp_path, "cancel"):
            raise RuntimeError("cancel")
    assert not list(tmp_path.iterdir())


def test_production_long_mix_is_bit_identical_to_short_path(tmp_path, monkeypatch):
    monkeypatch.setattr(audio_timeline, "log_to_video", Mock())
    monkeypatch.setattr(audio_timeline, "get_video_duration", lambda _: 120)
    segments = tmp_path / "segments.json"
    segments.write_text('[{"start": 0.1, "end": 0.6, "text": "one"},'
                        '{"start": 119.7, "end": 120, "text": "two"}]')
    for index in (1, 2):
        with Sine(index * 500, sample_rate=24000).to_audio_segment(duration=200).export(
                tmp_path / f"voice_{index:04d}.mp3", format="wav"):
            pass
    disk_output, memory_output = tmp_path / "disk.wav", tmp_path / "memory.wav"
    audio_timeline.build_audio_timeline(str(segments), str(tmp_path), "source", str(disk_output), "test")
    audio_timeline.build_audio_timeline(str(segments), str(tmp_path), "source", str(memory_output), "test",
                                        range_ms=(0, 120000), timeline_duration_ms=120000)
    assert AudioSegment.from_file(disk_output).raw_data == AudioSegment.from_file(memory_output).raw_data
    assert not list(tmp_path.glob(".audio-*"))

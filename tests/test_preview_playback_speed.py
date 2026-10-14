"""Preview-only playback rate: bounded PCM, native audio and transport clocks."""

from types import SimpleNamespace
from unittest.mock import Mock
import time

import numpy as np
import pytest

from hflow.desktop.manual_preview_audio_controller import (
    ManualPreviewAudioController, PCM_BUFFER_FRAMES, RATE, mix_frames,
)
from hflow.desktop.preview_tempo import PreviewTempoStream


def ramp_track():
    samples = np.arange(20000, dtype=np.int16).reshape(-1, 1).repeat(2, axis=1)
    return {"id": "voice", "kind": "voice", "start": 0, "samples": samples}


@pytest.mark.parametrize("rate", [.25, .5, 1.35, 1.5, 2, 2.75, 3])
def test_real_stream_preserves_pitch_stereo_and_has_bounded_backpressure(rate):
    positions = []
    def mixer(cursor, count):
        positions.append(cursor)
        phase = (cursor + np.arange(count)) / RATE
        samples = np.column_stack((np.sin(2 * np.pi * 220 * phase),
                                   np.sin(2 * np.pi * 440 * phase)))
        return (samples * 12000).astype("<i2").tobytes()
    stream = PreviewTempoStream(mixer, 0, rate)
    try:
        chunks = []
        total = 0
        deadline = time.monotonic() + 10
        while total < RATE and time.monotonic() < deadline:
            data = stream.peek(min(4801, RATE - total))
            if data:
                # Odd frame writes must not drop queued data.
                data = data[:min(len(data), 3001 * 4)]
                chunks.append(data)
                total += len(data) // 4
                stream.consume(len(data))
            else:
                assert not stream.error
                time.sleep(.005)
        assert total == RATE, stream.error
        output = np.frombuffer(b"".join(chunks), dtype="<i2").reshape(-1, 2)
        for channel, frequency in enumerate((220, 440)):
            spectrum = abs(np.fft.rfft(output[RATE // 5:, channel]))
            peak = np.fft.rfftfreq(len(output[RATE // 5:]), 1 / RATE)[spectrum.argmax()]
            assert peak == pytest.approx(frequency, abs=2)
        time.sleep(.15)
        latest = len(positions)
        time.sleep(.15)
        assert len(positions) == latest  # producer stops, not a full-video render
        assert stream._queue.qsize() <= 8
    finally:
        stream.close()
        stream._writer.join(timeout=1)
        stream._reader.join(timeout=1)
    assert stream._process.poll() is not None
    assert not stream._writer.is_alive() and not stream._reader.is_alive()


@pytest.mark.parametrize("action", ["seek", "pause", "rate", "volume", "release", "tracks"])
def test_tempo_is_cancelled_before_transport_or_mix_changes(action):
    audio = ManualPreviewAudioController()
    tempo = Mock(error="")
    audio._tempo_stream = tempo
    audio._playing = True
    audio._playback_rate = 2
    audio._tracks = [ramp_track()]
    audio._sink = Mock()
    audio._position_seconds = 3
    try:
        if action == "seek":
            audio.seek(11)
        elif action == "pause":
            audio.synchronize(3, False, False)
        elif action == "rate":
            audio.setPlaybackRate(1.5, 3)
        elif action == "volume":
            audio.setVolumes(10, 20, 30)
        elif action == "tracks":
            audio._accept((audio._generation, [ramp_track()], ""))
        else:
            audio.release()
        tempo.close.assert_called_once()
        assert audio._tempo_stream is None
    finally:
        audio.close()


def test_one_x_pump_retains_bit_exact_mix_without_a_filter_process():
    audio = ManualPreviewAudioController()
    track = ramp_track()
    audio._tracks = [track]
    audio._playing = True
    sink = Mock()
    sink.bytesFree.return_value = 100 * 4
    sink.bufferSize.return_value = 100 * 4
    device = Mock()
    device.write.return_value = 100 * 4
    sink.start.return_value = device
    audio._sink = sink
    try:
        audio._pump()
        assert audio._tempo_stream is None
        device.write.assert_called_once_with(mix_frames([track], 0, 100, audio._volumes))
    finally:
        audio.close()


def test_normal_rate_is_bit_exact_with_existing_mixer_and_mute_is_preserved():
    track = ramp_track()
    assert mix_frames([track], 17, 100, {"voice": .7}, {"voice"}) == bytes(400)


@pytest.mark.parametrize("rate", [.25, .5, 1.35, 1.5, 2, 2.75, 3])
def test_rate_change_discards_old_queue_without_autoplay_or_cache_rebuild(rate):
    audio = ManualPreviewAudioController()
    audio._sink = Mock()
    audio._native_player = Mock()
    audio._key = "keep-cache"
    track = ramp_track()
    audio._tracks = [track]
    try:
        audio.setPlaybackRate(rate, 11.25)
        assert not audio._playing and not audio._timer.isActive()
        assert audio._cursor == round(11.25 * RATE)
        assert audio.positionSeconds == 11.25
        assert audio._key == "keep-cache" and audio._tracks == [track]
        audio._sink.reset.assert_called_once()
        audio._native_player.setPlaybackRate.assert_called_once_with(rate)
        audio._native_player.play.assert_not_called()
        audio.setPlaybackRate(rate, 12)
        audio._sink.reset.assert_called_once()
        for invalid in (0, -1, 4, float("nan"), float("inf")):
            audio.setPlaybackRate(invalid, 12)
        audio.setPlaybackRate(1, float("nan"))
        assert audio._playback_rate == rate
    finally:
        audio.close()


@pytest.mark.parametrize("rate", [.25, .5, 1, 1.35, 1.5, 2, 2.75, 3])
def test_pump_accounts_for_audible_not_buffered_timeline_at_every_rate(rate, monkeypatch):
    audio = ManualPreviewAudioController()
    queued = 0
    def write(data):
        nonlocal queued
        # Exercise partial writes with an odd number of stereo frames.
        written_frames = min(4801, len(data) // 4)
        queued += written_frames
        return written_frames * 4
    sink = Mock()
    sink.bufferSize.return_value = PCM_BUFFER_FRAMES * 4
    sink.bytesFree.side_effect = lambda: (PCM_BUFFER_FRAMES - queued) * 4
    sink.start.return_value = SimpleNamespace(write=write)
    audio._sink = sink
    audio._playing = True
    audio._playback_rate = rate
    audio._cursor = RATE * 5
    tempo = Mock(error="")
    tempo.peek.side_effect = lambda count: bytes(count * 4)
    monkeypatch.setattr("hflow.desktop.preview_tempo.PreviewTempoStream", Mock(return_value=tempo))
    try:
        audio._pump()
        assert audio._cursor == RATE * 5 + 4801 * rate
        assert audio.positionSeconds == pytest.approx(5)
        queued -= 3001
        audio._pump()
        assert audio.positionSeconds == pytest.approx(5 + 3001 * rate / RATE)
        audio.seek(2)
        assert audio.positionSeconds == 2
        assert audio._cursor == 2 * RATE
        assert audio._playback_rate == rate
    finally:
        audio.close()

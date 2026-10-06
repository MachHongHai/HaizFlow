import gc
import tempfile
import tracemalloc
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PySide6.QtGui import QGuiApplication

from haizflow.desktop.manual_preview_audio_controller import (
    RATE,
    ManualPreviewAudioController,
    apply_source_decisions,
    mix_frames,
)


def test_seven_minute_audio_uses_disk_cache_without_full_pcm_allocation():
    app = QGuiApplication.instance() or QGuiApplication([])
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "seven-minutes.wav"
        one_second = np.full((RATE, 2), 1200, dtype="<i2").tobytes()
        with wave.open(str(path), "wb") as output:
            output.setnchannels(2)
            output.setsampwidth(2)
            output.setframerate(RATE)
            for _ in range(420):
                output.writeframesraw(one_second)
        audio = ManualPreviewAudioController()
        try:
            tracemalloc.start()
            samples = audio._decode(path)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            assert isinstance(samples, np.memmap)
            assert len(samples) == RATE * 420
            assert peak < 8 * 1024**2
            assert audio._decode(path) is samples
            mapped = apply_source_decisions(samples, [{
                "source_start_ms": 0, "source_end_ms": 420_000, "sequence_start_ms": 0,
            }])
            assert np.shares_memory(mapped, samples)
            pcm = mix_frames([{"id": "source", "kind": "source", "start": 0, "samples": mapped}],
                             RATE * 419, 1920, {"source": 1.0})
            assert len(pcm) == 1920 * 4
            assert np.frombuffer(pcm, dtype="<i2")[0] == 1200
            cache_root = Path(audio._pcm_directory.name)
            del mapped, samples
        finally:
            audio.close()
            gc.collect()
            app.processEvents()
        assert not cache_root.exists()


def test_audio_preparing_state_is_generation_safe_and_blocks_silent_playback():
    app = QGuiApplication.instance() or QGuiApplication([])
    audio = ManualPreviewAudioController()
    video = SimpleNamespace(video_id="video", project_type="manual", enable_audio_separation=False, files={})
    try:
        with patch("haizflow.services.editor_documents.load", return_value=None), \
                patch("haizflow.pipeline.manual_tools.published_voice_record", return_value=None), \
                patch.object(audio._executor, "submit"):
            audio.request(video, [])
        generation = audio._generation
        assert audio.busy and audio.progress == 0
        audio.synchronize(12, True, False)
        assert not audio._playing and not audio._timer.isActive()
        audio._accept_progress((generation, .4))
        audio._accept_progress((generation, .2))
        assert audio.progress == .4
        audio._accept((generation - 1, [], ""))
        assert audio.busy
        audio._accept((generation, [], ""))
        assert not audio.busy and audio.progress == 1
        audio.release()
        assert not audio.busy and audio.progress == 0
    finally:
        audio.close()
        app.processEvents()


def test_multi_clip_source_mapping_uses_disk_allocator_and_retains_gaps():
    app = QGuiApplication.instance() or QGuiApplication([])
    audio = ManualPreviewAudioController()
    source = np.full((RATE * 4, 2), 1500, dtype="<i2")
    try:
        mapped = apply_source_decisions(source, [
            {"source_start_ms": 1000, "source_end_ms": 2000, "sequence_start_ms": 0},
            {"source_start_ms": 3000, "source_end_ms": 4000, "sequence_start_ms": 2000},
        ], allocate=audio._allocate_pcm)
        assert isinstance(mapped, np.memmap)
        assert len(mapped) == RATE * 3
        assert np.all(mapped[:RATE] == 1500)
        assert np.all(mapped[RATE:RATE * 2] == 0)
        assert np.all(mapped[RATE * 2:] == 1500)
        del mapped
    finally:
        audio.close()
        gc.collect()
        app.processEvents()

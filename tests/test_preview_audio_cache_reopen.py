"""Fast disk-cache hydration retains source checks and LRU semantics."""
import os
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from PySide6.QtGui import QGuiApplication

from haizflow.desktop.manual_preview_audio_controller import ManualPreviewAudioController


@pytest.fixture
def audio(tmp_path):
    app = QGuiApplication.instance() or QGuiApplication([])
    controller = ManualPreviewAudioController()
    controller._pcm_cache_directory = tmp_path
    yield controller
    controller.close()
    app.processEvents()


def test_disk_hit_stats_cache_once_and_does_not_rewrite_fresh_metadata(audio):
    key = ("source", 100, 1, None, False)
    cache = audio._pcm_cache_path(key)
    expected = np.arange(400, dtype="<i2").reshape(-1, 2)
    cache.write_bytes(expected.tobytes())
    original_stat = Path.stat
    calls = []

    def stat(path, *args, **kwargs):
        if path == cache:
            calls.append(path)
        return original_stat(path, *args, **kwargs)

    with patch.object(Path, "stat", stat), patch.object(Path, "touch") as touch:
        restored = audio._cached_pcm(key, audio._generation)
        assert len(calls) == 1
        touch.assert_not_called()
    np.testing.assert_array_equal(restored, expected)


def test_old_disk_hit_refreshes_lru_and_memory_hit_does_no_io(audio):
    key = ("source", 100, 1, None, False)
    cache = audio._pcm_cache_path(key)
    cache.write_bytes(bytes(400))
    previous = time.time() - 120
    os.utime(cache, (previous, previous))
    restored = audio._cached_pcm(key, audio._generation)
    assert cache.stat().st_mtime > previous + 60
    with patch.object(Path, "stat", side_effect=AssertionError("Memory hit must skip disk")):
        assert audio._cached_pcm(key, audio._generation) is restored


@pytest.mark.parametrize("contents", [b"", b"incomplete"])
def test_incomplete_disk_pcm_is_not_mapped(audio, contents):
    key = ("source", 100, 1, None, False)
    cache = audio._pcm_cache_path(key)
    cache.write_bytes(contents)
    with patch.object(audio, "_map_pcm", side_effect=AssertionError("Reject incomplete PCM")):
        assert audio._cached_pcm(key, audio._generation) is None


def test_removed_cache_file_and_directory_are_cache_misses(audio):
    key = ("source", 100, 1, None, False)
    assert audio._cached_pcm(key, audio._generation) is None
    audio._pcm_cache_path(key).mkdir()
    assert audio._cached_pcm(key, audio._generation) is None


def test_pruning_under_budget_does_not_restat_paths(audio):
    for index in range(5):
        (audio._pcm_cache_directory / f"{index}.pcm").write_bytes(bytes(400))
    with patch.object(Path, "stat", side_effect=AssertionError("Use directory-entry metadata")):
        audio._prune_disk_pcm(audio._generation)
    assert len(list(audio._pcm_cache_directory.glob("*.pcm"))) == 5


def test_pruning_keeps_recent_files_and_ignores_obsolete_generation(audio, monkeypatch):
    from haizflow.desktop import manual_preview_audio_controller as module

    monkeypatch.setattr(module, "PCM_CACHE_BUDGET_BYTES", 8)
    directory = audio._pcm_cache_directory
    for index in range(3):
        path = directory / f"{index}.pcm"
        path.write_bytes(bytes(4))
        os.utime(path, (100 + index, 100 + index))
    audio._prune_disk_pcm(audio._generation - 1)
    assert len(list(directory.glob("*.pcm"))) == 3
    audio._prune_disk_pcm(audio._generation)
    assert {path.name for path in directory.glob("*.pcm")} == {"1.pcm", "2.pcm"}

"""Indexed hot paths must preserve byte-identical audio and timeline semantics."""
import random

import numpy as np
import pytest

from haizflow.core.interval_index import IntervalIndex
from haizflow.desktop.manual_preview_audio_controller import IndexedAudioTracks, mix_frames
from haizflow.schemas.editor import EditorClip, EditorKeyframe
from haizflow.services.editor_documents import evaluate_keyframes, keyframe_index


def test_interval_index_preserves_overlap_order_and_half_open_edges():
    rng = random.Random(18)
    rows = [(0, 1000000, "long"), *[(i * 3, i * 3 + 2, i) for i in range(10000)]]
    rng.shuffle(rows)
    index = IntervalIndex(rows)
    for start in [0, 2, 3, 15003, 29999, 30000, 999999, 1000000]:
        assert index.intersect(start, start + 1) == [value for left, right, value in rows if left < start + 1 and right > start]
    assert index.intersect(0, 0) == []


def test_indexed_audio_is_byte_identical_with_overlaps_loops_fades_ducking_and_seeks():
    rng = np.random.default_rng(73)
    tracks = [{"id": str(i), "kind": "voice", "start": i * 151 - 300,
               "duration_frames": 450, "fade_in_frames": i % 17, "fade_out_frames": i % 31,
               "gain": .7, "samples": rng.integers(-10000, 10000, (600, 2), dtype=np.int16)} for i in range(60)]
    tracks += [{"id": "music", "kind": "music", "start": 0, "loop": True,
                "duck_ranges": [(i * 151, i * 151 + 220) for i in range(60)],
                "duck_attack_frames": 50, "duck_release_frames": 70, "duck_gain": .3,
                "samples": rng.integers(-3000, 3000, (127, 2), dtype=np.int16)},
               {"id": "empty", "kind": "voice", "start": 0, "samples": np.empty((0, 2), dtype=np.int16)}]
    random.Random(15).shuffle(tracks)
    indexed = IndexedAudioTracks(tracks)
    volumes = {"voice": .8, "music": .4}
    for cursor in [0, 145, 1900, 5, 9000, 15000, 200, -300]:
        for count in [1, 127, 480, 9600]:
            for muted in [frozenset(), frozenset({"3", "music"})]:
                assert mix_frames(indexed, cursor, count, volumes, muted) == mix_frames(tracks, cursor, count, volumes, muted)
    assert all("_duck_index" not in row for row in tracks)


@pytest.mark.parametrize("interpolation", ["linear", "ease_in", "ease_out", "ease_in_out"])
def test_compiled_keyframes_match_reference_including_duplicate_times(interpolation):
    clip = EditorClip(clip_id="animation", track_id="overlays", kind="image", start_ms=1000, duration_ms=10000,
                      keyframes=[EditorKeyframe(keyframe_id=f"key-{i}", time_ms=t, property_name="scale", value=v, interpolation=interpolation)
                                 for i, (t, v) in enumerate([(700, 100), (0, 30), (100, 60), (100, 70), (700, 200), (900, 10)])])
    frames = sorted(clip.keyframes, key=lambda frame: frame.time_ms)
    def reference(time):
        local = max(0, time - clip.start_ms)
        if local <= frames[0].time_ms: return float(frames[0].value)
        if local >= frames[-1].time_ms: return float(frames[-1].value)
        for i in range(1, len(frames)):
            if local <= frames[i].time_ms:
                left, right = frames[i - 1], frames[i]
                break
        p = (local - left.time_ms) / max(1, right.time_ms - left.time_ms)
        if interpolation == "ease_in": p *= p
        elif interpolation == "ease_out": p = 1 - (1 - p) ** 2
        elif interpolation == "ease_in_out": p = 2 * p * p if p < .5 else 1 - ((-2 * p + 2) ** 2) / 2
        return float(left.value + (right.value - left.value) * p)
    compiled = keyframe_index(clip)
    for time in range(800, 2100, 7):
        assert evaluate_keyframes(clip, "scale", time, 50, index=compiled) == reference(time)
    assert evaluate_keyframes(clip, "opacity", 1500, 87, index=compiled) == 87

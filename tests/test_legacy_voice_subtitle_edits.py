"""Merge/delete must not silence unchanged speech from pre-ID manifests."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pytest
from PySide6.QtGui import QGuiApplication

from haizflow.desktop.manual_preview_audio_controller import ManualPreviewAudioController
from haizflow.desktop.manual_subtitle_model import identify_segments
from haizflow.schemas.editor import EditorClip, EditorDocument, EditorSequence, EditorTrack
from haizflow.services import editor_documents
from haizflow.services.subtitle_identity import voice_source_indices


@pytest.fixture
def legacy_edit(tmp_path):
    source = [{"text": text, "start": float(index * 3), "end": float(index * 3 + 2)}
              for index, text in enumerate(["Trước", "Gộp A", "Gộp B", "Giữ nguyên", "Lặp", "Lặp"])]
    current = identify_segments("legacy-edits", source)
    outputs = {}
    for index in range(len(source)):
        audio = tmp_path / f"voice_{index + 1:04d}.mp3"
        audio.write_bytes(f"ID3 original voice {index}".encode())
        outputs[f"clip_{index + 1}"] = str(audio)
    published = {"signature": "voice", "resolved_outputs": outputs}
    video = SimpleNamespace(video_id="legacy-edits", project_type="manual", files={}, active_artifacts={},
                            enable_audio_separation=False, original_video_volume=60,
                            background_music_volume=30, tts_volume=100)
    return video, source, current, published


@pytest.mark.parametrize("operation", ["delete-first", "delete-middle", "merge", "merge-delete", "reorder-retime"])
def test_legacy_manifest_matches_original_indices_after_edit(legacy_edit, operation):
    video, source, current, _ = legacy_edit
    expected = list(range(6))
    if operation == "delete-first":
        del current[0]
        del expected[0]
    elif operation == "delete-middle":
        del current[1]
        del expected[1]
    elif operation in {"merge", "merge-delete"}:
        current[1]["text"] += " " + current[2]["text"]
        current[1]["end"] = current[2]["end"]
        del current[2]
        expected[1] = None
        del expected[2]
        if operation == "merge-delete":
            del current[1]
            del expected[1]
    else:
        current.reverse()
        expected.reverse()
        for index, row in enumerate(current):
            row.update(start=index * 3 + 1, end=index * 3 + 2)
    assert voice_source_indices(video.video_id, current, source) == {
        index: old for index, old in enumerate(expected) if old is not None}


def test_identical_text_cannot_override_explicit_speaker_identity():
    source = [{"segment_id": "male", "text": "Không", "start": 0, "end": 1},
              {"segment_id": "female", "text": "Không", "start": 2, "end": 3}]
    assert voice_source_indices("v", [source[1]], source) == {0: 1}
    assert voice_source_indices("v", [{**source[0], "segment_id": "new"}], source) == {}
    assert voice_source_indices("v", [{"text": "Không", "start": 0, "end": 1}], source) == {}


def test_ambiguous_legacy_rows_are_not_matched_by_position_or_text():
    source = [{"text": "Không", "start": 0, "end": 1} for _ in range(2)]
    assert voice_source_indices("v", [{"segment_id": "unknown", **source[0]}], source) == {}
    stable = identify_segments("v", source)
    assert voice_source_indices("v", [stable[1]], source) == {0: 1}


@pytest.mark.parametrize("operation", ["delete", "merge", "undo", "redo", "pending-publication"])
def test_reconcile_repairs_affected_projects_without_reviving_changed_speech(legacy_edit, operation):
    video, source, current, published = legacy_edit
    original = deepcopy(current)
    if operation != "undo":
        if operation == "delete":
            del current[1]
        else:
            current[1]["text"] += " " + current[2]["text"]
            current[1]["end"] = current[2]["end"]
            del current[2]
    document = EditorDocument(video_id=video.video_id, sequence=EditorSequence(duration_ms=20000),
        tracks=[EditorTrack(track_id="subtitles", kind="subtitle", name="Phụ đề"),
                EditorTrack(track_id="voice", kind="voice", name="Giọng đọc")],
        clips=[clip for row in current for clip in (
            EditorClip(clip_id=f"subtitle-{row['segment_id']}", track_id="subtitles", kind="subtitle",
                       segment_id=row["segment_id"], name=row["text"], start_ms=round(row["start"] * 1000),
                       duration_ms=round((row["end"] - row["start"]) * 1000)),
            EditorClip(clip_id=f"voice-{row['segment_id']}", track_id="voice", kind="voice",
                       segment_id=row["segment_id"], name=row["text"], start_ms=round(row["start"] * 1000),
                       duration_ms=round((row["end"] - row["start"]) * 1000), enabled=False,
                       metadata={"state": "stale"}))])
    before = document.model_dump()
    with patch.object(editor_documents, "_published_voice_sources", return_value=(published, source)):
        repaired = editor_documents._reconcile_media_assets(video, document,
            subtitle_segments=original if operation == "pending-publication" else current)
    voices = {c.segment_id: c for c in repaired.clips if c.track_id == "voice"}
    expected = voice_source_indices(video.video_id, current, source)
    assert len(expected) == len(current) - (operation in {"merge", "redo", "pending-publication"})
    for index, row in enumerate(current):
        clip = voices[row["segment_id"]]
        if index in expected:
            assert clip.enabled and clip.metadata["state"] == "ready"
            asset = editor_documents.asset_by_id(repaired, clip.asset_id)
            assert asset.path == published["resolved_outputs"][f"clip_{expected[index] + 1}"]
        else:
            assert not clip.enabled and clip.metadata["state"] == "stale"
    assert document.model_dump() == before


def test_preview_decodes_correct_legacy_parts_after_merge_and_delete(legacy_edit, tmp_path, monkeypatch):
    app = QGuiApplication.instance() or QGuiApplication([])
    video, source, current, published = legacy_edit
    del current[1:3]
    document = EditorDocument(video_id=video.video_id, sequence=EditorSequence(duration_ms=20000),
        tracks=[EditorTrack(track_id="subtitles", kind="subtitle", name="Phụ đề"),
                EditorTrack(track_id="voice", kind="voice", name="Giọng đọc")],
        clips=[clip for row in current for clip in (
            EditorClip(clip_id=f"subtitle-{row['segment_id']}", track_id="subtitles", kind="subtitle",
                       segment_id=row["segment_id"], name=row["text"], start_ms=round(row["start"] * 1000),
                       duration_ms=2000, metadata={"segment_payload": deepcopy(row)}),
            EditorClip(clip_id=f"voice-{row['segment_id']}", track_id="voice", kind="voice",
                       segment_id=row["segment_id"], name=row["text"], start_ms=round(row["start"] * 1000),
                       duration_ms=2000, metadata={"state": "ready"}))])
    audio = ManualPreviewAudioController()
    audio._executor.shutdown(wait=False, cancel_futures=True)
    results = []
    audio._executor = SimpleNamespace(submit=lambda callback: (results.append(callback()) or Mock()), shutdown=Mock())
    monkeypatch.setattr("haizflow.services.video_store.get_video_dir", lambda _: str(tmp_path))
    monkeypatch.setattr(editor_documents, "load", lambda _: document)
    monkeypatch.setattr("haizflow.pipeline.manual_tools.published_voice_record", lambda *_args, **_kwargs: published)
    monkeypatch.setattr("haizflow.pipeline.manual_tools.published_voice_source_segments",
                        lambda *_args, **_kwargs: source)
    monkeypatch.setattr("haizflow.pipeline.manual_tools._voice_manifest_payload", lambda _: {})
    monkeypatch.setattr("haizflow.pipeline.manual_tools._audio_background", lambda *_args, **_kwargs: ("", "", []))
    decoded = []
    monkeypatch.setattr(audio, "_decode", lambda path, *_args, **_kwargs:
                        (decoded.append(path) or np.ones((480, 2), dtype=np.int16)))
    try:
        audio.request(video, current)
        assert results[0][2] == ""
        assert len(results[0][1]) == len(current)
        assert decoded == [published["resolved_outputs"][f"clip_{index + 1}"] for index in (0, 3, 4, 5)]
        assert app is not None
    finally:
        audio.close()

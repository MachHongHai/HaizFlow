"""Non-destructive source placement, trimming and matched preview/export clocks."""

import subprocess
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pytest

from haizflow.desktop.manual_preview_audio_controller import RATE, apply_source_decisions
from haizflow.desktop.project_import_controller import ProjectImportController
from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.pipeline.sequence_compiler import materialize_source_sequence, materialize_source_video
from haizflow.schemas.editor import EditorAsset, EditorClip, EditorDocument, EditorSequence, SourceEditDecision
from haizflow.schemas.video import SubtitleStyle, VideoConfig, subtitle_style_for_project
from haizflow.services import editor_documents
from haizflow.utils.ffmpeg import _binary, get_video_duration


def source_document():
    return EditorDocument(
        video_id="source-edit",
        sequence=EditorSequence(duration_ms=10000, edit_decisions=[SourceEditDecision(
            decision_id="original", source_start_ms=0, source_end_ms=10000, sequence_start_ms=0)]),
        assets=[EditorAsset(asset_id="source", kind="source", duration_ms=10000)],
        clips=[
            EditorClip(clip_id="source", track_id="source-video", kind="source_video",
                       asset_id="source", duration_ms=10000, source_out_ms=10000),
            EditorClip(clip_id="source-audio-1", track_id="source-audio", kind="audio",
                       asset_id="source", duration_ms=10000, source_out_ms=10000),
            EditorClip(clip_id="subtitle", track_id="subtitles", kind="subtitle",
                       name="A translated sentence", start_ms=3000, duration_ms=1200),
            EditorClip(clip_id="voice", track_id="voice", kind="voice", start_ms=3000,
                       duration_ms=1200, metadata={"state": "ready", "text_revision": 3}),
        ],
    )


def mutation_host(document):
    history = []

    def mutate(_label, callback, **_kwargs):
        before = document.model_dump()
        callback(document)
        after = document.model_dump()
        if before == after:
            return False
        history.append((before, after))
        return True

    return SimpleNamespace(
        _manual_editor_document=SimpleNamespace(document_object=document),
        _editor_track_locked=lambda _document, _track: False,
        _refresh_source_sequence=HaizFlowController._refresh_source_sequence,
        _apply_editor_mutation=mutate,
    ), history


def test_source_drag_and_edge_resize_are_temporarily_disabled():
    document = source_document()
    host, history = mutation_host(document)
    untouched = document.model_dump()
    for edge in ("left", "right"):
        assert not HaizFlowController.trimClip(host, "source", edge, 3000)
    assert not HaizFlowController.moveClip(host, "source", 5000, "source-video")
    assert not HaizFlowController.moveClip(host, "source", 5000)
    assert document.model_dump() == untouched
    assert history == []


def test_subtitle_and_voice_edge_editing_is_not_disabled_with_source():
    document = source_document()
    host, _ = mutation_host(document)
    assert HaizFlowController.trimClip(host, "subtitle", "right", 4500)
    assert HaizFlowController.moveClip(host, "voice", 3200, "voice")
    assert document.clips[2].duration_ms == 1500
    assert document.clips[3].start_ms == 3200
    assert document.clips[0].duration_ms == 10000


def test_explicit_source_cut_remains_available_without_drag_resize():
    document = source_document()
    document.clips[1].metadata["follow_source"] = False
    host, _ = mutation_host(document)
    assert HaizFlowController.trimSourceBoundary(host, "right", 7000)
    assert document.clips[0].duration_ms == 7000
    assert document.sequence.edit_decisions[0].source_end_ms == 7000
    assert document.clips[1].metadata["follow_source"] is False


def test_pcm_mapping_has_silence_in_gaps_and_keeps_stereo():
    samples = np.full((RATE, 2), 1500, dtype="<i2")
    mapped = apply_source_decisions(samples, [
        {"source_start_ms": 0, "source_end_ms": 250, "sequence_start_ms": 250},
        {"source_start_ms": 500, "source_end_ms": 750, "sequence_start_ms": 750},
    ])
    assert mapped.shape == (RATE, 2)
    assert not np.any(mapped[:RATE // 4])
    assert np.all(mapped[RATE // 4:RATE // 2] == 1500)
    assert not np.any(mapped[RATE // 2:3 * RATE // 4])
    assert np.all(mapped[3 * RATE // 4:] == 1500)
    with pytest.raises(ValueError, match="Overlapping"):
        apply_source_decisions(samples, [
            {"source_start_ms": 0, "source_end_ms": 750, "sequence_start_ms": 0},
            {"source_start_ms": 0, "source_end_ms": 250, "sequence_start_ms": 500},
        ])


def test_real_source_gap_export_matches_pcm_preview(tmp_path):
    video, audio = tmp_path / "source.mp4", tmp_path / "source.wav"
    subprocess.run([_binary("ffmpeg"), "-y", "-f", "lavfi", "-i",
                    "color=c=red:s=64x64:r=20:d=1", "-c:v", "mpeg4", str(video)],
                   check=True, capture_output=True)
    subprocess.run([_binary("ffmpeg"), "-y", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=1", "-ar", "48000", "-ac", "2", str(audio)],
                   check=True, capture_output=True)
    document = EditorDocument(video_id="gap-export", sequence=EditorSequence(
        duration_ms=1500, edit_decisions=[SourceEditDecision(
            decision_id="shifted", source_start_ms=0, source_end_ms=1000, sequence_start_ms=500)]))
    edited, bed = materialize_source_sequence(str(video), str(audio), document, tmp_path / "mix", "gap-export")
    picture = materialize_source_video(str(video), document, tmp_path / "picture", "gap-picture")
    assert 1.45 <= get_video_duration(edited) <= 1.6
    assert 1.45 <= get_video_duration(picture) <= 1.6
    raw = subprocess.run([_binary("ffmpeg"), "-v", "error", "-i", bed,
                          "-f", "s16le", "-ar", "48000", "-ac", "2", "pipe:1"],
                         check=True, capture_output=True).stdout
    pcm = np.frombuffer(raw, dtype="<i2").reshape(-1, 2)
    assert not np.any(pcm[:RATE // 2])
    assert np.any(pcm[RATE // 2:])
    frame = subprocess.run([_binary("ffmpeg"), "-v", "error", "-ss", "0.2", "-i", picture,
                            "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                           check=True, capture_output=True).stdout
    assert max(frame) < 12  # A genuine black gap, not the first source frame repeated.


def test_manual_subtitle_defaults_do_not_replace_user_styling():
    original = SubtitleStyle()
    manual = subtitle_style_for_project("manual", original)
    assert (manual.font_size, manual.position_y_percent, manual.box_height_percent) == (84, 80, 12)
    assert original == SubtitleStyle()
    assert subtitle_style_for_project("single", original) == original
    assert subtitle_style_for_project("manual", original, overridden=True) == original
    custom = SubtitleStyle(font_size=92, position_y_percent=67)
    assert subtitle_style_for_project("manual", custom) == custom
    config = VideoConfig(project_type="manual")
    host = SimpleNamespace(_build_config=lambda: config, _project_type="manual")
    imported = ProjectImportController(host)._config_for_project_import()
    assert imported.subtitle_style == manual
    assert config.subtitle_style == original
    assert editor_documents._subtitle_style(imported).font_size == 84
    assert imported.subtitle_layout_override is True


def test_download_batch_import_reports_rejection_instead_of_closing_dialog(tmp_path):
    source = tmp_path / "download.mp4"
    source.write_bytes(b"source")
    host = SimpleNamespace(download_project_sources=SimpleNamespace(
        selected_items=lambda: [{"file_path": str(source)}]))
    controller = ProjectImportController(host)
    controller.import_batch_videos = Mock(return_value=False)
    assert not controller.import_selected_download_project_videos("batch")
    assert source.read_bytes() == b"source"


def test_batch_import_propagates_background_queue_rejection(tmp_path):
    source = tmp_path / "download.mp4"
    source.write_bytes(b"source")
    controller = ProjectImportController(SimpleNamespace(_media_import_events=Mock()))
    with patch.object(controller, "_queue_batch_paths", return_value=False):
        assert not controller.import_batch_videos([str(source)])

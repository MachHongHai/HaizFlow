import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from haizflow.desktop.manual_editor_document_model import ManualEditorDocumentModel
from haizflow.desktop.manual_preview_audio_controller import RATE, apply_source_decisions
from haizflow.desktop.manual_preview_composition_controller import ManualPreviewCompositionController
from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.pipeline.sequence_compiler import (
    apply_overlays,
    export_preflight,
    map_source_intervals,
    subtitle_style_overrides,
    write_subtitles,
)
from haizflow.schemas.editor import (
    EditorAsset,
    EditorClip,
    EditorDocument,
    EditorKeyframe,
    EditorSequence,
    EditorTextStyle,
    EditorTrack,
    SourceEditDecision,
)
from haizflow.schemas.video import SubtitleStyle
from haizflow.services import editor_documents


def test_source_boundary_trim_shifts_layers_without_changing_text_or_voice_state():
    document = EditorDocument(
        video_id="manual-trim",
        sequence=EditorSequence(
            duration_ms=6000,
            edit_decisions=[SourceEditDecision(
                decision_id="decision-source", source_start_ms=0,
                source_end_ms=6000, sequence_start_ms=0,
            )],
        ),
        tracks=[
            EditorTrack(track_id="source-video", kind="source_video", name="Video"),
            EditorTrack(track_id="subtitles", kind="subtitle", name="Subtitles"),
            EditorTrack(track_id="voice", kind="voice", name="Voice"),
            EditorTrack(track_id="music", kind="music", name="Music"),
        ],
        clips=[
            EditorClip(clip_id="source", track_id="source-video", kind="source_video",
                       duration_ms=6000, source_out_ms=6000),
            EditorClip(clip_id="subtitle-a", track_id="subtitles", kind="subtitle",
                       segment_id="a", name="Xin chào", start_ms=500, duration_ms=2000),
            EditorClip(clip_id="voice-a", track_id="voice", kind="voice",
                       segment_id="a", name="Xin chào", start_ms=500, duration_ms=2000,
                       metadata={"state": "ready", "text_revision": 2}),
            EditorClip(clip_id="music", track_id="music", kind="audio",
                       start_ms=3500, duration_ms=2000),
        ],
    )
    labels = []
    host = SimpleNamespace()
    host._editor_track_locked = lambda _document, _track: False
    host._refresh_source_sequence = lambda changed: HaizFlowController._refresh_source_sequence(changed)

    def mutate(label, callback):
        labels.append(label)
        callback(document)
        return True

    host._apply_editor_mutation = mutate
    assert HaizFlowController.trimSourceBoundary(host, "left", 1000)
    assert labels == ["trim_source_boundary"]
    assert document.sequence.duration_ms == 5000
    assert document.sequence.edit_decisions[0].source_start_ms == 1000
    clips = {clip.clip_id: clip for clip in document.clips}
    assert (clips["subtitle-a"].start_ms, clips["subtitle-a"].duration_ms) == (0, 1500)
    assert (clips["voice-a"].start_ms, clips["voice-a"].source_in_ms) == (0, 500)
    assert clips["voice-a"].metadata == {"state": "ready", "text_revision": 2}
    assert clips["music"].start_ms == 2500
    assert HaizFlowController.trimSourceBoundary(host, "right", 4000)
    assert document.sequence.duration_ms == 4000
    assert (clips["music"].start_ms, clips["music"].duration_ms) == (2500, 1500)


def test_legacy_split_source_is_read_only_for_boundary_trim():
    document = EditorDocument(
        video_id="legacy-split",
        sequence=EditorSequence(
            duration_ms=4000,
            edit_decisions=[
                SourceEditDecision(decision_id="a", source_start_ms=0,
                                   source_end_ms=2000, sequence_start_ms=0),
                SourceEditDecision(decision_id="b", source_start_ms=3000,
                                   source_end_ms=5000, sequence_start_ms=2000),
            ],
        ),
        clips=[
            EditorClip(clip_id="a", track_id="source-video", kind="source_video",
                       duration_ms=2000),
            EditorClip(clip_id="b", track_id="source-video", kind="source_video",
                       start_ms=2000, duration_ms=2000, source_in_ms=3000),
        ],
    )
    before = document.model_dump()
    host = SimpleNamespace(
        _editor_track_locked=lambda _document, _track: False,
        _refresh_source_sequence=lambda changed: HaizFlowController._refresh_source_sequence(changed),
    )

    def mutate(_label, callback):
        callback(document)
        return before != document.model_dump()

    host._apply_editor_mutation = mutate
    assert not HaizFlowController.trimSourceBoundary(host, "left", 500)
    assert document.model_dump() == before


@pytest.mark.parametrize("label", [
    "split_source", "duplicate_clip", "ripple_delete",
    "add_overlay", "add_overlay_from_asset", "set_keyframe",
    "move_keyframe", "remove_keyframe", "add_marker", "move_marker",
    "update_marker", "remove_marker",
])
def test_retired_authoring_commands_are_rejected_before_document_access(label):
    host = SimpleNamespace()
    assert not HaizFlowController._apply_editor_mutation(
        host, label, lambda _document: pytest.fail("retired command executed")
    )


def test_export_preflight_blocks_missing_active_media_and_reports_stale_voice(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    document = EditorDocument(
        video_id="manual-1",
        sequence=EditorSequence(duration_ms=2000),
        tracks=[
            EditorTrack(track_id="source-video", kind="source_video", name="Video"),
            EditorTrack(track_id="overlays", kind="overlay", name="Lớp phủ"),
            EditorTrack(track_id="voice", kind="voice", name="Giọng đọc"),
        ],
        assets=[
            EditorAsset(asset_id="missing", kind="image", name="Logo", path=str(tmp_path / "logo.png")),
        ],
        clips=[
            EditorClip(clip_id="logo", track_id="overlays", kind="image",
                asset_id="missing", name="Logo", duration_ms=2000),
            EditorClip(clip_id="voice-a", track_id="voice", kind="voice",
                segment_id="a", name="Xin chào", duration_ms=1000,
                enabled=False, metadata={"state": "stale"}),
        ],
    )

    result = export_preflight(document, str(source), tmp_path / "output")

    assert result["canExport"] is False
    assert {item["code"] for item in result["issues"]} >= {"missing_media", "stale_voice"}


def test_export_preflight_allows_partial_video_when_resources_exist(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    overlay = tmp_path / "logo.png"
    overlay.write_bytes(b"image")
    document = EditorDocument(
        video_id="manual-1",
        sequence=EditorSequence(duration_ms=2000),
        tracks=[EditorTrack(track_id="overlays", kind="overlay", name="Lớp phủ")],
        assets=[EditorAsset(asset_id="logo", kind="image", name="Logo", path=str(overlay))],
        clips=[EditorClip(clip_id="logo", track_id="overlays", kind="image",
            asset_id="logo", name="Logo", duration_ms=2000)],
    )

    result = export_preflight(document, str(source), tmp_path / "output")

    assert result["canExport"] is True
    assert not [item for item in result["issues"] if item["severity"] == "error"]
    assert result["requiredBytes"] > 0


def test_split_subtitle_creates_two_stale_voice_clips_without_running_tts():
    document = EditorDocument(
        video_id="manual-1",
        sequence=EditorSequence(duration_ms=4000),
        tracks=[
            EditorTrack(track_id="subtitles", kind="subtitle", name="Phụ đề"),
            EditorTrack(track_id="voice", kind="voice", name="Giọng đọc"),
        ],
        clips=[
            EditorClip(clip_id="subtitle-a", track_id="subtitles", kind="subtitle",
                segment_id="a", name="Xin chào Việt Nam", start_ms=500, duration_ms=2000),
            EditorClip(clip_id="voice-a", track_id="voice", kind="voice",
                segment_id="a", name="Xin chào Việt Nam", start_ms=500,
                duration_ms=2000, enabled=True),
        ],
    )
    host = SimpleNamespace(
        _editor_track_locked=lambda _document, _track: False,
        _split_subtitle_text=HaizFlowController._split_subtitle_text,
    )
    host._apply_editor_mutation = lambda _label, callback: (callback(document) or True)

    created = HaizFlowController.splitSubtitleSegment(host, "a", 1500)

    subtitles = sorted(
        (clip for clip in document.clips if clip.track_id == "subtitles"),
        key=lambda clip: clip.start_ms,
    )
    voices = [clip for clip in document.clips if clip.track_id == "voice"]
    assert created
    assert [clip.duration_ms for clip in subtitles] == [1000, 1000]
    assert " ".join(clip.name for clip in subtitles) == "Xin chào Việt Nam"
    assert len(voices) == 2
    assert all(not clip.enabled and clip.metadata["state"] == "stale" for clip in voices)


def test_replace_subtitle_text_is_one_mutation_and_invalidates_only_matching_voice():
    document = EditorDocument(
        video_id="manual-1",
        sequence=EditorSequence(duration_ms=4000),
        tracks=[
            EditorTrack(track_id="subtitles", kind="subtitle", name="Phụ đề"),
            EditorTrack(track_id="voice", kind="voice", name="Giọng đọc"),
        ],
        clips=[
            EditorClip(
                clip_id="subtitle-a", track_id="subtitles", kind="subtitle",
                segment_id="a", name="Xin chào bạn", duration_ms=1000,
                metadata={"segment_payload": {"revision": 4}},
            ),
            EditorClip(
                clip_id="subtitle-b", track_id="subtitles", kind="subtitle",
                segment_id="b", name="Tạm biệt bạn", start_ms=1000, duration_ms=1000,
            ),
            EditorClip(
                clip_id="voice-a", track_id="voice", kind="voice",
                segment_id="a", name="Xin chào bạn", duration_ms=1000,
                enabled=True, metadata={"state": "ready", "text_revision": 4},
            ),
            EditorClip(
                clip_id="voice-b", track_id="voice", kind="voice",
                segment_id="b", name="Tạm biệt bạn", start_ms=1000,
                duration_ms=1000, enabled=True, metadata={"state": "ready"},
            ),
        ],
    )
    labels = []

    def mutate(label, callback, **_kwargs):
        labels.append(label)
        callback(document)
        return True

    host = SimpleNamespace(_apply_editor_mutation=mutate)

    changed = HaizFlowController.replaceSubtitleText(
        host, "xin chào", "Chào", False, True, ""
    )

    subtitle_a = next(item for item in document.clips if item.clip_id == "subtitle-a")
    voice_a = next(item for item in document.clips if item.clip_id == "voice-a")
    voice_b = next(item for item in document.clips if item.clip_id == "voice-b")
    assert changed == 1
    assert labels == ["replace_subtitle_text"]
    assert subtitle_a.name == "Chào bạn"
    assert subtitle_a.metadata["segment_payload"]["revision"] == 5
    assert not voice_a.enabled and voice_a.metadata["state"] == "stale"
    assert voice_b.enabled and voice_b.metadata["state"] == "ready"


def test_marker_move_and_delete_are_undoable_editor_mutations():
    from haizflow.schemas.editor import EditorMarker

    document = EditorDocument(
        video_id="manual-1",
        sequence=EditorSequence(duration_ms=4000),
        markers=[EditorMarker(marker_id="marker-a", time_ms=1000, name="Kiểm tra")],
    )
    labels = []

    def mutate(label, callback, **_kwargs):
        labels.append(label)
        callback(document)
        return True

    host = SimpleNamespace(_apply_editor_mutation=mutate)

    assert HaizFlowController.updateEditorMarker(host, "marker-a", 2500, "", "")
    assert document.markers[0].time_ms == 2500
    assert HaizFlowController.removeEditorMarker(host, "marker-a")
    assert document.markers == []
    assert labels == ["move_marker", "remove_marker"]


def test_ready_voice_clip_registers_persistent_audio_asset_for_waveform(tmp_path):
    audio = tmp_path / "voice-a.mp3"
    audio.write_bytes(b"ID3" + b"voice" * 20)
    video = _video(tmp_path)
    document = EditorDocument(
        video_id=video.video_id,
        sequence=EditorSequence(duration_ms=1000),
        tracks=[EditorTrack(track_id="voice", kind="voice", name="Giọng đọc")],
        clips=[EditorClip(
            clip_id="voice-a", track_id="voice", kind="voice",
            segment_id="a", name="Xin chào", duration_ms=1000,
            enabled=False, metadata={"state": "stale"},
        )],
    )

    with (
        patch.object(editor_documents, "ensure", return_value=document),
        patch.object(editor_documents, "save", side_effect=lambda _video, value: value),
    ):
        stored = editor_documents.mark_voice_clips_ready(
            video,
            [{"segment_id": "a", "revision": 3}],
            {"a": str(audio)},
        )

    voice = stored.clips[0]
    asset = stored.assets[0]
    assert voice.enabled and voice.metadata["state"] == "ready"
    assert voice.asset_id == asset.asset_id == "voice-asset-a"
    assert asset.kind == "audio" and asset.path == str(audio)


def test_ready_voice_clip_matches_idless_subtitle_artifact_by_order_and_text(tmp_path):
    audio = tmp_path / "voice-a.mp3"
    audio.write_bytes(b"ID3" + b"voice" * 20)
    video = _video(tmp_path)
    document = EditorDocument(
        video_id=video.video_id,
        sequence=EditorSequence(duration_ms=1000),
        clips=[
            EditorClip(
                clip_id="subtitle-a", track_id="subtitles", kind="subtitle",
                segment_id="stable-a", name="Xin chào", duration_ms=1000,
            ),
            EditorClip(
                clip_id="voice-a", track_id="voice", kind="voice",
                segment_id="stable-a", name="Xin chào", duration_ms=1000,
                enabled=False, metadata={"state": "stale"},
            ),
        ],
    )
    with (
        patch.object(editor_documents, "ensure", return_value=document),
        patch.object(editor_documents, "save", side_effect=lambda _video, value: value),
    ):
        stored = editor_documents.mark_voice_clips_ready(
            video, [{"text": "Xin chào", "revision": 0}],
            {"index:1": str(audio)},
        )
    voice = next(clip for clip in stored.clips if clip.track_id == "voice")
    assert voice.enabled and voice.asset_id == "voice-asset-stable-a"
    assert next(asset for asset in stored.assets if asset.asset_id == voice.asset_id).path == str(audio)


def test_existing_document_reconciles_music_added_after_migration(tmp_path):
    music = tmp_path / "music.m4a"
    music.write_bytes(b"music")
    video = _video(tmp_path)
    video.files["background_music"] = str(music)
    document = EditorDocument(
        video_id=video.video_id,
        sequence=EditorSequence(duration_ms=4200),
        tracks=[EditorTrack(track_id="source-video", kind="source_video", name="Video")],
    )

    reconciled = editor_documents._reconcile_media_assets(video, document)

    assert any(track.track_id == "music" for track in reconciled.tracks)
    music_clip = next(clip for clip in reconciled.clips if clip.track_id == "music")
    music_asset = next(asset for asset in reconciled.assets if asset.asset_id == "background-music")
    assert music_clip.asset_id == music_asset.asset_id
    assert music_clip.duration_ms == 4200
    assert music_asset.path == str(music)


def test_existing_document_reattaches_compatible_published_voice(tmp_path):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"ID3voice")
    source_segments = tmp_path / "source-segments.json"
    source_segments.write_text(json.dumps([
        {"segment_id": "a", "text": "Xin chào", "start": 0, "end": 1, "revision": 3},
    ]), encoding="utf-8")
    video = _video(tmp_path)
    video.active_artifacts = {"tts_manifest": "voice-signature"}
    document = EditorDocument(
        video_id=video.video_id,
        sequence=EditorSequence(duration_ms=1000),
        tracks=[
            EditorTrack(track_id="subtitles", kind="subtitle", name="Phụ đề"),
            EditorTrack(track_id="voice", kind="voice", name="Giọng đọc"),
        ],
        clips=[
            EditorClip(
                clip_id="voice-a", track_id="voice", kind="voice",
                segment_id="a", name="Xin chào", duration_ms=1000,
                enabled=False, metadata={"state": "stale"},
            ),
        ],
    )
    voice_record = {
        "inputs": ["subtitle_document:subtitle-signature"],
        "resolved_outputs": {"clip_1": str(audio), "manifest": str(tmp_path / "manifest.json")},
    }
    subtitle_record = {"resolved_outputs": {"segments": str(source_segments)}}

    def peek(_video_id, kind, signature):
        if (kind, signature) == ("tts_manifest", "voice-signature"):
            return voice_record
        if (kind, signature) == ("subtitle_document", "subtitle-signature"):
            return subtitle_record
        return None

    with (
        patch.object(editor_documents.manual_artifacts, "peek", side_effect=peek),
        patch.object(editor_documents, "_legacy_segments", return_value=[
            {"segment_id": "a", "text": "Xin chào", "start": 0, "end": 1, "revision": 3},
        ]),
    ):
        reconciled = editor_documents._reconcile_media_assets(video, document)

    voice = next(clip for clip in reconciled.clips if clip.clip_id == "voice-a")
    asset = next(asset for asset in reconciled.assets if asset.asset_id == "voice-asset-a")
    assert voice.enabled and voice.metadata == {"state": "ready", "text_revision": 3}
    assert voice.asset_id == asset.asset_id
    assert asset.path == str(audio)


def test_existing_document_reattaches_idless_voice_without_reviving_edited_text(tmp_path):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"ID3voice")
    source_segments = tmp_path / "source-segments.json"
    source_segments.write_text(json.dumps([{"text": "Xin chào", "start": 0, "end": 1}]), encoding="utf-8")
    video = _video(tmp_path)
    video.active_artifacts = {"tts_manifest": "voice-signature"}
    document = EditorDocument(
        video_id=video.video_id,
        sequence=EditorSequence(duration_ms=1000),
        clips=[
            EditorClip(
                clip_id="subtitle-a", track_id="subtitles", kind="subtitle",
                segment_id="stable-a", name="Xin chào", duration_ms=1000,
            ),
            EditorClip(
                clip_id="voice-a", track_id="voice", kind="voice",
                segment_id="stable-a", name="Xin chào", duration_ms=1000,
                enabled=False, metadata={"state": "stale"},
            ),
        ],
    )
    voice_record = {
        "inputs": ["subtitle_document:subtitle-signature"],
        "resolved_outputs": {"clip_1": str(audio)},
    }
    subtitle_record = {"resolved_outputs": {"segments": str(source_segments)}}

    def peek(_video_id, kind, signature):
        return voice_record if kind == "tts_manifest" else subtitle_record

    with (
        patch.object(editor_documents.manual_artifacts, "peek", side_effect=peek),
        patch.object(editor_documents, "_legacy_segments", return_value=[
            {"text": "Xin chào", "start": 0, "end": 1},
        ]),
    ):
        repaired = editor_documents._reconcile_media_assets(video, document)
    voice = next(clip for clip in repaired.clips if clip.track_id == "voice")
    assert voice.enabled and voice.asset_id == "voice-asset-stable-a"

    document.clips[0].name = "Văn bản mới"
    with (
        patch.object(editor_documents.manual_artifacts, "peek", side_effect=peek),
        patch.object(editor_documents, "_legacy_segments", return_value=[
            {"text": "Văn bản mới", "start": 0, "end": 1},
        ]),
    ):
        stale = editor_documents._reconcile_media_assets(video, document)
    assert not next(clip for clip in stale.clips if clip.track_id == "voice").enabled


def test_existing_document_disables_voice_whose_text_no_longer_matches(tmp_path):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"ID3voice")
    source_segments = tmp_path / "source-segments.json"
    source_segments.write_text(
        json.dumps([{"segment_id": "a", "text": "Văn bản cũ", "revision": 2}]),
        encoding="utf-8",
    )
    video = _video(tmp_path)
    video.active_artifacts = {"tts_manifest": "voice-signature"}
    document = EditorDocument(
        video_id=video.video_id,
        sequence=EditorSequence(duration_ms=1000),
        clips=[EditorClip(
            clip_id="voice-a",
            track_id="voice",
            kind="voice",
            segment_id="a",
            asset_id="voice-asset-a",
            enabled=True,
            metadata={"state": "ready", "text_revision": 2},
        )],
        assets=[EditorAsset(
            asset_id="voice-asset-a",
            kind="audio",
            name="Giọng cũ",
            path=str(audio),
        )],
    )
    voice_record = {
        "inputs": ["subtitle_document:subtitle-signature"],
        "resolved_outputs": {"clip_0": str(audio)},
    }
    subtitle_record = {"resolved_outputs": {"segments": str(source_segments)}}

    def peek(_video_id, artifact_type, _signature):
        return voice_record if artifact_type == "tts_manifest" else subtitle_record

    with (
        patch.object(editor_documents.manual_artifacts, "peek", side_effect=peek),
        patch.object(editor_documents, "_legacy_segments", return_value=[
            {"segment_id": "a", "text": "Văn bản mới", "revision": 3},
        ]),
    ):
        reconciled = editor_documents._reconcile_media_assets(video, document)

    voice = next(clip for clip in reconciled.clips if clip.clip_id == "voice-a")
    assert not voice.enabled
    assert voice.asset_id == ""
    assert voice.metadata["state"] == "stale"


def test_legacy_split_source_cannot_be_ripple_deleted_in_new_editor():
    document = EditorDocument(
        video_id="manual-1",
        sequence=EditorSequence(duration_ms=6000),
        tracks=[
            EditorTrack(track_id="source-video", kind="source_video", name="Video"),
            EditorTrack(track_id="subtitles", kind="subtitle", name="Phụ đề"),
            EditorTrack(track_id="overlays", kind="overlay", name="Lớp phủ"),
        ],
        clips=[
            EditorClip(
                clip_id="source-a", track_id="source-video", kind="source_video",
                duration_ms=6000, source_out_ms=6000,
            ),
            EditorClip(
                clip_id="subtitle-a", track_id="subtitles", kind="subtitle",
                segment_id="a", name="Trong vùng cắt", start_ms=2200, duration_ms=500,
            ),
            EditorClip(
                clip_id="overlay-a", track_id="overlays", kind="image",
                name="Sau vùng cắt", start_ms=4000, duration_ms=1000,
            ),
        ],
    )
    document.clips[0].duration_ms = 2000
    document.clips.append(EditorClip(
        clip_id="source-b", track_id="source-video", kind="source_video",
        start_ms=2000, duration_ms=4000, source_in_ms=3000, source_out_ms=7000,
    ))
    document.sequence.edit_decisions = [
        SourceEditDecision(decision_id="a", source_start_ms=0,
                           source_end_ms=2000, sequence_start_ms=0),
        SourceEditDecision(decision_id="b", source_start_ms=3000,
                           source_end_ms=7000, sequence_start_ms=2000),
    ]
    before = document.model_dump()
    host = SimpleNamespace(_manual_editor_document=SimpleNamespace(document_object=document))
    assert not HaizFlowController.removeClips(host, ["source-b"], True)
    assert not HaizFlowController.removeClips(host, ["overlay-a"], False)
    assert document.model_dump() == before


def test_solo_audio_track_clears_other_audio_solos():
    document = EditorDocument(
        video_id="manual-1",
        tracks=[
            EditorTrack(track_id="voice", kind="voice", name="Giọng", solo=True),
            EditorTrack(track_id="music", kind="music", name="Nhạc"),
            EditorTrack(track_id="overlays", kind="overlay", name="Lớp phủ"),
        ],
    )

    def mutate(_label, callback, **_kwargs):
        callback(document)
        return True

    host = SimpleNamespace(_apply_editor_mutation=mutate)
    assert HaizFlowController.setTrackState(host, "music", "solo", True)
    states = {item.track_id: item.solo for item in document.tracks}
    assert states == {"voice": False, "music": True, "overlays": False}


def _video(tmp_path: Path):
    return SimpleNamespace(
        video_id="manual-1",
        original_filename="source.mp4",
        project_type="manual",
        subtitle_style=SubtitleStyle(),
        files={"video_input": str(tmp_path / "source.mp4")},
        video_width=1080,
        video_height=1920,
        original_video_volume=60,
        background_music_volume=30,
        tts_volume=100,
        watermark_text="",
        watermark_kind="text",
        watermark_scale_percent=100,
        watermark_opacity_percent=46,
        watermark_outline_percent=100,
        watermark_font_family="Arial",
        watermark_text_color="#FFFFFF",
        watermark_bold=True,
        watermark_italic=True,
        editor_document_schema_version=0,
        editor_document_revision=0,
        editor_document_path="",
    )


def test_first_editor_document_creates_metadata_backup_and_stable_tracks(tmp_path):
    video = _video(tmp_path)
    metadata = tmp_path / "video.json"
    metadata.write_text('{"schema_version": 17}', encoding="utf-8")
    destination = tmp_path / "editor" / "document.json"
    segments = [
        {"segment_id": "s1", "text": "Xin chào", "start": 0.2, "end": 1.4},
    ]
    with (
        patch.object(editor_documents, "document_path", return_value=destination),
        patch.object(editor_documents.video_store, "get_video_json_path", return_value=str(metadata)),
        patch.object(editor_documents.video_store, "save_video"),
        patch.object(editor_documents, "_legacy_segments", return_value=segments),
    ):
        document = editor_documents.ensure(video)

    assert (tmp_path / "video.pre-editor-v2.json").is_file()
    assert destination.is_file()
    assert [track.track_id for track in document.tracks] == [
        "source-video", "subtitles", "overlays", "voice", "source-audio", "music"
    ]
    assert next(clip for clip in document.clips if clip.track_id == "subtitles").segment_id == "s1"


def test_existing_editor_document_loads_without_rebuilding(tmp_path):
    path = tmp_path / "editor" / "document.json"
    path.parent.mkdir(parents=True)
    expected = EditorDocument(video_id="manual-1", revision=7)
    path.write_text(json.dumps(expected.model_dump()), encoding="utf-8")

    with patch.object(editor_documents, "document_path", return_value=path):
        loaded = editor_documents.load("manual-1")

    assert loaded is not None
    assert loaded.video_id == "manual-1"
    assert loaded.revision == 7


def test_sync_subtitle_keeps_full_payload_and_invalidates_only_changed_voice():
    document = EditorDocument(
        video_id="manual-1",
        sequence=EditorSequence(duration_ms=4000),
        tracks=[
            EditorTrack(track_id="subtitles", kind="subtitle", name="Phụ đề"),
            EditorTrack(track_id="voice", kind="voice", name="Giọng đọc"),
        ],
        clips=[
            EditorClip(clip_id="subtitle-a", track_id="subtitles", kind="subtitle",
                segment_id="a", name="A", duration_ms=1000),
            EditorClip(clip_id="voice-a", track_id="voice", kind="voice",
                segment_id="a", name="A", duration_ms=1000, enabled=True),
            EditorClip(clip_id="subtitle-b", track_id="subtitles", kind="subtitle",
                segment_id="b", name="B", start_ms=1200, duration_ms=1000),
            EditorClip(clip_id="voice-b", track_id="voice", kind="voice",
                segment_id="b", name="B", start_ms=1200, duration_ms=1000, enabled=True),
        ],
    )
    segments = [
        {"segment_id": "a", "text": "A mới", "start": 0, "end": 1, "words": [{"word": "A"}]},
        {"segment_id": "b", "text": "B", "start": 1.5, "end": 2.7},
    ]
    with (
        patch.object(editor_documents, "ensure", return_value=document),
        patch.object(editor_documents, "save", side_effect=lambda _video, value: value),
    ):
        synced = editor_documents.sync_subtitle_clips(SimpleNamespace(video_id="manual-1"), segments)

    voices = {clip.segment_id: clip for clip in synced.clips if clip.track_id == "voice"}
    subtitles = {clip.segment_id: clip for clip in synced.clips if clip.track_id == "subtitles"}
    assert voices["a"].enabled is False
    assert voices["b"].enabled is True
    assert subtitles["a"].metadata["segment_payload"]["words"][0]["word"] == "A"
    assert subtitles["b"].start_ms == 1500


def test_source_decisions_share_the_same_clock_for_preview_and_export(tmp_path):
    document = EditorDocument(
        video_id="manual-1",
        sequence=EditorSequence(
            duration_ms=2000,
            edit_decisions=[
                SourceEditDecision(decision_id="d1", source_start_ms=1000,
                    source_end_ms=2000, sequence_start_ms=0),
                SourceEditDecision(decision_id="d2", source_start_ms=3000,
                    source_end_ms=4000, sequence_start_ms=1000),
            ],
        ),
        tracks=[EditorTrack(track_id="subtitles", kind="subtitle", name="Phụ đề")],
        clips=[
            EditorClip(clip_id="subtitle-a", track_id="subtitles", kind="subtitle",
                segment_id="a", name="Một", start_ms=100, duration_ms=500),
            EditorClip(clip_id="subtitle-b", track_id="subtitles", kind="subtitle",
                segment_id="b", name="Hai", start_ms=1300, duration_ms=400),
        ],
    )

    source = np.arange(5 * RATE * 2, dtype=np.int16).reshape((-1, 2))
    preview = apply_source_decisions(source, [item.model_dump() for item in document.sequence.edit_decisions])
    assert len(preview) == 2 * RATE
    assert np.array_equal(preview[:10], source[RATE:RATE + 10])
    assert np.array_equal(preview[RATE:RATE + 10], source[3 * RATE:3 * RATE + 10])
    mapped = map_source_intervals(document, [(1.2, 1.6), (3.1, 3.8)])
    assert mapped[0] == pytest.approx((0.2, 0.6))
    assert mapped[1] == pytest.approx((1.1, 1.8))

    output = tmp_path / "subtitles.srt"
    assert write_subtitles(document, output)
    text = output.read_text(encoding="utf-8")
    assert "00:00:00,100 --> 00:00:00,600" in text
    assert "00:00:01,300 --> 00:00:01,700" in text


def test_keyframe_easing_uses_clip_local_time():
    clip = EditorClip(
        clip_id="overlay-1",
        track_id="overlays",
        kind="image",
        start_ms=1000,
        duration_ms=3000,
        keyframes=[
            EditorKeyframe(keyframe_id="k1", property_name="scale", time_ms=0, value=100),
            EditorKeyframe(keyframe_id="k2", property_name="scale", time_ms=1000,
                value=200, interpolation="ease_in"),
        ],
    )
    assert editor_documents.evaluate_keyframes(clip, "scale", 1000, 50) == 100
    assert editor_documents.evaluate_keyframes(clip, "scale", 1500, 50) == 125
    assert editor_documents.evaluate_keyframes(clip, "scale", 2000, 50) == 200


def test_legacy_keyframes_remain_readable_but_copy_authoring_is_disabled():
    document = EditorDocument(
        video_id="manual-keyframes",
        sequence=EditorSequence(duration_ms=4000),
        tracks=[EditorTrack(track_id="overlays", kind="overlay", name="Lớp phủ")],
        clips=[EditorClip(
            clip_id="overlay-a",
            track_id="overlays",
            kind="image",
            start_ms=500,
            duration_ms=3000,
            keyframes=[
                EditorKeyframe(keyframe_id="scale-a", property_name="scale",
                    time_ms=500, value=140, interpolation="ease_out"),
                EditorKeyframe(keyframe_id="opacity-a", property_name="opacity",
                    time_ms=500, value=65, interpolation="linear"),
            ],
        )],
    )

    host = SimpleNamespace(
        _manual_editor_document=SimpleNamespace(document_object=document),
        _editor_keyframe_clipboard=[],
    )

    before = document.model_dump()
    assert not HaizFlowController.copyClipKeyframes(host, "overlay-a", 1000)
    assert host._editor_keyframe_clipboard == []
    assert document.model_dump() == before


def test_subtitle_style_override_is_resolved_per_export_cue():
    document = EditorDocument(
        video_id="manual-1",
        sequence=EditorSequence(duration_ms=3000),
        tracks=[EditorTrack(track_id="subtitles", kind="subtitle", name="Phụ đề")],
        styles=[EditorTextStyle(style_id="subtitle-default", font_family="Bangers",
            font_size=48, text_color="#FFFFFF")],
        clips=[
            EditorClip(clip_id="subtitle-a", track_id="subtitles", kind="subtitle",
                segment_id="a", name="Một", duration_ms=1000,
                style_id="subtitle-default"),
            EditorClip(clip_id="subtitle-b", track_id="subtitles", kind="subtitle",
                segment_id="b", name="Hai", start_ms=1200, duration_ms=1000,
                style_id="subtitle-default",
                style_override={"font_size": 72, "text_color": "#00FF00"}),
        ],
    )

    overrides = subtitle_style_overrides(document)

    assert overrides[1]["font_size"] == 48
    assert overrides[1]["text_color"] == "#FFFFFF"
    assert overrides[2]["font_size"] == 72
    assert overrides[2]["text_color"] == "#00FF00"


def test_inline_subtitle_style_updates_only_selected_cue_and_preview():
    document = EditorDocument(
        video_id="manual-style",
        sequence=EditorSequence(duration_ms=3000),
        tracks=[EditorTrack(track_id="subtitles", kind="subtitle", name="Phụ đề")],
        styles=[EditorTextStyle(style_id="subtitle-default", font_family="Bangers")],
        clips=[
            EditorClip(clip_id="subtitle-a", track_id="subtitles", kind="subtitle",
                segment_id="a", name="Một", duration_ms=1000,
                style_id="subtitle-default"),
            EditorClip(clip_id="subtitle-b", track_id="subtitles", kind="subtitle",
                segment_id="b", name="Hai", start_ms=1200, duration_ms=1000,
                style_id="subtitle-default"),
        ],
    )

    def mutate(_label, callback):
        callback(document)
        return True

    host = SimpleNamespace(
        _apply_editor_mutation=mutate,
        _manual_subtitles=SimpleNamespace(segments=[
            {"segment_id": "a", "text": "Một", "start": 0, "end": 1},
            {"segment_id": "b", "text": "Hai", "start": 1.2, "end": 2.2},
        ]),
    )
    assert HaizFlowController.applyTextStyle(
        host, ["b"], {"text_color": "#00FF00", "outline_width": 4}, "segment"
    )
    export_styles = subtitle_style_overrides(document)
    preview_segments = HaizFlowController._subtitle_segments_for_editor_document(host, document)
    assert export_styles[1]["text_color"] == "#FFFFFF"
    assert export_styles[2]["text_color"] == "#00FF00"
    assert "_style" not in preview_segments[0]
    assert preview_segments[1]["_style"]["text_color"] == "#00FF00"
    assert preview_segments[1]["_style"]["outline_width"] == 4

    assert HaizFlowController.applyTextStyle(
        host, [], {"font_weight": 700}, "project"
    )
    assert subtitle_style_overrides(document)[1]["font_weight"] == 700
    assert subtitle_style_overrides(document)[2]["font_weight"] == 700

    # A project-wide edit must replace an older per-cue value for the same
    # property without discarding unrelated per-cue settings.
    assert HaizFlowController.applyTextStyle(
        host, [], {"text_color": "#FFCC00"}, "project"
    )
    export_styles = subtitle_style_overrides(document)
    assert export_styles[1]["text_color"] == "#FFCC00"
    assert export_styles[2]["text_color"] == "#FFCC00"
    assert export_styles[2]["outline_width"] == 4


def test_watermark_style_changes_are_written_to_editor_document(tmp_path):
    video = _video(tmp_path)
    video.watermark_text = "HAIZFLOW"
    video.watermark_font_family = "Impact"
    video.watermark_text_color = "#FFEF00"
    video.watermark_bold = False
    video.watermark_italic = False
    video.watermark_outline_percent = 150
    document = EditorDocument(
        video_id=video.video_id,
        sequence=EditorSequence(duration_ms=3000),
        styles=[EditorTextStyle(style_id="watermark-default", target_type="watermark")],
        clips=[EditorClip(clip_id="watermark-1", track_id="overlays", kind="text",
            name="HAIZFLOW", duration_ms=3000, style_id="watermark-default")],
    )
    saved = []
    host = SimpleNamespace(_manual_editor_document=None, _selected_video_id=video.video_id)
    with (
        patch.object(editor_documents, "load", return_value=document),
        patch.object(editor_documents, "save", side_effect=lambda _video, changed: saved.append(changed) or changed),
    ):
        HaizFlowController._sync_legacy_editor_visual_settings(host, video, {"watermark"})

    assert len(saved) == 1
    style = saved[0].styles[0]
    assert style.font_family == "Impact"
    assert style.text_color == "#FFEF00"
    assert style.font_weight == 400
    assert style.italic is False
    assert style.outline_width == 3


def test_text_overlay_compiler_uses_shared_sprite_and_keyframed_transform(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    destination = tmp_path / "overlay.mp4"
    document = EditorDocument(
        video_id="manual-1",
        sequence=EditorSequence(duration_ms=4000),
        tracks=[EditorTrack(track_id="overlays", kind="overlay", name="Lớp phủ")],
        styles=[EditorTextStyle(style_id="text-default", target_type="text_overlay",
            text_color="#F0E0D0", outline_color="#102030")],
        clips=[EditorClip(
            clip_id="text-1", track_id="overlays", kind="text", name="Nhãn",
            start_ms=500, duration_ms=2500, style_id="text-default",
            keyframes=[
                EditorKeyframe(keyframe_id="opacity-a", property_name="opacity",
                    time_ms=0, value=20),
                EditorKeyframe(keyframe_id="opacity-b", property_name="opacity",
                    time_ms=1000, value=100, interpolation="linear"),
            ],
        )],
    )

    with patch("haizflow.pipeline.sequence_compiler._run") as run:
        apply_overlays(str(source), str(destination), document, "test")

    command = run.call_args.args[0]
    graph = command[command.index("-filter_complex") + 1]
    sprite_input = command[command.index("-loop") + 3]
    assert sprite_input.endswith("sprite.png")
    assert "colorchannelmixer=aa='" in graph
    assert "rotate='" in graph
    assert "if(lt(t" in graph


def test_text_overlay_preview_resolves_the_same_style_as_export():
    document = EditorDocument(
        video_id="manual-1",
        sequence=EditorSequence(duration_ms=4000, source_asset_id="source"),
        tracks=[EditorTrack(track_id="overlays", kind="overlay", name="Lớp phủ")],
        styles=[EditorTextStyle(
            style_id="text-default",
            target_type="text_overlay",
            font_family="Segoe UI",
            font_size=72,
            text_color="#F0E0D0",
        )],
        clips=[EditorClip(
            clip_id="text-1",
            track_id="overlays",
            kind="text",
            name="Nhãn",
            duration_ms=4000,
            style_id="text-default",
            style_override={"outline_width": 7, "uppercase": True},
        )],
    )
    model = ManualEditorDocumentModel()
    model.set_document(document)
    preview = ManualPreviewCompositionController(model)

    frame = preview.frame
    assert frame["overlays"][0]["style"]["font_family"] == "Segoe UI"
    assert frame["overlays"][0]["style"]["font_size"] == 72
    assert frame["overlays"][0]["style"]["outline_width"] == 7
    assert frame["overlays"][0]["style"]["uppercase"] is True

    model.selectClip("text-1", False)
    assert model.selectedClip["resolved_style"] == frame["overlays"][0]["style"]
    model.close()


def test_waveform_is_attached_to_audio_clip_without_mutating_document():
    document = EditorDocument(
        video_id="manual-waveform",
        sequence=EditorSequence(duration_ms=1000),
        tracks=[EditorTrack(track_id="music", kind="music", name="Nhạc nền")],
        assets=[EditorAsset(asset_id="music-a", kind="audio", name="Nhạc")],
        clips=[EditorClip(
            clip_id="music-1",
            track_id="music",
            kind="audio",
            asset_id="music-a",
            duration_ms=1000,
        )],
    )
    model = ManualEditorDocumentModel()
    model.set_document(document)
    model._accept_waveform("manual-waveform", "music-a", {"peaks": [0.1, 0.75, 1.0]})

    assert model.clips[0]["waveform"] == [0.1, 0.75, 1.0]
    assert "waveform" not in document.clips[0].model_dump()
    model.close()


def test_selected_subtitle_reports_reading_and_overlap_without_false_layout_warning():
    document = EditorDocument(
        video_id="manual-warnings",
        sequence=EditorSequence(duration_ms=2000, source_asset_id="source"),
        tracks=[EditorTrack(track_id="subtitles", kind="subtitle", name="Phụ đề")],
        assets=[EditorAsset(
            asset_id="source", kind="source", name="Video", width=360, height=640
        )],
        styles=[EditorTextStyle(
            style_id="subtitle-default",
            font_size=64,
            max_width_percent=45,
            max_lines=1,
            safe_area_percent=5,
        )],
        clips=[
            EditorClip(
                clip_id="subtitle-a",
                track_id="subtitles",
                kind="subtitle",
                segment_id="a",
                name="Một đoạn phụ đề rất dài cần được cảnh báo trước khi xuất video",
                start_ms=0,
                duration_ms=700,
                style_id="subtitle-default",
            ),
            EditorClip(
                clip_id="subtitle-b",
                track_id="subtitles",
                kind="subtitle",
                segment_id="b",
                name="Đoạn chồng thời gian",
                start_ms=500,
                duration_ms=900,
                style_id="subtitle-default",
            ),
        ],
    )
    model = ManualEditorDocumentModel()
    model.set_document(document)
    model.selectClip("subtitle-a", False)

    codes = {item["code"] for item in model.selectedClip["warnings"]}

    assert codes == {"reading_speed", "overlap"}
    model.close()


def test_video_overlay_export_matches_preview_scale_and_source_offset(tmp_path):
    source = tmp_path / "source.mp4"
    overlay = tmp_path / "overlay.mp4"
    destination = tmp_path / "result.mp4"
    source.write_bytes(b"source")
    overlay.write_bytes(b"overlay")
    document = EditorDocument(
        video_id="manual-overlay",
        sequence=EditorSequence(duration_ms=5000, source_asset_id="source"),
        tracks=[EditorTrack(track_id="overlays", kind="overlay", name="Lớp phủ")],
        assets=[
            EditorAsset(asset_id="source", kind="source", path=str(source), width=1080, height=1920),
            EditorAsset(asset_id="pip", kind="video", path=str(overlay)),
        ],
        clips=[EditorClip(
            clip_id="pip-1",
            track_id="overlays",
            kind="video",
            asset_id="pip",
            start_ms=1000,
            duration_ms=2500,
            source_in_ms=750,
            source_out_ms=3250,
            loop=False,
        )],
    )

    with patch("haizflow.pipeline.sequence_compiler._run") as run:
        apply_overlays(str(source), str(destination), document, "test")

    command = run.call_args.args[0]
    graph = command[command.index("-filter_complex") + 1]
    assert "-stream_loop" not in command
    assert "trim=start=0.750000" in graph
    assert "scale=w='302.4*" in graph  # 28% of the 1080 px reference canvas.


def test_media_overlay_crop_is_compiled_before_scale(tmp_path):
    source = tmp_path / "source.mp4"
    overlay = tmp_path / "overlay.png"
    destination = tmp_path / "result.mp4"
    source.write_bytes(b"source")
    overlay.write_bytes(b"overlay")
    document = EditorDocument(
        video_id="manual-overlay-crop",
        sequence=EditorSequence(duration_ms=3000, source_asset_id="source"),
        tracks=[EditorTrack(track_id="overlays", kind="overlay", name="Lớp phủ")],
        assets=[
            EditorAsset(asset_id="source", kind="source", path=str(source), width=1080),
            EditorAsset(asset_id="logo", kind="image", path=str(overlay)),
        ],
        clips=[EditorClip(
            clip_id="logo-1",
            track_id="overlays",
            kind="image",
            asset_id="logo",
            duration_ms=3000,
            transform={
                "crop_left_percent": 10,
                "crop_right_percent": 20,
                "crop_top_percent": 5,
                "crop_bottom_percent": 15,
            },
        )],
    )

    with patch("haizflow.pipeline.sequence_compiler._run") as run:
        apply_overlays(str(source), str(destination), document, "test")

    command = run.call_args.args[0]
    graph = command[command.index("-filter_complex") + 1]
    assert "crop=w='iw*0.7':h='ih*0.8':x='iw*0.1':y='ih*0.05'" in graph
    assert graph.index("crop=w=") < graph.index("scale=w=")


def test_unlocked_overlay_aspect_ratio_uses_independent_export_scales(tmp_path):
    source = tmp_path / "source.mp4"
    overlay = tmp_path / "overlay.png"
    destination = tmp_path / "result.mp4"
    source.write_bytes(b"source")
    overlay.write_bytes(b"overlay")
    document = EditorDocument(
        video_id="manual-overlay-aspect",
        sequence=EditorSequence(duration_ms=1000, source_asset_id="source"),
        tracks=[EditorTrack(track_id="overlays", kind="overlay", name="Lớp phủ")],
        assets=[
            EditorAsset(asset_id="source", kind="source", path=str(source), width=1000),
            EditorAsset(asset_id="image", kind="image", path=str(overlay)),
        ],
        clips=[EditorClip(
            clip_id="image-1",
            track_id="overlays",
            kind="image",
            asset_id="image",
            duration_ms=1000,
            transform={
                "scale_x_percent": 150,
                "scale_y_percent": 70,
                "lock_aspect_ratio": False,
            },
        )],
    )

    with patch("haizflow.pipeline.sequence_compiler._run") as run:
        apply_overlays(str(source), str(destination), document, "test")

    command = run.call_args.args[0]
    graph = command[command.index("-filter_complex") + 1]
    assert "scale=w='200*(150)/100':h='ih*200/iw*(70)/100'" in graph


def test_unmuted_video_overlay_audio_is_mixed_on_the_editor_clock(tmp_path):
    source = tmp_path / "source.mp4"
    overlay = tmp_path / "overlay.mp4"
    destination = tmp_path / "result.mp4"
    source.write_bytes(b"source")
    overlay.write_bytes(b"overlay")
    document = EditorDocument(
        video_id="manual-overlay-audio",
        sequence=EditorSequence(duration_ms=5000, source_asset_id="source"),
        tracks=[EditorTrack(track_id="overlays", kind="overlay", name="Lớp phủ")],
        assets=[
            EditorAsset(asset_id="source", kind="source", path=str(source), width=1080),
            EditorAsset(asset_id="pip", kind="video", path=str(overlay)),
        ],
        clips=[EditorClip(
            clip_id="pip-1",
            track_id="overlays",
            kind="video",
            asset_id="pip",
            start_ms=1250,
            duration_ms=2000,
            source_in_ms=500,
            source_out_ms=2500,
            volume_percent=75,
            fade_in_ms=100,
            fade_out_ms=250,
            loop=True,
            muted=False,
        )],
    )

    with (
        patch("haizflow.pipeline.sequence_compiler.get_media_stream_types", return_value={"video", "audio"}),
        patch("haizflow.pipeline.sequence_compiler._run") as run,
    ):
        apply_overlays(str(source), str(destination), document, "test")

    command = run.call_args.args[0]
    graph = command[command.index("-filter_complex") + 1]
    assert "-stream_loop" in command
    assert "atrim=start=0.500000:duration=2.000000" in graph
    assert "volume=0.75" in graph
    assert "adelay=1250|1250" in graph
    assert "amix=inputs=2:duration=first" in graph
    assert command[command.index("-c:a") + 1] == "aac"

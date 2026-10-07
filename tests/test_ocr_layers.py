import json
import subprocess
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pytest

from haizflow.desktop.manual_edit_history import AppEditHistory
from haizflow.desktop.editor_preview_controller import EditorPreviewController
from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.pipeline.render import _ordered_subtitle_removal_prefix
from haizflow.schemas.editor import EditorDocument, EditorSequence
from haizflow.services import editor_documents, ocr_layers, translation
from haizflow.utils.ffmpeg import _binary


REGION = dict(x_percent=20, y_percent=60, width_percent=60, height_percent=20)


@pytest.fixture(autouse=True)
def enable_experimental_layers(monkeypatch):
    monkeypatch.setattr(ocr_layers, "EXTRA_LAYERS_ENABLED", True)


def document():
    value = EditorDocument(video_id="layer-test", sequence=EditorSequence(duration_ms=4000))
    assert ocr_layers.ensure_primary(value)
    return value


def host_for(value):
    model = SimpleNamespace(document_object=value, selectClip=Mock(), clearSelection=Mock())
    host = SimpleNamespace(
        _manual_editor_document=model,
        _editor_video=lambda: SimpleNamespace(video_id=value.video_id),
        _processing_queue=SimpleNamespace(contains=Mock(return_value=False)),
        _editor_track_locked=lambda *_args: False,
        selectedVideoChanged=Mock(),
    )
    history = AppEditHistory()
    history.select_video(value.video_id)

    def restore(payload):
        model.document_object = EditorDocument.model_validate(deepcopy(payload))
        return True

    def mutate(label, callback, **kwargs):
        before = model.document_object.model_dump()
        callback(model.document_object)
        after = model.document_object.model_dump()
        if before == after:
            return False
        history.record(label, lambda: restore(before), lambda: restore(after), **kwargs)
        return True

    host._apply_editor_mutation = mutate
    return host, history


def test_add_multiple_layers_delete_and_undo_without_removing_detected_region():
    host, history = host_for(document())
    first = HaizFlowController.addOcrLayer(host)
    second = HaizFlowController.addOcrLayer(host)
    assert first and second and first != second
    value = host._manual_editor_document.document_object
    assert [clip.name for clip in value.clips] == ["Vùng nhận diện", "Lớp che 1", "Lớp che 2"]
    assert not HaizFlowController.removeClips(host, [ocr_layers.PRIMARY_CLIP])
    assert HaizFlowController.removeClips(host, [first])
    assert {clip.clip_id for clip in value.clips} == {ocr_layers.PRIMARY_CLIP, second}
    assert not any(track.track_id == first for track in value.tracks)
    assert history.undo()
    restored = host._manual_editor_document.document_object
    assert {clip.clip_id for clip in restored.clips} == {ocr_layers.PRIMARY_CLIP, first, second}
    assert history.redo()
    assert first not in {clip.clip_id for clip in host._manual_editor_document.document_object.clips}


def test_layers_have_independent_geometry_modes_and_timing_and_survive_save(tmp_path):
    host, _ = host_for(document())
    first, second = HaizFlowController.addOcrLayer(host), HaizFlowController.addOcrLayer(host)
    assert HaizFlowController.updateOcrLayer(host, first, REGION, "patch")
    assert HaizFlowController.setOcrLayerRange(host, first, 500, 1500)
    assert HaizFlowController.moveClip(host, first, 700, second)
    assert HaizFlowController.trimClip(host, first, "right", 1900)
    value = host._manual_editor_document.document_object
    first_clip = editor_documents.clip_by_id(value, first)
    assert first_clip.track_id == first
    assert (first_clip.start_ms, first_clip.duration_ms) == (700, 1200)
    assert first_clip.metadata["removal_mode"] == "patch"
    assert editor_documents.clip_by_id(value, second).metadata["removal_mode"] == "blur"
    video = SimpleNamespace(video_id=value.video_id)
    target = tmp_path / "document.json"
    with patch.object(editor_documents, "document_path", return_value=target), patch.object(editor_documents.video_store, "save_video"):
        stored = editor_documents.save(video, value)
        loaded = editor_documents.load(value.video_id)
    assert loaded.model_dump() == stored.model_dump()
    assert loaded.schema_version == 3


def test_restore_primary_preserves_added_layers_and_keep_only_disables_primary():
    host, _ = host_for(document())
    extra = HaizFlowController.addOcrLayer(host)
    assert HaizFlowController.updateOcrLayer(host, extra, REGION, "patch")
    value = host._manual_editor_document.document_object
    video = SimpleNamespace(video_id=value.video_id, project_type="manual",
        remove_original_subtitles=True, original_subtitle_removal_mode="blur",
        original_subtitle_region_override=dict(REGION, x_percent=10))
    before = ocr_layers.layers(video, value, REGION)
    video.original_subtitle_region_override = {}
    after = ocr_layers.layers(video, value, REGION)
    assert next(layer for layer in after if layer["primary"])["region"] == REGION
    assert before[0] == after[0]
    video.remove_original_subtitles = False
    with patch.object(editor_documents, "load", return_value=value):
        payload = ocr_layers.render_region(video, REGION)
    assert [layer["clip_id"] for layer in payload["treatment_layers"]] == [extra]
    value.tracks[-1].visible = False
    with patch.object(editor_documents, "load", return_value=value):
        assert ocr_layers.render_region(video, REGION) is None


def test_invalid_regions_and_methods_do_not_mutate_document():
    host, _ = host_for(document())
    clip_id = HaizFlowController.addOcrLayer(host)
    before = host._manual_editor_document.document_object.model_dump()
    assert not HaizFlowController.updateOcrLayer(host, clip_id, dict(REGION, width_percent=120), "blur")
    assert not HaizFlowController.updateOcrLayer(host, clip_id, REGION, "unknown")
    assert not HaizFlowController.updateOcrLayer(host, ocr_layers.PRIMARY_CLIP, REGION, "blur")
    assert not HaizFlowController.setOcrLayerRange(host, clip_id, 1000, 1020)
    assert host._manual_editor_document.document_object.model_dump() == before


@pytest.mark.parametrize("primary", [False, True])
def test_reapplying_a_moved_region_replaces_the_old_mask_and_cache_key(tmp_path, primary):
    host, _ = host_for(document())
    video = SimpleNamespace(video_id="layer-test", project_type="manual",
        remove_original_subtitles=primary, original_subtitle_removal_mode="blur",
        original_subtitle_region_override={})
    clip_id = ocr_layers.PRIMARY_CLIP if primary else HaizFlowController.addOcrLayer(host)
    old = dict(x_percent=10, y_percent=10, width_percent=30, height_percent=20)
    moved = dict(old, y_percent=65)
    payloads = []
    for region in [old, moved]:
        if primary:
            video.original_subtitle_region_override = region
        else:
            assert HaizFlowController.updateOcrLayer(host, clip_id, region, "blur")
        with patch.object(editor_documents, "load", return_value=host._manual_editor_document.document_object):
            payloads.append(ocr_layers.render_region(video, old))
    for payload, region in zip(payloads, [old, moved], strict=True):
        assert len(payload["treatment_layers"]) == 1
        assert payload["treatment_layers"][0]["clip_id"] == clip_id
        assert payload["treatment_layers"][0]["region"] == region
    settings = dict(video_id=video.video_id, source_identity={"size": 1}, crop={},
        output_format="keep_ratio", remove_original_subtitles=True, removal_mode="blur",
        watermark_text="", watermark_scale_percent=100, preview_encoding="test",
        ocr_region=payloads[0])
    old_key = EditorPreviewController._source_effects_key(settings)
    updated = dict(settings, ocr_region=payloads[1])
    assert EditorPreviewController._source_effects_key(updated) != old_key
    base = tmp_path / "base-old"
    base.mkdir()
    cached = base / "preview.mp4"
    cached.write_bytes(b"old masked preview")
    EditorPreviewController._write_completion_marker(base / "preview.complete.json", cached, 4,
        base_context={"effects": old_key, "source_start": 0, "duration": 4})
    assert EditorPreviewController._reusable_treated_base(tmp_path, updated, 0, 4) is None

    def frame(payload):
        prefix = _ordered_subtitle_removal_prefix(payload, 128, 96, "blur") if payload else ""
        command = [_binary("ffmpeg"), "-v", "error", "-f", "lavfi", "-i",
            "testsrc2=size=128x96:rate=1:duration=1"]
        if prefix:
            command += ["-filter_complex", prefix + "[source_without_original]null[out]", "-map", "[out]"]
        command += ["-threads", "1", "-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"]
        output = subprocess.run(command, check=True, capture_output=True).stdout
        return np.frombuffer(output, np.uint8).reshape(96, 128, 3).astype(float)

    raw, first, second = frame(None), frame(payloads[0]), frame(payloads[1])
    assert np.abs(first[12:26, 16:48] - raw[12:26, 16:48]).mean() > 5
    assert np.abs(second[12:26, 16:48] - raw[12:26, 16:48]).mean() < .5
    assert np.abs(second[66:78, 16:48] - raw[66:78, 16:48]).mean() > 5


def test_queued_video_blocks_all_ocr_layer_edits():
    host, _ = host_for(document())
    clip_id = HaizFlowController.addOcrLayer(host)
    host._processing_queue.contains.return_value = True
    before = host._manual_editor_document.document_object.model_dump()
    assert not HaizFlowController.addOcrLayer(host)
    assert not HaizFlowController.updateOcrLayer(host, clip_id, REGION, "patch")
    assert not HaizFlowController.setOcrLayerRange(host, clip_id, 500, 1500)
    assert not HaizFlowController.moveClip(host, clip_id, 500)
    assert not HaizFlowController.trimClip(host, clip_id, "right", 1000)
    assert not HaizFlowController.removeClips(host, [clip_id])
    assert not HaizFlowController.setTrackState(host, clip_id, "visible", False)
    assert host._manual_editor_document.document_object.model_dump() == before


def test_trim_proxy_uses_sequence_time_for_treatment_windows():
    sequence = {"edit_decisions": [{"source_start_ms": 5000, "sequence_start_ms": 0}]}
    offset = ocr_layers.render_time_offset(sequence, 6)
    assert offset == 1
    payload = {"timeline_offset_seconds": offset, "treatment_layers": [
        {"region": REGION, "start_ms": 1500, "duration_ms": 2000, "mode": "blur"}]}
    prefix = _ordered_subtitle_removal_prefix(payload, 128, 96, "patch", 6)
    assert "gte(t,0.500000)*lt(t,2.500000)" in prefix
    assert "gblur=" in prefix


def test_mixed_timed_treatments_render_real_frames_without_duplicate_filter_labels():
    payload = {"treatment_layers": [
        {"region": REGION, "start_ms": 500, "duration_ms": 500, "mode": "blur"},
        {"region": dict(REGION, y_percent=20), "start_ms": 1000, "duration_ms": 500, "mode": "patch"}]}

    def frames(prefix):
        command = [_binary("ffmpeg"), "-v", "error", "-f", "lavfi", "-i",
                   "testsrc2=size=128x96:rate=4:duration=2"]
        if prefix:
            command += ["-filter_complex", prefix + "[source_without_original]null[out]", "-map", "[out]"]
        command += ["-threads", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"]
        result = subprocess.run(command, check=True, capture_output=True)
        return np.frombuffer(result.stdout, dtype=np.uint8).reshape((-1, 96, 128, 3)).astype(float)

    original = frames("")
    result = frames(_ordered_subtitle_removal_prefix(payload, 128, 96, "blur"))
    assert result.shape == original.shape == (8, 96, 128, 3)
    difference = np.abs(result - original)
    assert difference[[0, 1, 6, 7]].mean() < 0.5
    assert difference[2:4, 60:70, 30:90].mean() > 5
    assert difference[4:6, 25:35, 30:90].mean() > 5


@pytest.mark.parametrize("mode", ["manual", "auto"])
def test_similarity_only_is_a_review_warning_not_a_failed_video(tmp_path, mode):
    source = tmp_path / "source.json"
    output = tmp_path / "translated.json"
    source.write_text(json.dumps([
        {"start": 0, "end": 1, "text": "The farmer gathered grass"},
        {"start": 1, "end": 2, "text": "The cattle waited nearby"}]), encoding="utf-8")
    answer = "Người nông dân gom cỏ"
    with patch.object(translation, "_translate_with_hymt2_worker", return_value=[answer, answer]) as worker, patch.object(translation, "log_to_video"):
        result = translation.translate_segments(str(source), str(output), "fixture", validation_mode=mode)
    assert worker.call_count == 3
    assert result[1]["translation_warnings"] == ["review_translation"]
    assert result[1]["text"] == answer
    assert "translation_warnings" not in result[0]
    assert json.loads(output.read_text(encoding="utf-8")) == result


@pytest.mark.parametrize("broken", ["Xin\ufffd chào", "Xin\ud800 chào", "\x00", ""])
def test_manual_keeps_editable_result_with_warning_for_invalid_text(tmp_path, broken):
    source, output = tmp_path / "source.json", tmp_path / "translated.json"
    source.write_text('[{"start":0,"end":1,"text":"Hello friend"}]', encoding="utf-8")
    with patch.object(translation, "_translate_with_hymt2_worker", return_value=[broken]), patch.object(translation, "log_to_video"):
        result = translation.translate_segments(str(source), str(output), "fixture", validation_mode="manual")
    assert result[0]["text"] and result[0]["translation_warnings"] == ["invalid_text"]
    assert "\ufffd" not in result[0]["text"] and "\ud800" not in result[0]["text"]
    assert result[0]["translation_warning_text"] == result[0]["text"]
    assert json.loads(output.read_text(encoding="utf-8")) == result


def test_auto_blocks_corrupt_text_without_overwriting_previous_output(tmp_path):
    source, output = tmp_path / "source.json", tmp_path / "translated.json"
    source.write_text('[{"start":0,"end":1,"text":"Hello friend"}]', encoding="utf-8")
    output.write_text("previous result", encoding="utf-8")
    with patch.object(translation, "_translate_with_hymt2_worker", return_value=["Xin\ufffd chào"]), patch.object(translation, "log_to_video"):
        with pytest.raises(RuntimeError, match="ký tự lỗi"):
            translation.translate_segments(str(source), str(output), "fixture")
    assert output.read_text(encoding="utf-8") == "previous result"


def test_layer_order_commands_are_not_exposed_in_ui():
    from pathlib import Path

    directory = Path(__file__).resolve().parents[1] / "src/haizflow/desktop/qml"
    for filename in ("OcrLayerList.qml", "SubtitleTimeline.qml", "TrackHeader.qml", "ManualWorkspace.qml"):
        text = (directory / filename).read_text(encoding="utf-8")
        assert "moveOcrLayer" not in text
        assert "layerOrderRequested" not in text
    assert not hasattr(HaizFlowController, "moveOcrLayer")


def test_new_layer_is_a_draft_until_apply_and_does_not_change_render_request():
    value = document()
    video = SimpleNamespace(video_id=value.video_id, project_type="manual", remove_original_subtitles=True,
                            original_subtitle_removal_mode="blur", original_subtitle_region_override={})
    host, _ = host_for(value)
    with patch.object(editor_documents, "load", return_value=value):
        before = ocr_layers.render_region(video, REGION)
        clip_id = HaizFlowController.addOcrLayer(host)
        assert ocr_layers.render_region(video, REGION) == before
        row = next(layer for layer in ocr_layers.layers(video, value, REGION) if layer["clip_id"] == clip_id)
        assert row["pending"] and not row["enabled"]
        assert HaizFlowController.updateOcrLayer(host, clip_id, row["region"], row["mode"])
        assert ocr_layers.render_region(video, REGION) != before
        row = next(layer for layer in ocr_layers.layers(video, value, REGION) if layer["clip_id"] == clip_id)
        assert not row["pending"] and row["enabled"]


def test_primary_region_migration_is_idempotent_and_repairs_missing_clip():
    value = document()
    assert not ocr_layers.ensure_primary(value)
    value.clips = []
    assert ocr_layers.ensure_primary(value)
    assert len(value.tracks) == len(value.clips) == 1
    assert not ocr_layers.ensure_primary(value)

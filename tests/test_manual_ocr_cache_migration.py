"""Reuse pre-layer OCR picture proxies without touching other cached stages."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QUrl

from hflow.desktop.editor_preview_controller import EditorPreviewController
from hflow.schemas.video import CropSettings


def fingerprint(settings):
    payload = EditorPreviewController._base_visual_cache_payload(settings)
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def old_and_layered_settings():
    region = {"x_percent": 15.97, "y_percent": 82.18, "width_percent": 68.06,
              "height_percent": 9.16, "line_height_percent": 9.16,
              "confidence": .992, "samples": 33}
    old = {"video_id": "old-long-project", "source_identity": {"path": "source.mp4", "size": 1234},
           "editor_sequence": {"duration_ms": 1674115, "edit_decisions": [
               {"decision_id": "source-decision-1", "source_start_ms": 0,
                "source_end_ms": 1674067, "sequence_start_ms": 0}]},
           "crop": CropSettings().model_dump(), "output_format": "keep_ratio",
           "remove_original_subtitles": True, "removal_mode": "patch",
           "watermark_text": "", "watermark_scale_percent": 100,
           "ocr_region": region, "original_subtitle_intervals": [(0, 4), (8, 14)],
           "preview_encoding": "manual-base-pcm-libass-watermark-overlay-v3",
           "independent_manual_preview": True}
    new = deepcopy(old)
    new["ocr_region"]["treatment_layers"] = [{
        "clip_id": "ocr-source-region", "primary": True, "name": "Vùng nhận diện",
        "region": {key: region[key] for key in ("x_percent", "y_percent", "width_percent", "height_percent")},
        "start_ms": 0, "duration_ms": 1674067, "mode": "patch", "enabled": True,
    }]
    return old, new


def legacy_cache(directory, settings, *, duration=1674.115):
    old_key = fingerprint(settings)
    output = directory / f"base-{old_key[:20]}" / "preview.mp4"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"completed OCR pictures")
    EditorPreviewController._write_completion_marker(
        output.with_name("preview.complete.json"), output, duration,
        base_context={"effects": EditorPreviewController._source_effects_key(settings),
                      "source_start": 0, "duration": duration})
    return output


def test_old_full_source_primary_ocr_hydrates_after_each_app_restart_without_work(tmp_path):
    old, new = old_and_layered_settings()
    output = legacy_cache(tmp_path, old)
    assert fingerprint(old) != fingerprint(new)
    assert EditorPreviewController._legacy_primary_ocr_fingerprint(new) == fingerprint(old)
    # Unrelated stage caches must remain byte-for-byte intact.
    for name in ("subtitles/segments.json", "voice/part.wav", "ocr/region.json"):
        target = tmp_path / name
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(b"unrelated-cache")
    before = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    for _restart in range(2):
        controller = EditorPreviewController(SimpleNamespace())
        with patch("hflow.desktop.editor_preview_controller.get_video_duration",
                   side_effect=AssertionError("No probe or render on migration hit")):
            controller._restore_manual_disk_cache(tmp_path, fingerprint(new), new)
        completed = controller._completed_requests[fingerprint(new)]
        assert completed[0] == str(output.resolve())
        assert completed[1] == ""  # Do not mix or rebuild audio.
        assert completed[5] == fingerprint(old)[:20]
        assert controller._completed_base_sources[fingerprint(new)][0] == str(output.resolve())
    after = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert after == before


@pytest.mark.parametrize("change", ["geometry", "mode", "start", "shorter", "extra", "not-primary",
                                   "source", "crop", "encoding", "intervals", "auto", "keep", "trim",
                                   "malformed-time"])
def test_changed_effects_never_reuse_legacy_ocr_cache(tmp_path, change):
    old, new = old_and_layered_settings()
    legacy_cache(tmp_path, old)
    layer = new["ocr_region"]["treatment_layers"][0]
    if change == "geometry":
        layer["region"]["y_percent"] = 70
    elif change == "mode":
        layer["mode"] = "blur"
    elif change == "start":
        layer["start_ms"] = 1000
    elif change == "shorter":
        layer["duration_ms"] -= 1000
    elif change == "extra":
        new["ocr_region"]["treatment_layers"].append(deepcopy(layer))
    elif change == "not-primary":
        layer["primary"] = False
    elif change == "source":
        new["source_identity"]["size"] += 1
    elif change == "crop":
        new["crop"]["zoom_percent"] = 120
    elif change == "encoding":
        new["preview_encoding"] = "different contract"
    elif change == "intervals":
        new["original_subtitle_intervals"] = [(0, 20)]
    elif change == "auto":
        new["independent_manual_preview"] = False
    elif change == "keep":
        new["remove_original_subtitles"] = False
    elif change == "trim":
        new["editor_sequence"]["edit_decisions"][0]["source_start_ms"] = 1000
        new["editor_sequence"]["duration_ms"] -= 1000
    elif change == "malformed-time":
        layer["duration_ms"] = "invalid"
    controller = EditorPreviewController(SimpleNamespace())
    controller._restore_manual_disk_cache(tmp_path, fingerprint(new), new)
    assert not controller._completed_requests


@pytest.mark.parametrize("problem", ["short", "truncated", "no-marker"])
def test_incomplete_legacy_cache_is_not_published(tmp_path, problem):
    old, new = old_and_layered_settings()
    output = legacy_cache(tmp_path, old, duration=12 if problem == "short" else 1674.115)
    if problem == "truncated":
        output.write_bytes(b"truncated")
    elif problem == "no-marker":
        output.with_name("preview.complete.json").unlink()
    controller = EditorPreviewController(SimpleNamespace())
    controller._restore_manual_disk_cache(tmp_path, fingerprint(new), new)
    assert not controller._completed_requests


def test_reopening_legacy_project_completes_request_without_progress_or_worker(tmp_path):
    from hflow.schemas.editor import EditorDocument, EditorSequence
    from hflow.services import editor_documents, manual_artifacts, ocr_layers, video_store

    old, _ = old_and_layered_settings()
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    old["source_identity"] = EditorPreviewController._file_identity(source)
    old["editor_sequence"]["source_asset_id"] = "source"
    document = EditorDocument(video_id=old["video_id"],
                              sequence=EditorSequence.model_validate(old["editor_sequence"]))
    old["editor_sequence"] = document.sequence.model_dump()
    ocr_layers.ensure_primary(document)
    # Match the source length, not the small container/word-alignment tail.
    document.clips[0].duration_ms = 1674067
    preview_dir = tmp_path / "temp/editor-preview"
    output = legacy_cache(preview_dir, old)
    video = SimpleNamespace(video_id=old["video_id"], project_type="manual", files={},
                            crop=CropSettings(), original_subtitle_removal_mode="patch",
                            remove_original_subtitles=True)
    host = SimpleNamespace(_selected_video=lambda: video, _resolve_video_file=lambda *_args: str(source),
                           manualPreviewAudio=object(), editorPreviewChanged=SimpleNamespace(emit=Mock()))
    controller = EditorPreviewController(host)
    try:
        with (patch.object(video_store, "get_video_dir", return_value=str(tmp_path)),
              patch.object(editor_documents, "load", return_value=document),
              patch.object(EditorPreviewController, "_ocr_region", return_value=old["ocr_region"]),
              patch.object(EditorPreviewController, "_source_subtitle_intervals",
                           return_value=old["original_subtitle_intervals"]),
              patch("hflow.desktop.editor_preview_controller.threading.Thread") as worker):
            assert controller.request("[]", 10)
            assert controller.request("[]", 100, cache_only=True)
            worker.assert_not_called()
            assert manual_artifacts.has_runtime_pins(video.video_id)
            host.editorPreviewChanged.emit.assert_called_once()
        assert not controller.busy
        assert controller.progress == 1
        assert controller.stage == "ready"
        assert controller._source.endswith("preview.mp4")
        assert Path(QUrl(controller.source).toLocalFile()).resolve() == output.resolve()
        assert Path(QUrl(controller.base_source).toLocalFile()).resolve() != source.resolve()
        assert controller._pinned_video_id == video.video_id
        assert controller._published_output_identity == controller._file_identity(output)
        assert controller.base_source == controller.source
    finally:
        controller.release()
    assert not manual_artifacts.has_runtime_pins(video.video_id)

"""Mask edits invalidate only intersecting picture chunks, never audio/OCR."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from haizflow.desktop.editor_preview_controller import EditorPreviewController
from haizflow.schemas.video import CropSettings


def settings():
    return {"video_id": "mask-test", "source_identity": {"path": "source", "size": 1},
        "source_path": "source", "crop": {}, "output_format": "keep_ratio",
        "remove_original_subtitles": True, "removal_mode": "patch",
        "watermark_text": "", "watermark_scale_percent": 100,
        "preview_encoding": "test", "independent_manual_preview": True,
        "duration": 36, "original_subtitle_intervals": [],
        "ocr_region": {"x_percent": 1, "treatment_layers": [
            {"clip_id": "primary", "region": {"x_percent": 10}, "mode": "patch",
             "start_ms": 0, "duration_ms": 36000},
            {"clip_id": "extra", "region": {"x_percent": 40}, "mode": "blur",
             "start_ms": 12000, "duration_ms": 12000}]}}


def test_only_overlapping_windows_change_and_primary_geometry_is_not_overwritten():
    old = settings()
    changed = deepcopy(old)
    changed["ocr_region"]["treatment_layers"][1]["region"] = {"x_percent": 65}
    payload = EditorPreviewController._mask_chunk_payload
    assert payload(old, 0, 12) == payload(changed, 0, 12)
    assert payload(old, 12, 12) != payload(changed, 12, 12)
    assert payload(old, 24, 12) == payload(changed, 24, 12)
    assert payload(changed, 12, 12)["ocr_region"]["treatment_layers"][0]["region"] == {"x_percent": 10}
    # Renaming/selecting a layer or changing primary UI-only geometry cannot
    # invalidate the actual masks when their rendered pixels have not changed.
    renamed = deepcopy(old)
    renamed["ocr_region"]["x_percent"] = 90
    renamed["ocr_region"]["treatment_layers"][1]["name"] = "renamed"
    assert payload(old, 12, 12) == payload(renamed, 12, 12)


def test_changed_mask_reuses_two_of_three_cached_chunks(tmp_path, monkeypatch):
    controller = EditorPreviewController(SimpleNamespace(editorPreviewChanged=SimpleNamespace(emit=Mock())))
    monkeypatch.setattr(controller, "_request_is_current", lambda *_args: True)
    monkeypatch.setattr(controller, "_set_progress", Mock())
    renders = []

    def render(_generation, _process, _video, _source, output, marker, _segments, duration,
               _format, _crop, region, *_args, **_kwargs):
        renders.append(deepcopy(region))
        output.write_bytes(b"cached-picture")
        controller._write_completion_marker(marker, output, duration)
        return True

    monkeypatch.setattr(controller, "_render_proxy_layer", render)
    assemble = Mock(return_value=True)
    monkeypatch.setattr(controller, "_assemble_preview_chunks", assemble)
    video = SimpleNamespace(crop=CropSettings())
    output = tmp_path / "preview.mp4"
    old = settings()
    assert controller._render_mask_chunks(1, "preview", video, old, tmp_path, output, tmp_path / "marker", 0)
    assert len(renders) == 3
    first_paths = assemble.call_args.args[2]
    changed = deepcopy(old)
    changed["ocr_region"]["treatment_layers"][1]["mode"] = "patch"
    assert controller._render_mask_chunks(2, "preview", video, changed, tmp_path, output, tmp_path / "marker", 0)
    assert len(renders) == 4
    paths = assemble.call_args.args[2]
    assert paths[0] == first_paths[0] and paths[2] == first_paths[2] and paths[1] != first_paths[1]
    assert all(Path(path).is_file() for path in paths)
    assert controller._render_mask_chunks(3, "preview", video, changed, tmp_path, output, tmp_path / "marker", 0)
    assert len(renders) == 4  # Reapplying identical masks does no encoding.


def test_cleanup_keeps_all_chunks_of_active_long_base(tmp_path):
    controller = EditorPreviewController
    active = tmp_path / "base-new/preview.mp4"
    active.parent.mkdir()
    active.write_bytes(b"base")
    names = []
    for index in range(45):
        folder = tmp_path / f"mask-chunk-{index}"
        folder.mkdir()
        (folder / "preview.mp4").write_bytes(b"chunk")
        names.append(folder.name)
    controller._write_completion_marker(active.parent / "preview.complete.json", active, 540,
                                         chunk_directories=names)
    stale = tmp_path / "mask-chunk-stale"
    stale.mkdir()
    (stale / "preview.mp4").write_bytes(b"old")
    controller._remove_stale_files(active)
    assert not stale.exists()
    assert all((tmp_path / name / "preview.mp4").is_file() for name in names)

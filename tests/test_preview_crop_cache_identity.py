"""Opening a saved project must not re-encode identical OCR pictures."""

import hashlib
import itertools
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QUrl

from haizflow.desktop.editor_preview_controller import EditorPreviewController as Preview
from haizflow.schemas.editor import EditorDocument, EditorSequence
from haizflow.schemas.video import CropSettings, SubtitleStyle

EDGES = ("left_percent", "right_percent", "top_percent", "bottom_percent")
SPELLINGS = list(itertools.product((False, True), repeat=4))


def digest(payload, *, ascii=False):
    return hashlib.sha256(json.dumps(payload, ensure_ascii=ascii, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def legacy_crop(spellings):
    return {**CropSettings().model_dump(),
            **{key: 0.0 if floating else 0 for key, floating in zip(EDGES, spellings)}}


def complete(output, duration):
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"complete-treated-pictures")
    Preview._write_completion_marker(output.with_name("preview.complete.json"), output, duration)


@pytest.fixture
def session(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"original-source")
    video = SimpleNamespace(video_id="crop-cache", project_type="manual", files={},
                            crop=CropSettings(), subtitle_style=SubtitleStyle(),
                            original_subtitle_removal_mode="patch", remove_original_subtitles=True)
    document = EditorDocument(video_id=video.video_id, sequence=EditorSequence(
        duration_ms=25000, edit_decisions=[{"decision_id": "source", "source_start_ms": 0,
                                         "source_end_ms": 25000, "sequence_start_ms": 0}]))
    region = {"x_percent": 20.5, "y_percent": 70.0,
              "width_percent": 60.25, "height_percent": 9.0}
    host = SimpleNamespace(_selected_video=lambda: video,
                           _resolve_video_file=lambda *_: str(source),
                           manualPreviewAudio=object(), editorPreviewChanged=SimpleNamespace(emit=Mock()))
    controller = Preview(host)
    module = "haizflow.desktop.editor_preview_controller"
    monkeypatch.setattr(f"{module}.video_store.get_video_dir", lambda _: str(tmp_path))
    monkeypatch.setattr("haizflow.services.editor_documents.load", lambda _: document)
    monkeypatch.setattr(f"{module}.manual_artifacts.pin", Mock())
    monkeypatch.setattr(f"{module}.manual_artifacts.unpin", Mock())
    monkeypatch.setattr(f"{module}.cancel_video", Mock())
    monkeypatch.setattr(controller, "_manual_voice_artifact", lambda _: None)
    monkeypatch.setattr(controller, "_ocr_region", lambda *_: deepcopy(region))
    with patch(f"{module}.threading.Thread") as worker:
        assert controller.request("[]", 0)
        settings = worker.call_args.kwargs["args"][3]
    controller.release()
    yield controller, video, settings, tmp_path / "temp/editor-preview"
    controller.release()


@pytest.mark.parametrize("spellings", SPELLINGS)
def test_all_crop_spellings_share_request_base_visual_and_chunk_keys(session, spellings):
    _, _, settings, _ = session
    variant = {**settings, "crop": legacy_crop(spellings), "duration": 25}
    assert digest(Preview._base_visual_cache_payload(variant)) == digest(Preview._base_visual_cache_payload(settings))
    assert digest(Preview._visual_cache_payload(variant)) == digest(Preview._visual_cache_payload(settings))
    assert digest(Preview._mask_chunk_payload(variant, 0, 12)) == digest(Preview._mask_chunk_payload(settings, 0, 12))
    assert Preview._source_effects_key(variant) == Preview._source_effects_key(settings)
    # The schema used int defaults in memory, float values after a disk load.
    loaded = CropSettings.model_validate_json(CropSettings().model_dump_json())
    assert Preview._crop_cache_payload(CropSettings().model_dump()) == Preview._crop_cache_payload(loaded.model_dump())


@pytest.mark.parametrize("spellings", SPELLINGS)
def test_reopen_restores_every_existing_crop_spelling_without_probe_or_render(session, spellings):
    controller, video, settings, directory = session
    payload = Preview._base_visual_cache_payload(settings)
    payload["crop"] = legacy_crop(spellings)  # Exact pre-fix JSON spelling.
    old_key = digest(payload)
    output = directory / f"base-{old_key[:20]}/preview.mp4"
    complete(output, 25)
    before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in directory.rglob("*") if p.is_file()}
    for _restart in range(3):
        video.crop = CropSettings.model_validate_json(video.crop.model_dump_json())
        controller._completed_requests.clear()
        controller._completed_base_sources.clear()
        with (patch("haizflow.desktop.editor_preview_controller.threading.Thread") as worker,
              patch("haizflow.desktop.editor_preview_controller.get_video_duration") as probe):
            assert controller.request("[]", 17, cache_only=True)
            worker.assert_not_called()
            probe.assert_not_called()
        assert Path(QUrl(controller.base_source).toLocalFile()) == output.resolve()
        assert controller.stage == "ready" and not controller.busy
        controller.release()
    after = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in directory.rglob("*") if p.is_file()}
    assert after == before  # Compatibility is read-only, not a cache rewrite.


@pytest.mark.parametrize("change", ["source", "subpixel-crop", "ocr", "mode", "timing", "encoding", "incomplete"])
def test_compatible_crop_lookup_does_not_relax_real_invalidation(session, change):
    controller, _, settings, directory = session
    old = Preview._base_visual_cache_payload(settings)
    old["crop"] = legacy_crop((True,) * 4)
    output = directory / f"base-{digest(old)[:20]}/preview.mp4"
    complete(output, 25)
    settings = deepcopy(settings)
    if change == "source":
        settings["source_identity"]["mtime_ns"] += 1
    elif change == "subpixel-crop":
        settings["crop"]["left_percent"] = 0.00001
    elif change == "ocr":
        settings["ocr_region"]["treatment_layers"][0]["region"]["y_percent"] += .00001
    elif change == "mode":
        settings["removal_mode"] = "blur"
    elif change == "timing":
        settings["ocr_region"]["treatment_layers"][0]["duration_ms"] -= 1
    elif change == "encoding":
        settings["preview_encoding"] += "-new-contract"
    else:
        output.write_bytes(b"truncated")
    key = digest(Preview._base_visual_cache_payload(settings))
    controller._restore_manual_disk_cache(directory, key, settings)
    assert not controller._completed_requests
    assert not controller._completed_base_sources


def test_exact_disk_hit_does_not_enumerate_compatibility_variants(session):
    controller, _, settings, directory = session
    key = digest(Preview._base_visual_cache_payload(settings))
    output = directory / f"base-{key[:20]}/preview.mp4"
    complete(output, 25)
    with patch.object(Preview, "_crop_cache_variants", side_effect=AssertionError("Exact hit stays O(1)")):
        controller._restore_manual_disk_cache(directory, key, settings)
    assert controller._completed_requests[key][0] == str(output.resolve())


def test_numeric_compatibility_also_supports_unchanged_multi_cut_sequences(session):
    controller, _, settings, directory = session
    settings["editor_sequence"] = {"duration_ms": 25000, "edit_decisions": [
        {"decision_id": "a", "source_start_ms": 0, "source_end_ms": 12000, "sequence_start_ms": 0},
        {"decision_id": "b", "source_start_ms": 15000, "source_end_ms": 28000, "sequence_start_ms": 12000}]}
    old = Preview._base_visual_cache_payload(settings)
    old["crop"] = legacy_crop((True,) * 4)
    output = directory / f"base-{digest(old)[:20]}/preview.mp4"
    complete(output, 25)
    key = digest(Preview._base_visual_cache_payload(settings))
    controller._restore_manual_disk_cache(directory, key, settings)
    assert controller._completed_requests[key][0] == str(output.resolve())


def test_nonzero_integer_crop_round_trip_and_subpixel_edits(session):
    _, _, settings, _ = session
    settings["crop"] = CropSettings(left_percent=4, right_percent=5, top_percent=1.125,
                                    bottom_percent=2.5).model_dump()
    stable = digest(Preview._base_visual_cache_payload(settings))
    settings["crop"]["left_percent"] = 4
    settings["crop"]["right_percent"] = 5
    assert digest(Preview._base_visual_cache_payload(settings)) == stable
    settings["crop"]["top_percent"] += .00001
    assert digest(Preview._base_visual_cache_payload(settings)) != stable


def test_partial_preview_reuses_old_float_chunks_after_restart(session):
    controller, video, settings, directory = session
    settings = {**settings, "duration": 25}
    chunks = []
    for index, (start, duration) in enumerate(Preview._visual_chunk_windows(25)):
        payload = Preview._mask_chunk_payload(settings, start, duration)
        payload["crop"] = legacy_crop(SPELLINGS[index + 1])
        output = directory / f"mask-chunk-{digest(payload, ascii=True)[:20]}/preview.mp4"
        complete(output, duration)
        chunks.append(output)
    output = directory / "base-resumed/preview.mp4"
    with (patch.object(controller, "_render_proxy_layer") as render,
          patch.object(controller, "_assemble_preview_chunks", return_value=True) as assemble):
        assert controller._render_mask_chunks(1, "preview", video, settings, directory,
                                              output, output.with_name("preview.complete.json"), 0)
        render.assert_not_called()
        assert assemble.call_args.args[2] == chunks

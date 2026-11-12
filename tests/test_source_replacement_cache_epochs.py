"""An explicit replacement starts fresh even when path/bytes/mtime match."""

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from haizflow.desktop.editor_preview_controller import EditorPreviewController
from haizflow.pipeline import manual_tools
from haizflow.schemas.video import VideoConfig
from haizflow.services import editor_documents, manual_artifacts, project_store, video_store


@pytest.fixture
def replacement(tmp_path, monkeypatch):
    monkeypatch.setattr(project_store, "PROJECT_INDEX_PATH", str(tmp_path / "projects.json"))
    monkeypatch.setattr(video_store, "LEGACY_VIDEO_WORKSPACES_DIR", str(tmp_path / "legacy"))
    video = video_store.create_video("replace-" + tmp_path.name, "original.mp4",
        VideoConfig(project_type="manual", project_directory=str(tmp_path), enable_audio_separation=False))
    source = tmp_path / "original.mp4"
    source.write_bytes(b"identical video bytes")
    shutil.copy2(source, video.files["video_input"])
    return video, source


@pytest.mark.parametrize("location", ["external", "input"])
@pytest.mark.parametrize("old_image_generation", [0, 1])
def test_same_video_replacement_really_runs_ocr_again(replacement, monkeypatch, location, old_image_generation):
    video, source = replacement
    if old_image_generation:
        video.manual_tool_generations = {"image": old_image_generation}
        video_store.save_video(video)
    detector = Mock(side_effect=[{"x_percent": 20}, {"x_percent": 21}])
    monkeypatch.setattr(manual_tools, "detect_original_subtitle_region", detector)
    reporter = SimpleNamespace(update=Mock())
    old_signature = manual_tools.ocr_signature(video)
    manual_tools._run_image(video, reporter)
    video = video_store.get_video(video.video_id)
    assert manual_artifacts.resolve(video.video_id, "ocr_region", old_signature)
    old_state = manual_artifacts.file_state(video.files["video_input"])
    stale_temp = Path(video_store.get_video_dir(video.video_id)) / "temp/original_subtitle_region.json"
    stale_temp.write_text('{"region": "OLD"}', encoding="utf-8")
    target = source if location == "external" else video.files["video_input"]
    replaced = video_store.replace_video_input(video.video_id, str(target))
    video_store._VIDEO_METADATA_CACHE.pop(video.video_id, None)
    replaced = video_store.get_video(video.video_id)  # Reopen from persisted metadata, not the replaced object.
    assert manual_artifacts.file_state(replaced.files["video_input"]) == old_state
    assert replaced.manual_tool_generations == {"source": 1}
    assert replaced.active_artifacts == {} and "ocr_region" not in replaced.files
    assert not stale_temp.exists()
    assert manual_tools.ocr_signature(replaced) != old_signature
    assert manual_artifacts.resolve(replaced.video_id, "ocr_region", manual_tools.ocr_signature(replaced)) is None
    manual_tools._run_image(replaced, reporter)
    assert detector.call_count == 2
    current = video_store.get_video(video.video_id)
    assert current.active_artifacts["ocr_region"] == manual_tools.ocr_signature(current)
    assert json.loads(Path(current.files["ocr_region"]).read_text("utf-8")) == {"x_percent": 21}
    assert Path(current.files["video_input"]).read_bytes() == b"identical video bytes"


def test_same_input_replacement_failure_restores_original_epoch_and_outputs(replacement, monkeypatch):
    video, _source = replacement
    old_signature = manual_tools.ocr_signature(video)
    old_temp = Path(video_store.get_video_dir(video.video_id)) / "temp/kept.txt"
    old_temp.write_text("kept", encoding="utf-8")
    save = video_store._save_video_unlocked
    def fail_commit(candidate):
        if candidate.manual_tool_generations.get("source"):
            raise OSError("metadata commit failed")
        return save(candidate)
    monkeypatch.setattr(video_store, "_save_video_unlocked", fail_commit)
    with pytest.raises(OSError, match="metadata commit failed"):
        video_store.replace_video_input(video.video_id, video.files["video_input"])
    restored = video_store.get_video(video.video_id)
    assert not restored.manual_tool_generations
    assert manual_tools.ocr_signature(restored) == old_signature
    assert Path(restored.files["video_input"]).read_bytes() == b"identical video bytes"
    assert old_temp.read_text("utf-8") == "kept"


def test_source_zero_keeps_legacy_ocr_key_and_source_epoch_cannot_alias_image_rerun(replacement):
    video, _source = replacement
    legacy = manual_artifacts.signature(manual_artifacts.file_state(video.files["video_input"]),
                                       manual_tools.DETECTOR_CACHE_VERSION, "manual-ocr-region-v1")
    assert manual_tools.ocr_signature(video) == legacy
    image_rerun = video.model_copy(update={"manual_tool_generations": {"image": 1}})
    replaced = video.model_copy(update={"manual_tool_generations": {"source": 1}})
    assert manual_tools.ocr_signature(image_rerun) != manual_tools.ocr_signature(replaced)


@pytest.mark.parametrize("provider", ["edge", "vieneu", "vieneu-gpu", "omnivoice", "omnivoice-gpu"])
@pytest.mark.parametrize("speaker_mode", ["single", "multiple"])
@pytest.mark.parametrize("separated", [False, True])
def test_other_processing_keys_change_with_source_epoch_even_if_all_content_is_equal(
        replacement, tmp_path, monkeypatch, provider, speaker_mode, separated):
    video, _source = replacement
    video.tts_provider = provider
    video.speaker_mode = speaker_mode
    video.enable_audio_separation = separated
    segments = [{"segment_id": "one", "start": 0, "end": 1, "text": "Xin chào."}]
    subtitle = tmp_path / "segments.json"
    subtitle.write_text(json.dumps(segments), encoding="utf-8")
    monkeypatch.setattr(manual_tools, "_load_segments", lambda *_args, **_kwargs: segments)
    monkeypatch.setattr(manual_tools, "_current_subtitle_record", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(manual_tools, "published_voice_record", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(manual_tools, "_artifact_ready", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(manual_tools, "_audio_background", lambda *_args, **_kwargs: ("same.wav", "same", []))
    monkeypatch.setattr(editor_documents, "load", lambda *_: None)
    def signatures(candidate):
        return {
            "source_audio": manual_tools.source_signature(candidate),
            "separation": manual_tools.separation_signature(candidate),
            "recognition": manual_tools.recognition_signature(candidate),
            "translation": manual_tools.translation_signature(candidate),
            "subtitles": manual_tools._subtitle_document_signature(candidate, str(subtitle)),
            "voice_clips": manual_tools._voice_clip_signatures(candidate, segments),
            "voice_manifest": manual_tools.voice_signature(candidate),
            "audio_mix": manual_tools.audio_signature(candidate),
            "export": manual_tools.export_signature(candidate),
        }
    before = signatures(video)
    for epoch in (1, 2):
        current = signatures(video.model_copy(update={"manual_tool_generations": {"source": epoch}}))
        assert all(before[key] != current[key] for key in before), (provider, speaker_mode, before, current)
        before = current


def test_reimported_same_srt_cannot_recover_recognition_from_previous_source(replacement, monkeypatch):
    video, _source = replacement
    monkeypatch.setattr("haizflow.services.subtitle_import.has_import", lambda *_: True)
    assert manual_tools.recognition_signature(video) != manual_tools.recognition_signature(
        video.model_copy(update={"manual_tool_generations": {"source": 1}}))


def test_preview_key_changes_even_if_file_identity_is_identical(replacement, tmp_path):
    video, _source = replacement
    fingerprints = []
    for epoch in (0, 1, 2):
        selected = video.model_copy(update={"manual_tool_generations": {"source": epoch} if epoch else {}})
        host = SimpleNamespace(_selected_video=lambda: selected,
            _resolve_video_file=lambda *_: selected.files["video_input"], manualPreviewAudio=object(),
            editorPreviewChanged=Mock())
        controller = EditorPreviewController(host)
        with (patch.object(controller, "_file_identity", side_effect=lambda _: {"path": "same", "size": 10, "mtime": 1}),
              patch.object(controller, "_ocr_region", return_value={}),
              patch.object(controller, "_source_subtitle_intervals", return_value=[]),
              patch.object(controller, "_manual_voice_artifact", return_value=None),
              patch.object(controller, "_restore_manual_disk_cache"),
              patch("haizflow.services.video_store.get_video_dir", return_value=str(tmp_path)),
              patch("haizflow.services.ocr_layers.render_region", return_value={}),
              patch("haizflow.services.editor_documents.load", return_value=None),
              patch("haizflow.desktop.editor_preview_controller.threading.Thread") as worker):
            assert controller.request("[]", 0)
        captured = worker.call_args.kwargs["args"][3]
        fingerprints.append(captured["request_fingerprint"])
    assert len(set(fingerprints)) == 3


def test_same_video_source_waveform_cannot_reuse_previous_source_epoch(replacement, monkeypatch):
    video, _source = replacement
    monkeypatch.setattr(editor_documents, "_source_duration_ms", lambda *_: 1000)
    monkeypatch.setattr(editor_documents, "_legacy_segments", lambda *_: [])
    fingerprints = []
    for epoch in (0, 1, 2):
        selected = video.model_copy(update={"manual_tool_generations": {"source": epoch} if epoch else {}})
        document = editor_documents.build_legacy_document(selected)
        fingerprints.append(next(asset.fingerprint for asset in document.assets if asset.asset_id == "source"))
    assert fingerprints[0] == editor_documents._fingerprint(video.files["video_input"])
    assert len(set(fingerprints)) == 3


def test_srt_import_cannot_commit_to_a_replaced_identical_source(replacement, tmp_path, monkeypatch):
    from haizflow.services import subtitle_import

    video, source = replacement
    path = tmp_path / "captions.srt"
    path.write_text("1\n00:00:00,000 --> 00:00:01,000\nXin chào.\n", encoding="utf-8")
    inspect = subtitle_import.inspect_srt
    def replace_during_inspection(*args, **kwargs):
        result = inspect(*args, **kwargs)
        video_store.replace_video_input(video.video_id, str(source))
        return result
    monkeypatch.setattr(subtitle_import, "inspect_srt", replace_during_inspection)
    with pytest.raises(ValueError, match="Video nguồn đã thay đổi"):
        subtitle_import.import_srt(video.video_id, str(path))
    current = video_store.get_video(video.video_id)
    assert "imported_source_srt" not in current.files and current.active_artifacts == {}


def test_preview_compatibility_never_resurrects_retired_same_source_cache(replacement, monkeypatch):
    import hashlib

    video, source = replacement
    root = Path(video_store.get_video_dir(video.video_id))
    settings = dict(video_id=video.video_id, source_identity=EditorPreviewController._file_identity(video.files["video_input"]),
        editor_sequence={}, crop=video.crop.model_dump(), output_format="keep_ratio", remove_original_subtitles=True,
        removal_mode="patch", watermark_text="", watermark_scale_percent=100, ocr_region={"x_percent": 20},
        preview_encoding="manual-base-pcm-libass-watermark-overlay-v3", independent_manual_preview=True,
        original_subtitle_intervals=[])
    key = hashlib.sha256(json.dumps(EditorPreviewController._base_visual_cache_payload(settings),
        ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    old_preview = root / "temp/editor-preview" / f"base-{key[:20]}" / "preview.mp4"
    old_preview.parent.mkdir(parents=True)
    old_preview.write_bytes(b"old preview")
    EditorPreviewController._write_completion_marker(old_preview.with_name("preview.complete.json"), old_preview, 10)
    original_cleanup = video_store.shutil.rmtree
    def defer_retired_cleanup(path, *args, **kwargs):
        if Path(path).name.startswith(".replace-input-"):
            return
        return original_cleanup(path, *args, **kwargs)
    monkeypatch.setattr(video_store.shutil, "rmtree", defer_retired_cleanup)
    replaced = video_store.replace_video_input(video.video_id, str(source))
    assert list(root.glob(".replace-input-*/old-temp/editor-preview/base-*/preview.mp4"))
    assert not old_preview.exists()
    settings["source_identity"]["source_replacement"] = replaced.manual_tool_generations["source"]
    fingerprint = hashlib.sha256(json.dumps(EditorPreviewController._base_visual_cache_payload(settings),
        ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    controller = EditorPreviewController(SimpleNamespace())
    controller._restore_manual_disk_cache(root / "temp/editor-preview", fingerprint, settings)
    assert not controller._completed_requests

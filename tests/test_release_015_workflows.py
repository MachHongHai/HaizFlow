"""Regression coverage for independent stages and editable source-caption coverage."""
import json
import queue
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from haizflow.desktop.processing_lifecycle_controller import ProcessingLifecycleController
from haizflow.desktop.project_import_controller import ProjectImportController
from haizflow.services import translation
from haizflow.services.ocr_regions import effective_region, normalize_region, source_frame_in_output


@pytest.mark.parametrize("provider", ["gemini-3.1-flash-lite", "full"])
def test_similar_valid_translations_warn_but_publish_after_bounded_retries(tmp_path, provider):
    source, target = tmp_path / "source.json", tmp_path / "translated.json"
    source.write_text(json.dumps([
        {"start": 0, "end": 1, "text": "The farmer gathered grass", "language": "en"},
        {"start": 1, "end": 2, "text": "The cattle waited nearby", "language": "en"},
    ]), encoding="utf-8")
    translated = "Người nông dân gom cỏ"
    def worker(texts, **kwargs):
        indexes = kwargs.get("translate_indices")
        return dict.fromkeys(indexes, translated) if kwargs.get("strict_source_only") else [translated] * len(texts)
    with (patch("haizflow.services.gemini_translation.translate_texts", side_effect=worker),
          patch.object(translation, "_translate_with_hymt2_worker", side_effect=worker),
          patch.object(translation, "log_to_video") as log):
        translation.translate_segments(str(source), str(target), "fixture", translation_model=provider,
                                       provider="gemini" if provider.startswith("gemini") else "hymt2")
    assert [item["text"] for item in json.loads(target.read_text(encoding="utf-8"))] == [translated, translated]
    assert any("similarity alone" in str(call) for call in log.call_args_list)


@pytest.mark.parametrize("tool", ["source", "separation", "image", "voice", "audio", "subtitle", "export"])
def test_manual_nontranslation_tool_enqueues_without_gemini_key(tool):
    video = SimpleNamespace(video_id="fixture", status="done", project_type="manual", project_key="",
                            translation_model="gemini-3.1-flash-lite", manual_target_tool=tool)
    host = SimpleNamespace(_processing_queue=SimpleNamespace(contains=Mock(return_value=False),
        enqueue=Mock(return_value=True), pending_ids=Mock(return_value=[])),
        appAlertRequested=Mock(), processingChanged=Mock(), selectedVideoChanged=Mock(), _log_queue=queue.Queue())
    with (patch("haizflow.desktop.processing_lifecycle_controller.video_store.get_video", return_value=video),
          patch("haizflow.desktop.processing_lifecycle_controller.video_store.update_video"),
          patch("haizflow.desktop.processing_lifecycle_controller.video_store.log_to_video"),
          patch("haizflow.services.processing_resume.configuration_snapshot", return_value={}),
          patch("haizflow.services.gemini_translation.key_configured", return_value=False) as key):
        assert ProcessingLifecycleController(host).enqueue_video(video.video_id)
    key.assert_not_called()
    host.appAlertRequested.emit.assert_not_called()


def test_source_replacement_releases_own_preview_before_queueing():
    host = SimpleNamespace(_selected_video_id="fixture", _selected_project_key="project",
        _processing_queue=SimpleNamespace(active_video_id="", discard=Mock(return_value=False)),
        sourceReplacementRequested=Mock(), releaseEditorPreview=Mock(), _audio_preview=SimpleNamespace(invalidate=Mock()))
    controller = ProjectImportController(host)
    controller._queue_import = Mock(return_value=True)
    with patch("haizflow.desktop.project_import_controller.video_store.get_video",
               return_value=SimpleNamespace(status="done")):
        assert controller._queue_replace("fixture", "source.mp4", None)
    host.sourceReplacementRequested.emit.assert_called_once_with("fixture")
    host.releaseEditorPreview.assert_called_once()
    host._audio_preview.invalidate.assert_called_once()
    assert controller._queue_import.call_count == 1


@pytest.mark.parametrize("region", [{}, {"x_percent": float("nan")},
    dict(x_percent=95, y_percent=0, width_percent=20, height_percent=5)])
def test_ocr_rejects_invalid_rectangle(region):
    with pytest.raises(ValueError):
        normalize_region(region)


def test_ocr_override_keeps_detector_immutable_and_is_used_by_render():
    detected = dict(x_percent=20, y_percent=80, width_percent=60, height_percent=8)
    edited = dict(x_percent=25, y_percent=75, width_percent=50, height_percent=10)
    video = SimpleNamespace(original_subtitle_region_override=edited, remove_original_subtitles=True)
    from haizflow.pipeline.manual_tools import _ocr_region
    assert effective_region(video, detected) == edited
    assert _ocr_region(video) == edited
    assert detected["x_percent"] == 20


def test_omnivoice_cleanup_never_needs_psutil_in_the_core():
    from haizflow.pipeline import omnivoice_tts
    with (patch.dict("sys.modules", {"psutil": None}),
          patch.object(omnivoice_tts, "_PERSISTENT_WORKER_PROCESS", None)):
        assert not omnivoice_tts.release_model_memory()


@pytest.mark.parametrize("output_format", ["keep_ratio", "tiktok_9_16_crop", "blur_background_9_16"])
def test_ocr_output_mapping_round_trips_source_coordinates_with_crop(output_format):
    from haizflow.schemas.video import CropSettings
    crop = CropSettings(left_percent=10, right_percent=20, top_percent=5, bottom_percent=15)
    frame = source_frame_in_output(1920, 1080, output_format, crop)
    assert frame["width_percent"] > 0 and frame["height_percent"] > 0
    for x, y in [(15, 20), (45, 65), (65, 75)]:
        output_x = frame["x_percent"] + x * frame["width_percent"] / 100
        output_y = frame["y_percent"] + y * frame["height_percent"] / 100
        assert (output_x - frame["x_percent"]) * 100 / frame["width_percent"] == pytest.approx(x)
        assert (output_y - frame["y_percent"]) * 100 / frame["height_percent"] == pytest.approx(y)
    assert source_frame_in_output(1920, 1080, output_format, crop.model_dump()) == frame


def test_ocr_preview_edits_only_stage_changes_and_apply_is_explicit():
    from pathlib import Path
    directory = Path(__file__).resolve().parents[1] / "src/haizflow/desktop/qml"
    workspace = (directory / "ManualWorkspace.qml").read_text(encoding="utf-8")
    panel = (directory / "ManualImageToolPanel.qml").read_text(encoding="utf-8")
    assert "root.setOcrRegionDraft(root.selectedOcrLayerId, region)" in workspace
    assert "root.selectOcrRegion()" in workspace
    assert "AppController.setOriginalSubtitleRegion" not in workspace
    assert "function applyTreatment()" in panel
    assert "controller.setManualSubtitleTreatment(treatment, region" in panel
    assert "AppController.setOriginalSubtitleRegion" not in panel
    assert "onClicked: imagePane.inspector.restoreDetectedOcrRegion()" in panel


@pytest.mark.parametrize("downloaded", [False, True])
def test_completed_auto_source_replacement_clears_artifacts_and_finishes_import(tmp_path, monkeypatch, downloaded):
    from pathlib import Path
    from haizflow.schemas.video import VideoConfig
    from haizflow.services import project_store, video_store
    monkeypatch.setattr(project_store, "PROJECT_INDEX_PATH", str(tmp_path / "runtime/projects.json"))
    monkeypatch.setattr(video_store, "LEGACY_VIDEO_WORKSPACES_DIR", str(tmp_path / "legacy"))
    config = VideoConfig(project_name="Auto replacement", project_directory=str(tmp_path / "projects"), project_type="single")
    video = video_store.create_video(f"auto-replace-{tmp_path.name}", "first.mp4", config)
    Path(video.files["video_input"]).write_bytes(b"old source")
    Path(video.files["voice_output"]).write_bytes(b"old voice")
    Path(video.files["final_video"]).write_bytes(b"old render")
    video.status = "done"
    video.progress = 100
    video.checkpoints = {"translation": "previous"}
    video.original_subtitle_region_override = dict(x_percent=0, y_percent=80, width_percent=100, height_percent=10)
    video_store.save_video(video)
    source = tmp_path / "new.mp4"
    source.write_bytes(b"new source")
    host = SimpleNamespace(_selected_video_id=video.video_id, _selected_project_key=video.project_key,
        _media_import_events=queue.Queue(), _media_import_busy=False, _media_import_total=0, _media_import_completed=0,
        _processing_queue=SimpleNamespace(active_video_id="", discard=Mock(return_value=False)),
        sourceReplacementRequested=Mock(), releaseEditorPreview=Mock(), _audio_preview=SimpleNamespace(invalidate=Mock()),
        mediaImportChanged=Mock(), _set_video_path=Mock(), _replace_logs=Mock(), _read_video_logs=Mock(return_value=""),
        videoThumbnailChanged=Mock(), selectedVideoChanged=Mock(), logsChanged=Mock(), _log_queue=queue.Queue(),
        refreshVideos=Mock(), _url_importer=SimpleNamespace(complete_import=Mock()))
    controller = ProjectImportController(host)
    with (patch("haizflow.desktop.project_import_controller.validate_video_integrity"),
          patch.object(controller, "_assign_thumbnail_in_worker")):
        assert controller._queue_replace(video.video_id, str(source), None, url_import=downloaded)
        for worker in tuple(controller._task_threads.values()):
            worker.join(3)
            assert not worker.is_alive()
        controller.drain_background_events()
    updated = video_store.get_video(video.video_id)
    assert updated.status == "pending" and updated.progress == 0
    assert updated.checkpoints == {} and updated.original_subtitle_region_override == {}
    assert Path(updated.files["video_input"]).read_bytes() == b"new source"
    assert not Path(updated.files["voice_output"]).exists()
    assert not Path(updated.files["final_video"]).exists()
    host._set_video_path.assert_called_once_with(updated.files["video_input"], refresh_thumbnail=True)
    host.selectedVideoChanged.emit.assert_called_once()
    assert not host._media_import_busy
    if downloaded:
        host._url_importer.complete_import.assert_called_once_with(True, "")

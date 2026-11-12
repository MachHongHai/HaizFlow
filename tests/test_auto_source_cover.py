"""Auto/Batch coverage is editable without mutating OCR or audio caches."""
import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.desktop.project_commands_controller import ProjectCommandsController
from haizflow.pipeline.process_video import _original_subtitle_region_for_render
from haizflow.schemas.video import VideoConfig
from haizflow.services import batch_settings, project_store, source_cover, video_store
from haizflow.services.processing_resume import can_resume, configuration_snapshot


REGION = dict(x_percent=12, y_percent=76, width_percent=70, height_percent=12)


@pytest.fixture
def video(tmp_path, monkeypatch):
    monkeypatch.setattr(project_store, "PROJECT_INDEX_PATH", str(tmp_path / "projects.json"))
    current = video_store.create_video("cover-" + tmp_path.name, "video.mp4", VideoConfig(
        project_name="Cover", project_type="single", project_directory=str(tmp_path / "projects")))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    return video_store.update_video(current.video_id, video_width=1920, video_height=1080,
        files={**current.files, "video_input": str(source)})


def test_region_roundtrips_config_store_and_batch_defaults(video, tmp_path):
    config = batch_settings.config_for({"originalSubtitleRegion": REGION})
    other = video_store.create_video("cover-batch-" + tmp_path.name, "batch.mp4", config)
    assert video_store.get_video(other.video_id).original_subtitle_region_override == REGION
    assert batch_settings.values_for(other)["originalSubtitleRegion"] == REGION
    automatic = batch_settings.config_for({"originalSubtitleRegion": {}})
    assert automatic.original_subtitle_region_override == {}
    assert batch_settings.differences(batch_settings.values_for(other), {"originalSubtitleRegion": {}}) == ["originalSubtitleRegion"]


@pytest.mark.parametrize("invalid", [{"x_percent": 1}, {**REGION, "width_percent": 110}, {**REGION, "y_percent": float("nan")}])
def test_invalid_regions_cannot_enter_new_configuration(invalid):
    with pytest.raises(ValueError):
        batch_settings.config_for({"originalSubtitleRegion": invalid})


def test_source_preview_reads_small_cache_only_and_never_selects_or_scans(video, tmp_path):
    cache = tmp_path / "ocr.json"
    cache.write_text(json.dumps({"region": REGION}), encoding="utf-8")
    video_store.update_video(video.video_id, files={**video.files, "ocr_region": str(cache)})
    host = SimpleNamespace(_selected_video_id=video.video_id, _selected_project_key=video.project_key,
                           _batch_video_ids=[], selectVideo=Mock())
    before = video_store.get_video(video.video_id).model_dump()
    media = HaizFlowController.sourceCoverPreviewMedia(host, video.video_id)
    assert media["detectedRegion"] == REGION
    assert media["videoSource"].startswith("file:")
    assert media["sourceKey"] == source_cover.source_key(video)
    assert video_store.get_video(video.video_id).model_dump() == before
    host.selectVideo.assert_not_called()
    assert HaizFlowController.sourceCoverPreviewMedia(host, "foreign") == {}
    host._selected_project_key = "another"
    assert HaizFlowController.sourceCoverPreviewMedia(host, video.video_id) == {}


def test_manual_override_bypasses_ocr_but_automatic_uses_existing_scan(video, tmp_path):
    reporter = Mock()
    video.original_subtitle_region_override = REGION
    with patch("haizflow.pipeline.process_video.detect_original_subtitle_region", return_value=REGION) as scan:
        assert _original_subtitle_region_for_render(video, reporter, str(tmp_path)) == REGION
        scan.assert_not_called()
        video.original_subtitle_region_override = {}
        assert _original_subtitle_region_for_render(video, reporter, str(tmp_path)) == REGION
        scan.assert_called_once()


def save_host(video):
    return SimpleNamespace(_selected_video_id=video.video_id, _settings_owner_video_id=video.video_id,
        _selected_project_key=video.project_key, _processing_queue=SimpleNamespace(contains=lambda _: False),
        _remove_original_subtitles=True, _original_subtitle_region_override={},
        persistVideoSettingsFor=Mock(return_value=True), subtitleSettingsChanged=Mock(), previewMediaChanged=Mock())


def test_save_commits_current_draft_and_can_reenable_automatic(video):
    host = save_host(video)
    key = source_cover.source_key(video)
    assert HaizFlowController.saveSourceCoverRegion(host, video.video_id, video.project_key, key, REGION)
    assert host._original_subtitle_region_override == REGION
    host.persistVideoSettingsFor.assert_called_once_with(video.video_id)
    assert HaizFlowController.saveSourceCoverRegion(host, video.video_id, video.project_key, key, {})
    assert host._original_subtitle_region_override == {}


@pytest.mark.parametrize("change", ["selection", "owner", "project", "source", "queued", "keep", "invalid"])
def test_stale_busy_or_invalid_dialog_cannot_commit(video, change):
    host = save_host(video)
    key = source_cover.source_key(video)
    region = REGION
    if change == "selection": host._selected_video_id = "another"
    if change == "owner": host._settings_owner_video_id = "another"
    if change == "project": host._selected_project_key = "another"
    if change == "source": key = "stale-source"
    if change == "queued": host._processing_queue.contains = lambda _: True
    if change == "keep": host._remove_original_subtitles = False
    if change == "invalid": region = {"x_percent": 10}
    assert not HaizFlowController.saveSourceCoverRegion(host, video.video_id, video.project_key, key, region)
    host.persistVideoSettingsFor.assert_not_called()
    assert host._original_subtitle_region_override == {}


def test_failed_commit_keeps_previous_region(video):
    host = save_host(video)
    host.persistVideoSettingsFor.return_value = False
    assert not HaizFlowController.saveSourceCoverRegion(host, video.video_id, video.project_key,
                                                       source_cover.source_key(video), REGION)
    assert host._original_subtitle_region_override == {}


def test_real_save_only_persists_settings_and_preserves_cache_without_starting_work(video):
    files = dict(video.files, voice_output="published-voice.wav", segments="published-subs.json")
    video = video_store.update_video(video.video_id, files=files)
    host = save_host(video)
    host._manual_settings_drafts = {}
    host.refreshVideos = Mock()
    host.selectedVideoChanged = Mock()
    host._video_settings_snapshot = HaizFlowController._video_settings_snapshot
    host._record_video_settings_change = Mock()
    host._apply_setup_to_video = lambda current: HaizFlowController._apply_config_to_video(host, current,
        HaizFlowController._video_config_from_snapshot(current,
            {"original_subtitle_region_override": host._original_subtitle_region_override}))
    host.persistVideoSettingsFor = lambda key: HaizFlowController.persistVideoSettingsFor(host, key)
    with patch("haizflow.pipeline.process_video.detect_original_subtitle_region") as scan, \
         patch("haizflow.pipeline.render.render_video") as render, \
         patch("haizflow.desktop.processing_lifecycle_controller.ProcessingLifecycleController.enqueue_video") as enqueue:
        assert HaizFlowController.saveSourceCoverRegion(host, video.video_id, video.project_key,
                                                       source_cover.source_key(video), REGION)
    scan.assert_not_called()
    render.assert_not_called()
    enqueue.assert_not_called()
    updated = video_store.get_video(video.video_id)
    assert updated.original_subtitle_region_override == REGION
    assert updated.files == files
    assert updated.status == video.status
    assert updated.active_artifacts == video.active_artifacts
    assert updated.checkpoints == video.checkpoints


def test_unrelated_snapshot_edits_keep_the_saved_cover_region(video):
    video.original_subtitle_region_override = REGION
    config = HaizFlowController._video_config_from_snapshot(video, {"tts_voice": "omnivoice:male"})
    assert config.original_subtitle_region_override == REGION


def test_legacy_batch_defaults_do_not_adopt_the_selected_videos_custom_region():
    record = {"project_type": "batch", "batch_settings": {"values": {"targetLanguage": "vi"}}}
    with patch.object(project_store, "get_project", return_value=record):
        assert batch_settings.stable_values("batch", {"originalSubtitleRegion": REGION}, [])["originalSubtitleRegion"] == {}
        record["batch_settings"]["values"]["originalSubtitleRegion"] = REGION
        assert batch_settings.stable_values("batch", {}, [])["originalSubtitleRegion"] == REGION


def test_old_pause_auto_default_remains_resumable_but_region_change_requires_restart(video):
    host = SimpleNamespace(_settings_processing_device="cpu", _selected_video_id="", appAlertRequested=Mock())
    video.status = "paused"
    video.processing_configuration = configuration_snapshot(video, "cpu")
    video.processing_configuration["settings"].pop("original_subtitle_region_override")
    assert can_resume(host, video)
    video.original_subtitle_region_override = REGION
    assert not can_resume(host, video)


@pytest.mark.parametrize("replace", [False, True])
def test_batch_keeps_individual_region_unless_explicitly_replaced(video, replace):
    config = VideoConfig(project_type="batch", project_key="batch", translation_model="q4",
                         speech_recognition_model="small-cpu", tts_provider="vieneu")
    def item(name, region):
        return SimpleNamespace(**{**config.model_dump(), "subtitle_style": config.subtitle_style,
            "original_subtitle_region_override": region}, video_id=name, files={}, status="pending",
            original_filename=name + ".mp4")
    shared, custom = item("shared", {}), item("custom", REGION)
    videos = {v.video_id: v for v in [shared, custom]}
    baseline = batch_settings.values_for(shared)
    host = SimpleNamespace(_selected_project_key="batch", _batch_video_ids=list(videos),
        _settings_processing_device="cpu", _processing_queue=SimpleNamespace(contains=lambda _: False),
        _capture_video_asset_snapshot=lambda v, **_: copy.deepcopy(vars(v)), _restore_video_asset_snapshot=Mock(),
        _record_batch_asset_change=Mock(), _show_app_alert=Mock(), refreshVideos=Mock(), batchChanged=Mock())
    commands = ProjectCommandsController(host)
    changed = {**REGION, "y_percent": 55}
    with patch.object(commands, "batch_settings_values", return_value=baseline), \
         patch("haizflow.desktop.project_commands_controller.video_store.get_video", side_effect=videos.get), \
         patch("haizflow.desktop.project_commands_controller.video_store.update_video") as update, \
         patch("haizflow.desktop.project_commands_controller.project_store.save_batch_settings"):
        assert commands.apply_batch_settings_values("batch", {"originalSubtitleRegion": changed}, replace)
    assert {c.args[0] for c in update.call_args_list} == ({"shared", "custom"} if replace else {"shared"})
    assert all(c.kwargs["original_subtitle_region_override"] == changed for c in update.call_args_list)

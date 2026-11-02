"""Watermark motion is opt-out, persisted and isolated from speech caches."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from haizflow.desktop.editor_preview_controller import EditorPreviewController
from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.pipeline import manual_tools, render
from haizflow.schemas.video import VideoConfig, VideoInfo, WatermarkPosition
from haizflow.services import batch_settings, processing_resume, video_export, video_store


def video_for(**changes):
    return VideoInfo.model_validate({
        **VideoConfig().model_dump(), "video_id": "motion-test", "original_filename": "source.mp4",
        "status": "pending",
        "created_at": "2026-11-02T00:00:00Z", "updated_at": "2026-11-02T00:00:00Z", **changes,
    })


@pytest.mark.parametrize("kind", ["single", "manual", "batch"])
def test_default_and_legacy_watermarks_move_but_opt_out_persists(tmp_path, kind):
    config = VideoConfig(project_type=kind, project_directory=str(tmp_path), watermark_moving=False,
                         watermark_position={"x_percent": 15.5, "y_percent": 25.75})
    video = video_store.create_video("motion-" + kind, "source.mp4", config)
    assert video.watermark_moving is False
    with patch.dict(video_store._VIDEO_METADATA_CACHE, {}, clear=True):
        assert video_store.get_video(video.video_id).watermark_moving is False
        assert video_store.get_video(video.video_id).watermark_position == config.watermark_position
    legacy = video.model_dump()
    legacy.pop("watermark_moving")
    assert VideoInfo.model_validate(legacy).watermark_moving is True
    assert VideoConfig().watermark_moving is True
    assert VideoConfig.model_validate_json(config.model_dump_json()).watermark_moving is False


@pytest.mark.parametrize("moving", [True, False])
def test_batch_settings_round_trip(moving):
    video = video_for(watermark_moving=moving, watermark_position={"x_percent": 12.5, "y_percent": 24.25})
    values = batch_settings.values_for(video)
    assert values["watermarkMoving"] is moving
    assert batch_settings.config_for(values).watermark_moving is moving
    assert batch_settings.config_for(values).watermark_position == video.watermark_position


@pytest.mark.parametrize("saved,expected", [({}, True), ({"watermarkMoving": False}, False)])
def test_saved_batch_defaults_do_not_inherit_another_projects_motion(saved, expected):
    with patch.object(batch_settings.project_store, "get_project", return_value={
        "project_type": "batch", "batch_settings": {"values": saved},
    }):
        values = batch_settings.stable_values("batch", {"watermarkMoving": False}, [])
    assert values["watermarkMoving"] is expected


@pytest.mark.parametrize("factory,args", [
    (render._watermark_filter, ("TEST", 1080, 1920)),
    (render._image_watermark_filter, ("[2:v]", 1080, 1920)),
])
def test_static_watermark_ignores_export_range_clock(factory, args):
    default = factory(*args)
    assert default == factory(*args, moving=True)
    assert "2*PI*t/31" in default
    fixed = factory(*args, moving=False)
    assert fixed == factory(*args, moving=False, time_offset_seconds=42)
    assert "2*PI*0/31" in fixed and "2*PI*0/43+1.2" in fixed
    assert fixed != default


def test_toggle_notifier_is_lightweight_and_idempotent():
    host = SimpleNamespace(_watermark_moving=True, watermarkStyleChanged=Mock())
    setter = HaizFlowController.watermarkMoving.fset
    setter(host, False)
    setter(host, False)
    assert host._watermark_moving is False
    host.watermarkStyleChanged.emit.assert_called_once_with()


def test_manual_toggle_deactivates_visual_exports_not_voice_or_ocr():
    video = video_for(project_type="manual", watermark_text="TEST", status="manual_ready")
    config = VideoConfig.model_validate({**video.model_dump(), "watermark_moving": False})
    host = SimpleNamespace()
    with (patch.object(video_store, "update_video") as update,
          patch.object(video_store, "get_video", return_value=video.model_copy(update={"watermark_moving": False})),
          patch.object(manual_tools.manual_artifacts, "deactivate") as deactivate,
          patch.object(HaizFlowController, "_sync_legacy_editor_visual_settings") as sync):
        HaizFlowController._apply_config_to_video(host, video, config)
    assert update.call_args.kwargs == {"watermark_moving": False}
    assert deactivate.call_args.args[1] == {"visual_proxy", "export"}
    assert sync.call_args.args[-1] == {"watermark"}


def test_auto_render_and_resume_fingerprints_change_only_for_opt_out():
    video = video_for()
    moving = processing_resume.configuration_snapshot(video, "cpu")
    assert "watermark_moving" not in moving["settings"]  # Existing paused tasks remain resumable.
    fixed = video.model_copy(update={"watermark_moving": False})
    assert processing_resume.configuration_snapshot(fixed, "cpu")["settings"]["watermark_moving"] is False
    assert video_export.render_revision(video) != video_export.render_revision(fixed)


def test_manual_export_identity_changes_but_speech_identity_does_not(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    video = video_for(project_type="manual", watermark_text="TEST", files={"video_input": str(source)})
    fixed = video.model_copy(update={"watermark_moving": False})
    with (patch.object(manual_tools, "_current_subtitle_record", return_value=None),
          patch.object(manual_tools, "_artifact_ready", return_value=False),
          patch.object(manual_tools, "_load_segments", return_value=[
              {"segment_id": "cue", "start": 0, "end": 1, "text": "Xin chào"}]),
          patch.object(manual_tools.editor_documents, "load", return_value=None)):
        assert manual_tools.export_signature(video) != manual_tools.export_signature(fixed)
        voice = manual_tools.voice_signature(video)
        assert voice and voice == manual_tools.voice_signature(fixed)
        assert manual_tools.audio_signature(video) == manual_tools.audio_signature(fixed)


def test_manual_proxy_does_not_render_again_for_motion_toggle():
    settings = dict(video_id="motion", source_identity={}, crop={}, output_format="keep_ratio",
                    remove_original_subtitles=False, removal_mode="keep", watermark_text="TEST",
                    watermark_scale_percent=100, ocr_region={}, preview_encoding="test")
    base = EditorPreviewController._base_visual_cache_payload
    assert base(settings) != base({**settings, "watermark_moving": False})
    settings["independent_manual_preview"] = True
    assert base(settings) == base({**settings, "watermark_moving": False})


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1, 101])
def test_watermark_position_rejects_unsafe_coordinates(bad):
    with pytest.raises(ValueError):
        WatermarkPosition(x_percent=bad, y_percent=50)


@pytest.mark.parametrize("factory,args", [
    (render._watermark_filter, ("TEST", 1080, 1920)),
    (render._image_watermark_filter, ("[2:v]", 1080, 1920)),
])
def test_dragged_position_is_fixed_and_ignored_when_automatic_motion_is_enabled(factory, args):
    point = {"x_percent": 12.5, "y_percent": 24.25}
    fixed = factory(*args, moving=False, position=point)
    assert "*0.12500000" in fixed and "*0.24250000" in fixed
    assert fixed == factory(*args, moving=False, position=point, time_offset_seconds=30)
    assert factory(*args, moving=True, position=point) == factory(*args)


def test_manual_position_commit_saves_once_and_rolls_back_failed_save():
    class Host:
        watermarkPosition = property(
            HaizFlowController.watermarkPosition.fget, HaizFlowController.watermarkPosition.fset)
        watermarkMoving = property(HaizFlowController.watermarkMoving.fget, HaizFlowController.watermarkMoving.fset)

    host = Host()
    host._watermark_position = {}
    host._watermark_moving = True
    host.watermarkStyleChanged = Mock()
    host.canEditSelectedVideo = True
    host._selected_video = lambda: video_for(project_type="manual")
    host.saveSelectedVideoSettings = Mock(return_value=True)
    point = {"x_percent": 20, "y_percent": 30}
    assert HaizFlowController.commitManualWatermarkPosition(host, point)
    host.saveSelectedVideoSettings.assert_called_once_with()
    assert host.watermarkPosition == point and host.watermarkMoving is False
    host.saveSelectedVideoSettings.return_value = False
    assert not HaizFlowController.commitManualWatermarkPosition(host, {"x_percent": 50, "y_percent": 60})
    assert host.watermarkPosition == point and host.watermarkMoving is False
    host.canEditSelectedVideo = False
    host.saveSelectedVideoSettings.reset_mock()
    assert not HaizFlowController.commitManualWatermarkPosition(host, {"x_percent": 0, "y_percent": 0})
    host.saveSelectedVideoSettings.assert_not_called()


def test_position_and_motion_are_one_atomic_settings_undo():
    from haizflow.desktop.manual_edit_history import AppEditHistory

    old = video_for(project_type="manual")
    point = WatermarkPosition(x_percent=20, y_percent=30)
    new = old.model_copy(update={"watermark_position": point, "watermark_moving": False})
    snapshot = HaizFlowController._video_settings_snapshot
    state = [new]
    history = AppEditHistory()
    history.select_video(old.video_id)

    def apply(_id, values):
        config = HaizFlowController._video_config_from_snapshot(state[0], values)
        state[0] = state[0].model_copy(update={"watermark_position": config.watermark_position,
                                            "watermark_moving": config.watermark_moving})
        return True

    host = SimpleNamespace(_edit_history_recording_suspended=False, _manual_edit_history=history,
                           _apply_video_settings_snapshot=apply)
    HaizFlowController._record_video_settings_change(host, old.video_id, snapshot(old), snapshot(new))
    assert len(history._undo) == 1
    assert history.undo() and state[0].watermark_position is None and state[0].watermark_moving is True
    assert history.redo() and state[0].watermark_position == point and state[0].watermark_moving is False

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

from haizflow.desktop.project_commands_controller import ProjectCommandsController
from haizflow.schemas.video import SubtitleStyle, VideoConfig
from haizflow.services import batch_settings, project_store, video_store


def test_resolution_scaling_keeps_positions_and_proportional_type():
    shared = {"subtitleReferenceWidth": 1080, "subtitleReferenceHeight": 1920,
        "subtitleStyle": {**SubtitleStyle(font_size=55, position_y_percent=65).model_dump(), "manual": True}}
    original = deepcopy(shared)
    small = batch_settings.values_for_video(shared, SimpleNamespace(video_width=576, video_height=1024))
    assert small["subtitleStyle"]["font_size"] == 29
    assert small["subtitleStyle"]["position_y_percent"] == 65
    assert small["subtitleStyle"]["manual"]
    assert shared == original
    large = batch_settings.values_for_video(shared, SimpleNamespace(video_width=1080, video_height=1920))
    assert large == shared
    assert batch_settings.config_for(shared).batch_subtitle_reference_width == 1080


def test_apply_to_mixed_resolution_batch_and_report_real_overrides(monkeypatch):
    config = VideoConfig(project_type="batch", tts_provider="vieneu", speech_recognition_model="small-cpu",
                         subtitle_style=SubtitleStyle(font_size=55, position_y_percent=65), subtitle_layout_override=True)
    records = {key: SimpleNamespace(**{**config.model_dump(), "subtitle_style": config.subtitle_style.model_copy(),
        "video_id": key, "original_filename": key + ".mp4", "video_width": width, "video_height": height,
        "files": {}, "status": "done", "progress": 100, "step": "done", "error": None, "resume_step": ""})
        for key, width, height in [("large",1080,1920), ("small",576,1024)]}
    saved = batch_settings.values_for(records["large"])
    host = SimpleNamespace(_selected_project_key="batch", _selected_video_id="", _batch_video_ids=list(records),
        _settings_processing_device="cpu", _processing_queue=SimpleNamespace(contains=lambda _: False),
        _capture_video_asset_snapshot=lambda video, **_: deepcopy(video.__dict__),
        _record_batch_asset_change=Mock(), refreshVideos=Mock(), batchChanged=Mock(), _show_app_alert=Mock())
    commands = ProjectCommandsController(host)
    monkeypatch.setattr(commands, "batch_settings_values", lambda: deepcopy(saved))
    monkeypatch.setattr(video_store, "get_video", records.get)
    monkeypatch.setattr(video_store, "update_video", lambda key, **changes: records[key].__dict__.update(changes))
    monkeypatch.setattr(project_store, "save_batch_settings", lambda _key, values: saved.update(deepcopy(values)))
    assert commands.apply_batch_settings_values("batch", {"subtitleReferenceWidth":1080,
        "subtitleReferenceHeight":1920}, replace_overrides=True)
    assert records["small"].subtitle_style.font_size == 29
    assert records["large"].subtitle_style.font_size == 55
    assert commands.batch_setting_overrides() == []
    records["small"].subtitle_style.position_y_percent = 80
    assert commands.batch_setting_overrides() == [{"videoId":"small", "fileName":"small.mp4", "differences":["subtitleStyle"]}]

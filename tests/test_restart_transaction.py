"""Restart never leaves an old manifest pointing to partly deleted cache."""

import os
import uuid
from pathlib import Path

import pytest

from hflow.schemas.video import VideoConfig
from hflow.services import manual_artifacts, project_store, video_store


@pytest.fixture
def old_video(tmp_path):
    project = project_store.create_project("Restart " + uuid.uuid4().hex[:8], str(tmp_path), "single")
    config = VideoConfig(project_type="single", project_key=project["key"], project_id=project["project_id"],
                         project_name=project["project_name"], project_directory=str(tmp_path))
    video = video_store.create_video(uuid.uuid4().hex, "source.mp4", config)
    source = Path(video.files["video_input"])
    source.write_bytes(b"input kept")
    music = source.parent / "music.mp3"
    music.write_bytes(b"music kept")
    temporary = Path(video_store.get_video_dir(video.video_id)) / "temp"
    temporary.mkdir(exist_ok=True)
    (temporary / "voice_final.wav").write_bytes(b"old voice")
    staging = manual_artifacts.create_staging_directory(video.video_id, "export")
    (staging / "video.mp4").write_bytes(b"old render")
    record = manual_artifacts.publish(video.video_id, "export", "old", staging, {"video": "video.mp4"})
    video_store.update_video(video.video_id, status="paused", checkpoints={"render": "old"},
        files={**video.files, "background_music": str(music), "final_video": record["resolved_outputs"]["video"]})
    return video_store.get_video(video.video_id), record, temporary


def test_locked_temp_rename_rolls_back_previously_moved_cache(old_video, monkeypatch):
    video, record, temporary = old_video
    replace = os.replace
    def locked(source, destination):
        if Path(source) == temporary:
            raise PermissionError(13, "WinError 32: temp locked")
        return replace(source, destination)
    monkeypatch.setattr("hflow.services.video_store.os.replace", locked)
    with pytest.raises(PermissionError):
        video_store.prepare_video_restart(video.video_id)
    assert (temporary / "voice_final.wav").read_bytes() == b"old voice"
    assert Path(record["resolved_outputs"]["video"]).read_bytes() == b"old render"
    assert manual_artifacts.resolve(video.video_id, "export", "old")
    assert video_store.get_video(video.video_id).checkpoints == {"render": "old"}


def test_metadata_failure_restores_old_files_and_references(old_video, monkeypatch):
    video, record, temporary = old_video
    save = video_store._save_video_unlocked
    calls = 0
    def fail_once(current):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError(13, "metadata locked")
        return save(current)
    monkeypatch.setattr(video_store, "_save_video_unlocked", fail_once)
    with pytest.raises(PermissionError):
        video_store.prepare_video_restart(video.video_id)
    assert (temporary / "voice_final.wav").read_bytes() == b"old voice"
    assert Path(record["resolved_outputs"]["video"]).read_bytes() == b"old render"
    restored = video_store.get_video(video.video_id)
    assert restored.status == "paused" and restored.active_artifacts == {"export": "old"}


def test_successful_restart_is_clean_and_keeps_input_assets(old_video):
    video, record, temporary = old_video
    restarted = video_store.prepare_video_restart(video.video_id)
    assert restarted.active_artifacts == {} and restarted.checkpoints == {}
    assert not (temporary / "voice_final.wav").exists()
    assert not Path(record["resolved_outputs"]["video"]).exists()
    assert Path(restarted.files["video_input"]).read_bytes() == b"input kept"
    assert Path(restarted.files["background_music"]).read_bytes() == b"music kept"
    assert (temporary / "voice_parts").is_dir()
    assert not list(temporary.parent.glob(".processing-backup-restart-*"))

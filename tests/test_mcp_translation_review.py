"""Text-only correction must preserve source/timings/speakers and never run models."""
import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from haizflow.desktop.project_commands_controller import ProjectCommandsController
from haizflow.mcp.translation_review import context_rows, patch


@pytest.fixture
def state():
    return {"revision": "revision-v1", "source": [{"start": 0, "end": 2, "text": "My sister is here."}],
            "segments": [{"segment_id": "seg-a", "start": 0, "end": 2, "speaker": "speaker-a",
                          "text": "Bạn của tôi tới rồi.", "extra": {"keep": True}},
                         {"segment_id": "seg-b", "start": 2, "end": 4, "text": "Chào bạn."}]}


def test_source_target_context_and_pagination(state):
    rows = context_rows(state, 0, 1)
    assert len(rows) == 1 and rows[0]["cue_id"] == "cue-1"
    assert rows[0]["source_matches"][0]["text"] == "My sister is here."
    assert rows[0]["speaker"] == "speaker-a"
    assert context_rows(state, 1, 1)[0]["cue_id"] == "cue-2"


def test_patch_preserves_all_non_text_data_and_unmodified_cues(state):
    before = copy.deepcopy(state)
    updated, changed = patch(state, [{"cue_id": "cue-1", "expected_text": "Bạn của tôi tới rồi.",
                                     "text": "Chị gái tôi tới rồi."}], "revision-v1")
    assert changed == ["cue-1"]
    expected = copy.deepcopy(before["segments"])
    expected[0]["text"] = "Chị gái tôi tới rồi."
    assert updated == expected
    assert state == before


@pytest.mark.parametrize("edits,revision", [
    ([{"cue_id": "cue-1", "expected_text": "Bạn của tôi tới rồi.", "text": "Khác"}], "stale"),
    ([{"cue_id": "cue-1", "expected_text": "already changed", "text": "Khác"}], "revision-v1"),
    ([{"cue_id": "cue-99", "expected_text": "", "text": "Khác"}], "revision-v1"),
    ([{"cue_id": "cue-1", "expected_text": "Bạn của tôi tới rồi.", "text": "Khác", "start": 99}], "revision-v1"),
])
def test_bad_patch_does_not_mutate_any_cue(state, edits, revision):
    before = copy.deepcopy(state)
    with pytest.raises(ValueError):
        patch(state, edits, revision)
    assert state == before


@pytest.mark.parametrize("status", ["done", "paused"])
def test_auto_commit_without_processing_does_not_enqueue_or_touch_original(tmp_path, monkeypatch, status):
    from haizflow.schemas.video import VideoConfig, VideoInfo

    source, translated = tmp_path / "source.json", tmp_path / "translated.json"
    source.write_text('[{"start":0,"end":2,"text":"My sister"}]', encoding="utf-8")
    translated.write_text('[{"start":0,"end":2,"text":"Bạn tôi"}]', encoding="utf-8")
    config = VideoConfig(project_type="single")
    video = VideoInfo(**config.model_dump(), video_id="review-auto", original_filename="input.mp4",
                      status=status, created_at="now", updated_at="now",
                      files={"transcript_json": str(translated)}, checkpoints={"translation": "old", "render": "old"})
    host = SimpleNamespace(_selected_video_id=video.video_id, _show_app_alert=Mock(), _enqueue_video=Mock(),
                           selectedVideoChanged=Mock())
    update, deactivate = Mock(), Mock()
    monkeypatch.setattr("haizflow.services.video_store.get_video", lambda _id: video)
    monkeypatch.setattr("haizflow.services.video_store.update_video", update)
    monkeypatch.setattr("haizflow.services.video_store.log_to_video", Mock())
    monkeypatch.setattr("haizflow.services.manual_artifacts.deactivate", deactivate)
    command = ProjectCommandsController(host)
    assert command.approve_translation_review(json.dumps([{"start": 0, "end": 2, "text": "Chị gái tôi"}]),
                                              continue_processing=False)
    host._enqueue_video.assert_not_called()
    assert json.loads(translated.read_text("utf-8"))[0]["text"] == "Chị gái tôi"
    assert "My sister" in source.read_text("utf-8")
    assert update.call_args.kwargs["status"] == "paused"
    assert update.call_args.kwargs["checkpoints"] == {"translation": "old"}
    deactivate.assert_called_once_with(video.video_id, {"export", "visual_proxy"})


def test_auto_snapshot_reads_owned_original_and_tracks_source_changes(tmp_path, monkeypatch):
    from haizflow.mcp.translation_review import snapshot
    from haizflow.schemas.video import VideoConfig, VideoInfo

    (tmp_path / "temp").mkdir()
    source = tmp_path / "temp" / "source_segments.json"
    translated = tmp_path / "translated.json"
    source.write_text('[{"start":0,"end":2,"text":"Sister"}]', encoding="utf-8")
    translated.write_text('[{"start":0,"end":2,"text":"Chị gái"}]', encoding="utf-8")
    video = VideoInfo(**VideoConfig(project_type="single").model_dump(), video_id="snapshot-auto",
                      original_filename="input.mp4", status="done", created_at="now", updated_at="now",
                      files={"transcript_json": str(translated)})
    monkeypatch.setattr("haizflow.services.video_store.get_video_dir", lambda _id: str(tmp_path))
    first = snapshot(video)
    assert first["source"][0]["text"] == "Sister"
    assert context_rows(first)[0]["source_matches"][0]["text"] == "Sister"
    source.write_text('[{"start":0,"end":2,"text":"Brother"}]', encoding="utf-8")
    assert snapshot(video)["revision"] != first["revision"]

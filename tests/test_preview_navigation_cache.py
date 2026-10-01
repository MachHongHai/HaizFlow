"""Processed Manual previews survive route teardown while voice work runs."""

import json
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QUrl

from haizflow.desktop.editor_preview_controller import EditorPreviewController
from haizflow.schemas.video import CropSettings, SubtitleStyle


@pytest.fixture
def preview_session(tmp_path, monkeypatch):
    videos = {
        name: SimpleNamespace(
            video_id=name, project_type="manual", status="manual_ready",
            subtitle_style=SubtitleStyle(), crop=CropSettings(),
            remove_original_subtitles=True, original_subtitle_removal_mode="patch",
            files={},
        ) for name in ("a", "b")
    }
    for name in videos:
        (tmp_path / name).mkdir()
        (tmp_path / name / "source.mp4").write_bytes(b"unprocessed-source")
    host = SimpleNamespace(
        selected=videos["a"], manualPreviewAudio=object(),
        editorPreviewChanged=SimpleNamespace(emit=Mock()),
    )
    host._selected_video = lambda: host.selected
    host._resolve_video_file = lambda video, *_args: str(tmp_path / video.video_id / "source.mp4")
    module = "haizflow.desktop.editor_preview_controller"
    monkeypatch.setattr(f"{module}.video_store.get_video_dir", lambda video_id: str(tmp_path / video_id))
    monkeypatch.setattr(f"{module}.video_store.get_video", lambda _video_id: None)
    monkeypatch.setattr("haizflow.services.editor_documents.load", lambda _video_id: None)
    monkeypatch.setattr(f"{module}.manual_artifacts.pin", Mock())
    monkeypatch.setattr(f"{module}.manual_artifacts.unpin", Mock())
    monkeypatch.setattr(f"{module}.cancel_video", Mock())
    controller = EditorPreviewController(host)
    monkeypatch.setattr(controller, "_manual_voice_artifact", lambda _video: None)
    finished = threading.Event()

    def render(generation, _process_id, video, settings, _preview_dir):
        output = tmp_path / video.video_id / "processed-preview.mp4"
        output.write_bytes(b"processed-blur-crop-preview")
        controller._finish_success(
            generation, output, 0, 120, video_id=video.video_id,
            request_fingerprint=settings["request_fingerprint"], base_playback_path=output,
        )
        finished.set()

    renderer = Mock(side_effect=render)
    monkeypatch.setattr(controller, "_render", renderer)

    def prime(name):
        host.selected = videos[name]
        finished.clear()
        assert controller.request(json.dumps([]), 22)
        assert finished.wait(2)
        assert controller.stage == "ready"

    yield host, controller, renderer, videos, prime, tmp_path
    controller.release()


def test_return_to_running_voice_restores_processed_cache_without_render(preview_session):
    host, controller, renderer, videos, prime, _ = preview_session
    prime("a")
    cached = controller.base_source
    assert "processed-preview" in cached
    controller.release()
    assert controller.base_source == ""
    prime("b")
    controller.release()
    host.selected = videos["a"]
    videos["a"].status = "processing"
    videos["a"].manual_target_tool = "voice"
    videos["a"].tts_voice = "omnivoice:clone"
    assert controller.request(json.dumps([{"start": 0, "end": 2, "text": "Edited"}]), 44, cache_only=True)
    assert controller.base_source == cached
    assert controller.source == cached
    assert controller.stage == "ready"
    assert not controller.busy
    assert renderer.call_count == 2
    assert controller.audio_source == ""


def test_cache_only_miss_does_not_start_preview_worker(preview_session):
    _, controller, renderer, _, _, _ = preview_session
    assert not controller.request("[]", 0, cache_only=True)
    assert renderer.call_count == 0
    assert controller.source == controller.base_source == ""
    assert not controller.busy


def test_changed_effects_do_not_resurrect_stale_preview(preview_session):
    _, controller, renderer, videos, prime, _ = preview_session
    prime("a")
    controller.release()
    videos["a"].original_subtitle_removal_mode = "blur"
    assert not controller.request("[]", 0, cache_only=True)
    assert renderer.call_count == 1
    assert controller.base_source == ""


def test_corrupt_cache_is_not_opened_or_rebuilt_during_voice(preview_session):
    _, controller, renderer, _, prime, _ = preview_session
    prime("a")
    path = QUrl(controller.base_source).toLocalFile()
    controller.release()
    with open(path, "wb") as file:
        file.write(b"broken")
    assert not controller.request("[]", 0, cache_only=True)
    assert renderer.call_count == 1
    assert controller.source == controller.base_source == ""


def test_missing_manual_base_is_not_reported_as_ready(preview_session):
    _, controller, renderer, _, prime, _ = preview_session
    prime("a")
    controller.release()
    controller._completed_base_sources.clear()
    assert not controller.request("[]", 0, cache_only=True)
    assert renderer.call_count == 1
    assert controller.stage != "ready"

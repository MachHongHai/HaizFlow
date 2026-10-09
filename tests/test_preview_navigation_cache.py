"""Processed Manual previews survive route teardown while voice work runs."""

import json
import threading
from pathlib import Path
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


def test_replacement_cannot_reopen_and_repin_a_released_preview(preview_session):
    from haizflow.desktop.project_import_controller import ProjectImportController
    host, controller, renderer, videos, prime, _ = preview_session
    host._project_import = ProjectImportController(host)
    prime("a")
    controller.release()
    before = renderer.call_count
    host._project_import._tasks[1] = {"operation": "replace", "video_id": "a"}
    assert not controller.request("[]", 0)
    assert controller.source == "" and controller._pinned_video_id == ""
    assert renderer.call_count == before
    # A replacement in another project must not prevent opening this cache.
    host._project_import._tasks[1]["video_id"] = "b"
    assert controller.request("[]", 0)
    assert controller.source and controller._pinned_video_id == "a"
    assert renderer.call_count == before


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


def test_processed_project_restores_disk_cache_while_another_project_runs(preview_session, monkeypatch):
    host, controller, renderer, videos, prime, root = preview_session
    prime("b")
    fingerprint = controller._request_fingerprint
    directory = root / "b/temp/editor-preview" / f"base-{fingerprint[:20]}"
    directory.mkdir(parents=True)
    output = directory / "preview.mp4"
    output.write_bytes(b"complete-treated-base")
    controller._write_completion_marker(directory / "preview.complete.json", output, 120)
    controller.release()
    controller._completed_requests.clear()
    controller._completed_base_sources.clear()
    videos["a"].status = "processing"
    host.isProcessing = True
    host.selected = videos["b"]
    # The facade must use the selected video, never global processing state.
    from haizflow.desktop.qml_controller import HaizFlowController
    host._editor_preview = controller
    host.isSelectedVideoQueued = False
    probe = Mock(side_effect=AssertionError("Completed caches must not invoke FFprobe"))
    monkeypatch.setattr("haizflow.desktop.editor_preview_controller.get_video_duration", probe)
    assert HaizFlowController.requestEditorPreview(host, "[]", 30)
    assert Path(QUrl(controller.base_source).toLocalFile()) == output.resolve()
    assert controller.stage == "ready" and not controller.busy
    assert renderer.call_count == 1
    assert videos["a"].status == "processing"
    probe.assert_not_called()


@pytest.mark.parametrize("invalid", ["size", "duration", "json", "effects"])
def test_disk_cache_recovery_never_opens_incomplete_or_stale_files(preview_session, invalid):
    _, controller, renderer, videos, prime, root = preview_session
    prime("a")
    fingerprint = controller._request_fingerprint
    directory = root / "a/temp/editor-preview" / f"base-{fingerprint[:20]}"
    directory.mkdir(parents=True)
    output = directory / "preview.mp4"
    output.write_bytes(b"complete-treated-base")
    marker = directory / "preview.complete.json"
    controller._write_completion_marker(marker, output, 120)
    if invalid == "size":
        output.write_bytes(b"truncated")
    elif invalid == "duration":
        marker.write_text(json.dumps({"version": 1, "size": output.stat().st_size, "duration": 0}))
    elif invalid == "json":
        marker.write_text("{invalid")
    else:
        videos["a"].original_subtitle_removal_mode = "blur"
    controller.release()
    controller._completed_requests.clear()
    controller._completed_base_sources.clear()
    assert not controller.request("[]", 0, cache_only=True)
    assert controller.base_source == ""
    assert renderer.call_count == 1

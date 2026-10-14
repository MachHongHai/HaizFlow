"""Cancel export-owned runs only; queue detach is independent of current page."""

import threading
from types import SimpleNamespace
from unittest.mock import Mock

from PySide6.QtCore import QObject
from PySide6.QtGui import QGuiApplication

from hflow.desktop.video_export_controller import VideoExportController
from hflow.services.processing_queue import SerialProcessingQueue


def host_for(task_queue):
    host = QObject()
    host._settings_language = "vi"
    host._selected_video_id = "unrelated-project"
    host._processing_queue = task_queue
    for name in ("exportStateChanged", "selectedVideoChanged", "processingChanged"):
        setattr(host, name, Mock())
    host.refreshVideos = Mock()
    return host


def test_cancel_detaches_only_owned_waiters_and_cancels_owned_active_render(monkeypatch):
    app = QGuiApplication.instance() or QGuiApplication([])
    started, release = threading.Event(), threading.Event()
    ran = []
    def runner(identifier):
        ran.append(identifier)
        if identifier == "active-export":
            started.set()
            release.wait(5)
    task_queue = SerialProcessingQueue(runner)
    host = host_for(task_queue)
    exporter = VideoExportController(host)
    exporter.timer.stop()
    videos = {key: SimpleNamespace(step="manual_export", resume_step="manual_export", checkpoints={"voice": True})
              for key in ("active-export", "waiting-export", "unrelated")}
    update = Mock()
    pause = Mock()
    monkeypatch.setattr("hflow.desktop.video_export_controller.video_store.get_video", videos.get)
    monkeypatch.setattr("hflow.desktop.video_export_controller.video_store.update_video", update)
    monkeypatch.setattr("hflow.pipeline.process_registry.cancel_video", pause)
    try:
        assert task_queue.enqueue("active-export") and started.wait(1)
        assert task_queue.enqueue("waiting-export") and task_queue.enqueue("unrelated")
        exporter.jobs = [{"videoId": key, "status": "rendering", "progress": 10}
                         for key in ("active-export", "waiting-export")]
        for job in exporter.jobs:
            exporter._capture_render_owner(job)
        exporter.cancel_all()
        pause.assert_called_once_with("active-export")
        assert task_queue.pending_ids() == ["unrelated"]
        assert all(job["status"] == "cancelled" for job in exporter.jobs)
        assert exporter.busy  # Wait for the producer's finally/cleanup.
        assert {call.args[0] for call in update.call_args_list} == {"active-export", "waiting-export"}
        assert all(video.checkpoints == {"voice": True} for video in videos.values())
    finally:
        release.set()
        assert task_queue.shutdown(timeout_seconds=2)
        exporter.shutdown()
        app.processEvents()
    assert not exporter.busy and "waiting-export" not in ran


def test_old_export_token_cannot_cancel_new_run_of_same_video(monkeypatch):
    app = QGuiApplication.instance() or QGuiApplication([])
    started, release = threading.Event(), threading.Event()
    task_queue = SerialProcessingQueue(lambda _key: (started.set(), release.wait(5)))
    host = host_for(task_queue)
    exporter = VideoExportController(host)
    exporter.timer.stop()
    pause = Mock()
    monkeypatch.setattr("hflow.pipeline.process_registry.cancel_video", pause)
    try:
        assert task_queue.enqueue("same-video") and started.wait(1)
        token = task_queue.token_for("same-video")
        exporter.jobs = [{"videoId": "same-video", "status": "paused", "renderToken": token - 1}]
        exporter.cancel_all()
        pause.assert_not_called()
        assert task_queue.token_for("same-video") == token and task_queue.contains("same-video")
    finally:
        release.set()
        task_queue.shutdown(timeout_seconds=2)
        exporter.shutdown()
        app.processEvents()

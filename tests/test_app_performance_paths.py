import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QSignalSpy

from haizflow.desktop.project_workspace_controller import ProjectWorkspaceController
from haizflow.desktop.video_export_controller import ExportJobModel, export_job_summary
from haizflow.services import video_store
from haizflow.services import manual_artifacts


def test_catalog_io_is_off_thread_and_stale_results_are_discarded(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []
    host = SimpleNamespace(_background_events_timer=object())
    workspace = ProjectWorkspaceController(host)
    revision = [4]
    monkeypatch.setattr(video_store, "metadata_revision", lambda: revision[0])

    def collect():
        captured = revision[0]
        calls.append(threading.get_ident())
        entered.set()
        release.wait(2)
        return captured, [], [], []

    workspace._collect_catalog = collect
    workspace._apply_catalog = Mock()
    workspace.refresh_videos()
    assert entered.wait(1)
    assert calls[0] != threading.get_ident()
    assert workspace._refresh_running
    revision[0] = 5
    release.set()
    deadline = time.monotonic() + 3
    while not workspace._apply_catalog.called and time.monotonic() < deadline:
        workspace.drain_events()
        time.sleep(.005)
    assert workspace._apply_catalog.call_args.args[0] == 5
    assert len(calls) == 2
    workspace.close()
    workspace.refresh_videos()
    assert len(calls) == 2


def test_catalog_refresh_requests_are_coalesced(monkeypatch):
    release, entered = threading.Event(), threading.Event()
    monkeypatch.setattr(video_store, "metadata_revision", lambda: 4)
    workspace = ProjectWorkspaceController(SimpleNamespace(_background_events_timer=object()))
    def collect():
        entered.set()
        release.wait(2)
        return 4, [], [], []
    workspace._collect_catalog = Mock(side_effect=collect)
    workspace._apply_catalog = Mock()
    workspace.refresh_videos()
    assert entered.wait(1)
    for _ in range(30):
        workspace.refresh_videos()
    assert workspace._collect_catalog.call_count == 1
    release.set()
    deadline = time.monotonic() + 3
    while not workspace._apply_catalog.called and time.monotonic() < deadline:
        workspace.drain_events()
        time.sleep(.005)
    assert workspace._collect_catalog.call_count == 2
    assert workspace._apply_catalog.call_count == 1
    workspace.close()


def test_export_progress_only_notifies_the_changed_row():
    app = QGuiApplication.instance() or QGuiApplication([])
    model = ExportJobModel()
    jobs = [{"videoId": str(i), "path": str(i), "progress": 0} for i in range(1000)]
    model.sync(jobs)
    reset, changed = QSignalSpy(model.modelReset), QSignalSpy(model.dataChanged)
    jobs[513]["progress"] = 40
    model.sync(jobs)
    assert reset.count() == 0
    assert changed.count() == 1
    assert changed.at(0)[0].row() == 513
    model.sync(jobs)
    assert changed.count() == 1
    assert model.data(model.index(513), model.JobRole)["progress"] == 40


def test_export_summary_and_strip_choose_the_same_measured_job():
    jobs = [{"videoId": "a", "status": "done", "progress": 100},
            {"videoId": "b", "status": "exporting", "progress": 57},
            {"videoId": "c", "status": "pending", "progress": 0},
            {"videoId": "d", "status": "failed", "progress": 1}]
    summary = export_job_summary(jobs)
    assert summary["activeJob"] == jobs[1]
    assert summary["activeJob"]["progress"] == 57
    assert summary["activeVideoIds"] == ["b", "c"]
    assert (summary["done"], summary["failed"], summary["waiting"]) == (1, 1, False)


def test_fresh_artifact_digest_is_not_read_again(tmp_path, monkeypatch):
    output = tmp_path / "video.mp4"
    output.write_bytes(b"managed render")
    original = manual_artifacts._sha256
    digest = Mock(wraps=original)
    monkeypatch.setattr(manual_artifacts, "_sha256", digest)
    _, checksums, _ = manual_artifacts._output_records(tmp_path, {"video": "video.mp4"})
    assert manual_artifacts._has_expected_digest(output, checksums["video"]["size"], checksums["video"]["sha256"])
    assert digest.call_count == 1
    output.write_bytes(b"broken render!")
    assert not manual_artifacts._has_expected_digest(output, checksums["video"]["size"], checksums["video"]["sha256"])


def test_overlay_static_payloads_are_not_serialized_on_every_tick(monkeypatch):
    from haizflow.desktop.manual_editor_document_model import ManualEditorDocumentModel
    from haizflow.desktop.manual_preview_composition_controller import ManualPreviewCompositionController
    from haizflow.schemas.editor import EditorClip, EditorDocument, EditorTrack
    app = QGuiApplication.instance() or QGuiApplication([])
    document = EditorDocument(video_id="overlay-perf", tracks=[
        EditorTrack(track_id="overlays", name="Overlay", kind="overlay")], clips=[
        EditorClip(clip_id="image", track_id="overlays", kind="image", duration_ms=10000)])
    model = ManualEditorDocumentModel()
    model.set_document(document)
    preview = ManualPreviewCompositionController(model)
    serialize = Mock(side_effect=AssertionError("Playback must not serialize static clip data"))
    monkeypatch.setattr(EditorClip, "model_dump", serialize)
    try:
        for index in range(1, 100):
            preview.setTime(index * .02)
        assert len(preview.overlays) == 1
        serialize.assert_not_called()
    finally:
        preview.close()
        model.close()

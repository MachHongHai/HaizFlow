from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtGui import QGuiApplication

from haizflow.desktop.project_workspace_controller import ProjectWorkspaceController
from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.services import editor_documents, video_store


def catalog_host(video):
    model = lambda: SimpleNamespace(update_video=Mock(return_value=True), update_project=Mock(return_value=True),
                                    set_videos=Mock(), set_projects=Mock())
    summary = {"key": video.project_key, "project_type": "batch"}
    return SimpleNamespace(_catalog_videos={video.video_id: video}, _video_project_key=lambda v: v.project_key,
        _batch_video_ids=[video.video_id], _selected_video_id=None,
        _project_summaries_by_key={video.project_key: summary}, _build_project_summaries=Mock(return_value=[summary]),
        videos=model(), batch_videos=model(), projects=model(), batch_projects=model(), single_projects=model(),
        manual_projects=model(), download_projects=model(), publish_projects=model(),
        _refresh_batch_model=Mock(), selectedVideoChanged=Mock(), projectCatalogChanged=Mock(),
        _thumbnail_refresh_running=False)


@pytest.mark.parametrize("change,settings,results", [({"progress": 30}, False, False),
    ({"status": "done"}, False, True), ({"step": "finalizing"}, False, True),
    ({"tts_provider": "vieneu-gpu"}, True, False), ({"active_artifacts": {"image": "new"}}, True, False)])
def test_batch_progress_does_not_invalidate_settings_or_results(monkeypatch, change, settings, results):
    previous = SimpleNamespace(video_id="one", project_key="batch", project_type="batch", status="processing",
                               progress=5, step="voice", error="", files={}, original_filename="one.mp4")
    host = catalog_host(previous)
    current = SimpleNamespace(**{**vars(previous), **change})
    monkeypatch.setattr(video_store, "get_video", lambda _: current)
    workspace = ProjectWorkspaceController(host)
    assert workspace.apply_video_metadata_changes({"one"})
    assert host._batch_metadata_settings_changed is settings
    assert host._batch_metadata_results_changed is results
    # Repeated metadata updates reuse membership rather than scan all projects.
    class NoRescan(dict):
        def values(self): raise AssertionError("Incremental update scanned the full catalogue")
        def items(self): raise AssertionError("Incremental update rebuilt membership")
    replacement = NoRescan(host._catalog_videos)
    host._catalog_videos = replacement
    workspace._catalog_members_source = replacement
    assert workspace.apply_video_metadata_changes({"one"})


def test_first_catalogue_is_loading_until_models_are_published_even_if_empty():
    host = catalog_host(SimpleNamespace(video_id="one", project_key="batch"))
    assert HaizFlowController.projectCatalogState.fget(host) == "loading"
    workspace = ProjectWorkspaceController(host)
    workspace._apply_catalog(7, [], [], [])
    assert HaizFlowController.projectCatalogState.fget(host) == "ready"
    host.projectCatalogChanged.emit.assert_called_once()
    host.projects.set_projects.assert_called_once_with([])


def test_catalogue_error_is_not_reported_as_empty():
    host = SimpleNamespace(projectCatalogChanged=Mock())
    workspace = ProjectWorkspaceController(host)
    workspace._refresh_events.put(("error", "test"))
    workspace.drain_events()
    assert HaizFlowController.projectCatalogState.fget(host) == "error"


def test_preflight_panel_reuses_snapshot_but_real_export_forces_fresh_checks(tmp_path, monkeypatch):
    from haizflow.pipeline import sequence_compiler
    from haizflow.services import video_export
    video = SimpleNamespace(video_id="one", project_type="manual")
    document = object()
    host = SimpleNamespace(_selected_video=lambda: video,
        _manual_editor_document=SimpleNamespace(video_id="one", document_object=document, _revision=1),
        _resolve_video_file=lambda *_: "source.mp4")
    ensure = Mock(return_value=document)
    monkeypatch.setattr(editor_documents, "ensure", ensure)
    monkeypatch.setattr(video_export, "export_destination", lambda _: tmp_path / "output.mp4")
    preflight = Mock(return_value={"canExport": True, "issues": []})
    monkeypatch.setattr(sequence_compiler, "export_preflight", preflight)
    HaizFlowController.manualExportPreflight(host)
    second = HaizFlowController.manualExportPreflight(host)
    second["issues"].append("external mutation")
    assert HaizFlowController.manualExportPreflight(host)["issues"] == []
    assert preflight.call_count == 1
    ensure.assert_not_called()
    host._manual_editor_document._revision += 1
    HaizFlowController.manualExportPreflight(host)
    assert preflight.call_count == 2
    HaizFlowController.manualExportPreflight(host, True)
    assert preflight.call_count == 3 and ensure.call_count == 1


def test_caption_projection_is_detached_and_computed_once_per_document(monkeypatch):
    from haizflow.desktop.manual_editor_document_model import ManualEditorDocumentModel
    from haizflow.schemas.editor import EditorClip, EditorDocument
    app = QGuiApplication.instance() or QGuiApplication([])
    model = ManualEditorDocumentModel()
    monkeypatch.setattr(model, "_schedule_waveforms", lambda: None)
    document = EditorDocument(video_id="projection", clips=[EditorClip(
        clip_id="caption", track_id="subtitles", segment_id="one", kind="subtitle", name="Hello", duration_ms=1000)])
    resolve = Mock(wraps=editor_documents.resolved_text_style)
    monkeypatch.setattr(editor_documents, "resolved_text_style", resolve)
    try:
        model.set_document(document)
        result = model.subtitleSegments
        result[0]["text"] = "Changed externally"
        assert model.subtitleSegments[0]["text"] == "Hello"
        assert resolve.call_count == 1
        model.set_document(document.model_copy(deep=True))
        assert model.subtitleSegments[0]["text"] == "Hello"
        assert resolve.call_count == 2
    finally:
        model.close()
    assert app is not None

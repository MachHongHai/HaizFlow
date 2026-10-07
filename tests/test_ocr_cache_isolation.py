"""OCR visual edits must not overwrite independently published editor data."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from haizflow.desktop.manual_editor_document_model import ManualEditorDocumentModel
from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.schemas.editor import EditorClip, EditorDocument, EditorSequence, EditorTrack
from haizflow.schemas.video import VideoConfig
from haizflow.services import editor_documents, ocr_layers, project_store, video_store


REGION = dict(x_percent=20, y_percent=75, width_percent=60, height_percent=10)


@pytest.fixture
def video(tmp_path, monkeypatch):
    monkeypatch.setattr(project_store, "PROJECT_INDEX_PATH", str(tmp_path / "projects.json"))
    return video_store.create_video(f"ocr-isolation-{tmp_path.name}", "source.mp4",
        VideoConfig(project_type="manual", project_name="OCR isolation",
                    project_directory=str(tmp_path / "projects")))


def test_saving_editor_with_old_snapshot_preserves_newly_published_results(video):
    old = video.model_copy(deep=True)
    files = dict(video.files, segments="new-subtitles.json", voice_output="new-voice.wav")
    active = {"subtitle_document": "new-subtitle", "tts_manifest": "new-voice", "audio_mix": "new-mix"}
    video_store.update_video(video.video_id, files=files, active_artifacts=active,
                             manual_completed_stages=["translation", "subtitles", "voice"])
    document = EditorDocument(video_id=video.video_id, sequence=EditorSequence(duration_ms=5000))
    stored = editor_documents.save(old, document)
    current = video_store.get_video(video.video_id)
    assert current.files == files
    assert current.active_artifacts == active
    assert current.manual_completed_stages == ["translation", "subtitles", "voice"]
    assert current.editor_document_revision == stored.revision


@pytest.mark.parametrize("treatment", ["keep", "blur", "patch"])
def test_apply_only_changes_ocr_configuration_and_visual_cache(video, treatment):
    files = dict(video.files, segments="subtitles.json", voice_output="voice.wav")
    active = {"subtitle_document": "subs", "tts_manifest": "voice", "audio_mix": "mix"}
    current = video_store.update_video(video.video_id, files=files, active_artifacts=active,
        tts_voice="omnivoice:clone", target_language="vi",
        manual_completed_stages=["translation", "subtitles", "voice", "timeline"])
    host = SimpleNamespace(_selected_video=lambda: current, _project_type="manual",
        _processing_queue=SimpleNamespace(contains=lambda *_: False),
        subtitleSettingsChanged=Mock(), selectedVideoChanged=Mock(), manualToolStateChanged=Mock(),
        _apply_setup_to_video=Mock(side_effect=AssertionError("Must not persist other panels")),
        _record_video_settings_change=Mock(), runManualTool=Mock())
    with patch("haizflow.pipeline.manual_tools.image_region_cached", return_value=True), \
         patch("haizflow.desktop.qml_controller.manual_artifacts.deactivate") as deactivate:
        assert HaizFlowController.setManualSubtitleTreatment(host, treatment, REGION)
    result = video_store.get_video(video.video_id)
    assert result.files == files
    assert result.active_artifacts == active
    assert result.tts_voice == "omnivoice:clone"
    assert result.manual_completed_stages == current.manual_completed_stages
    assert result.original_subtitle_region_override == REGION
    assert result.remove_original_subtitles == (treatment != "keep")
    deactivate.assert_called_once_with(video.video_id, {"visual_proxy", "export"})
    host._apply_setup_to_video.assert_not_called()
    host.runManualTool.assert_not_called()


def test_experimental_layers_are_hidden_without_deleting_saved_data(video):
    document = EditorDocument(video_id=video.video_id, sequence=EditorSequence(duration_ms=5000))
    ocr_layers.ensure_primary(document)
    document.tracks.append(EditorTrack(track_id="experimental", kind="ocr", name="Lớp che 1"))
    document.clips.append(EditorClip(clip_id="experimental", track_id="experimental", kind="ocr",
        duration_ms=5000, metadata={"region": REGION, "removal_mode": "patch"}))
    editor_documents.save(video, document)
    model = ManualEditorDocumentModel()
    try:
        model.set_document(document)
        assert not any(track["kind"] == "ocr" for track in model.tracks)
        assert not any(clip["kind"] == "ocr" for clip in model.clips)
        assert [item["clip_id"] for item in model.ocrLayers] == [ocr_layers.PRIMARY_CLIP]
        assert not HaizFlowController.addOcrLayer(SimpleNamespace())
        video.remove_original_subtitles = False
        assert ocr_layers.render_region(video, REGION) is None
        assert any(clip.clip_id == "experimental" for clip in editor_documents.load(video.video_id).clips)
    finally:
        model.close()


def test_ensure_reconciles_against_current_metadata_not_the_old_snapshot(video):
    editor_documents.save(video, EditorDocument(video_id=video.video_id))
    old = video.model_copy(deep=True)
    video_store.update_video(video.video_id, active_artifacts={"tts_manifest": "just-published"})
    with patch.object(editor_documents, "_reconcile_media_assets", side_effect=lambda _video, doc: doc) as reconcile:
        editor_documents.ensure(old)
    assert reconcile.call_args.args[0].active_artifacts == {"tts_manifest": "just-published"}

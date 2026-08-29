import os
import sys
import queue
import threading
import time
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.desktop import qml_controller
from haizflow.desktop import project_import_controller
from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.desktop.project_import_controller import ProjectImportController
from haizflow.desktop.project_commands_controller import ProjectCommandsController
from haizflow.desktop.localization import QMessageBox
from haizflow.desktop.processing_lifecycle_controller import ProcessingLifecycleController
from haizflow.desktop.project_workspace_controller import ProjectWorkspaceController
from haizflow.schemas.video import VideoConfig


class _DownloadSourceModel:
    def __init__(self):
        self.items = []

    def set_items(self, items):
        self.items = [{**item, "selected": False} for item in items]

    def set_selected(self, row, selected, *, exclusive=False):
        if not 0 <= row < len(self.items):
            return False
        if exclusive and selected:
            for index, item in enumerate(self.items):
                item["selected"] = index == row
        else:
            self.items[row]["selected"] = bool(selected)
        return True

    def selected_items(self):
        return [item for item in self.items if item["selected"]]


class MultiProjectControllerTests(unittest.TestCase):
    def test_selecting_video_loads_its_own_speech_model(self):
        host = Mock()
        host._selected_video_id = None
        host._settings_owner_video_id = None
        host._project_directory = "D:/projects"
        host._processing_queue = SimpleNamespace(active_video_id=None)
        host._video_project_key.return_value = "project-a"
        host._normalized_tts_provider.side_effect = lambda _language, provider: provider
        host._normalized_voice_for_language.side_effect = lambda _language, voice, _provider: voice
        host._resolve_video_file.return_value = "D:/projects/input/video.mp4"
        host._read_video_logs.return_value = ""
        video = SimpleNamespace(
            video_id="video-turbo",
            project_name="Turbo video",
            original_filename="input.mp4",
            project_directory="D:/projects",
            project_type="single",
            source_language="auto",
            output_format="keep_ratio",
            status="pending",
            mode="A",
            target_language="vi",
            speech_recognition_model="turbo",
            tts_provider="omnivoice",
            tts_voice="omnivoice:female",
            enable_audio_separation=True,
            original_video_volume=60,
            background_music_volume=30,
            tts_volume=100,
            watermark_text="",
            remove_original_subtitles=True,
            original_subtitle_removal_mode="patch",
            subtitle_style=SimpleNamespace(),
            subtitle_layout_override=False,
            files={"thumbnail": ""},
        )

        with patch(
            "haizflow.desktop.project_workspace_controller.migrate_legacy_single_export",
            return_value=False,
        ):
            ProjectWorkspaceController(host).select_video(video)

        self.assertEqual(host._speech_recognition_model, "turbo")
        host.speechRecognitionModelChanged.emit.assert_called_once_with()

    def test_whisper_turbo_option_uses_verified_model_and_selected_gpu(self):
        host = SimpleNamespace(
            _hardware_capabilities=SimpleNamespace(cuda_available=False),
            _active_processing_device="gpu",
            _settings_processing_device="gpu",
            _whisper_turbo_model_ready=True,
            _settings_language="en",
        )

        options = HaizFlowController.speechRecognitionModelOptions.fget(host)

        self.assertTrue(options[1]["available"])

    def test_whisper_turbo_option_stays_locked_until_integrity_passes(self):
        host = SimpleNamespace(
            _hardware_capabilities=SimpleNamespace(cuda_available=True),
            _active_processing_device="gpu",
            _settings_processing_device="gpu",
            _whisper_turbo_model_ready=False,
            _settings_language="en",
        )

        options = HaizFlowController.speechRecognitionModelOptions.fget(host)

        self.assertFalse(options[1]["available"])

    def test_whisper_turbo_readiness_uses_the_integrity_verifier(self):
        with patch.object(qml_controller, "verify_whisper_turbo_model") as verifier:
            self.assertTrue(HaizFlowController._detect_whisper_turbo_model_ready())

        verifier.assert_called_once()

    def test_download_project_source_import_uses_single_replace_and_batch_copy_flows(self):
        with tempfile.TemporaryDirectory() as temporary:
            first = Path(temporary) / "first.mp4"
            second = Path(temporary) / "second.mp4"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            signal = SimpleNamespace(emit=Mock())
            host = SimpleNamespace(
                download_project_sources=_DownloadSourceModel(),
                downloadProjectSourcesChanged=signal,
                _selected_video_id="selected-video",
            )
            controller = ProjectImportController(host)
            controller.import_video = Mock(return_value=True)
            controller.import_batch_videos = Mock()
            sources = [
                {
                    "item_id": "one",
                    "project_name": "Downloads",
                    "category": "video",
                    "file_name": first.name,
                    "file_path": str(first),
                    "file_size": 5,
                },
                {
                    "item_id": "two",
                    "project_name": "Downloads",
                    "category": "channel",
                    "file_name": second.name,
                    "file_path": str(second),
                    "file_size": 6,
                },
            ]

            with patch.object(
                project_import_controller.project_store, "list_download_project_videos", return_value=sources
            ):
                controller.refresh_download_project_sources()
            controller.set_download_project_source_selected(0, True, exclusive=True)
            self.assertTrue(controller.import_selected_download_project_videos("single"))
            controller.import_video.assert_called_once_with(str(first), replace_selected=True)

            controller.set_download_project_source_selected(0, True, exclusive=False)
            controller.set_download_project_source_selected(1, True, exclusive=False)
            self.assertTrue(controller.import_selected_download_project_videos("batch"))
            controller.import_batch_videos.assert_called_once_with([str(first), str(second)])

    def test_download_project_source_single_selection_is_exclusive(self):
        model = _DownloadSourceModel()
        model.set_items(
            [
                {"item_id": "one", "selected": False},
                {"item_id": "two", "selected": False},
            ]
        )
        host = SimpleNamespace(
            download_project_sources=model,
            downloadProjectSourcesChanged=SimpleNamespace(emit=Mock()),
        )
        controller = ProjectImportController(host)

        controller.set_download_project_source_selected(0, True, exclusive=True)
        controller.set_download_project_source_selected(1, True, exclusive=True)

        self.assertEqual([item["item_id"] for item in model.selected_items()], ["two"])

    def test_covering_original_subtitles_clears_stale_manual_layout(self):
        host = SimpleNamespace(
            _remove_original_subtitles=False,
            _subtitle_layout_override=True,
            subtitleSettingsChanged=SimpleNamespace(emit=Mock()),
        )

        HaizFlowController.removeOriginalSubtitles.fset(host, True)

        self.assertTrue(host._remove_original_subtitles)
        self.assertFalse(host._subtitle_layout_override)
        host.subtitleSettingsChanged.emit.assert_called_once_with()

    def test_original_subtitle_removal_mode_rejects_unknown_values(self):
        host = SimpleNamespace(
            _original_subtitle_removal_mode="patch",
            subtitleSettingsChanged=SimpleNamespace(emit=Mock()),
        )

        HaizFlowController.originalSubtitleRemovalMode.fset(host, "unsupported")

        self.assertEqual(host._original_subtitle_removal_mode, "patch")
        host.subtitleSettingsChanged.emit.assert_not_called()

    def test_new_project_setup_resets_all_project_local_settings(self):
        changed = {
            name: SimpleNamespace(emit=Mock())
            for name in (
                "workflowModeChanged",
                "targetLanguageChanged",
                "ttsVoiceChanged",
                "ttsVoiceOptionsChanged",
                "enableAudioSeparationChanged",
                "originalVolumeChanged",
                "backgroundMusicVolumeChanged",
                "ttsVolumeChanged",
                "watermarkTextChanged",
                "backgroundMusicChanged",
            )
        }
        preview = SimpleNamespace(invalidate=Mock())
        host = SimpleNamespace(
            _workflow_mode="review",
            _target_language="en",
            _tts_voice="en-US-GuyNeural",
            _enable_audio_separation=True,
            _original_volume=15,
            _background_music_volume=75,
            _tts_volume=55,
            _watermark_text="Previous project",
            _background_music_path="old.m4a",
            _original_subtitle_removal_mode="inpaint",
            _audio_preview=preview,
            **changed,
        )
        controller = ProjectImportController(host)
        controller.cancel_background_music_link_import = Mock()

        controller._reset_new_project_setup()

        self.assertEqual(host._workflow_mode, "A")
        self.assertEqual(host._target_language, "vi")
        self.assertEqual(host._tts_provider, "omnivoice")
        self.assertEqual(host._tts_voice, "omnivoice:female")
        self.assertEqual(host._speaker_mode, "single")
        self.assertTrue(host._enable_audio_separation)
        self.assertEqual((host._original_volume, host._background_music_volume, host._tts_volume), (60, 30, 100))
        self.assertEqual(host._watermark_text, "")
        self.assertEqual(host._background_music_path, "")
        self.assertEqual(host._original_subtitle_removal_mode, "patch")
        preview.invalidate.assert_called_once_with()
        controller.cancel_background_music_link_import.assert_called_once_with()

    def test_new_batch_import_is_persisted_before_existing_cards(self):
        project_key = "batch:campaign"
        existing = SimpleNamespace(
            video_id="existing",
            project_type="batch",
            project_key=project_key,
            batch_import_order=0,
            created_at="2026-08-01T10:00:00Z",
        )
        newly_imported = SimpleNamespace(
            video_id="new",
            project_type="batch",
            project_key=project_key,
            batch_import_order=0,
            created_at="2026-08-01T11:00:00Z",
        )
        videos = {video.video_id: video for video in (existing, newly_imported)}
        host = SimpleNamespace(
            _batch_video_ids=[existing.video_id],
            _selected_project_key=project_key,
            _video_project_key=lambda video: video.project_key,
        )

        def update_video(video_id, **changes):
            video = videos[video_id]
            for key, value in changes.items():
                setattr(video, key, value)
            return video

        with (
            patch.object(project_import_controller.video_store, "list_videos", return_value=list(videos.values())),
            patch.object(project_import_controller.video_store, "update_video", side_effect=update_video),
        ):
            ProjectImportController(host)._prepend_batch_import([newly_imported.video_id])

        self.assertEqual(host._batch_video_ids, ["new", "existing"])
        self.assertLess(newly_imported.batch_import_order, existing.batch_import_order)

    def test_new_batch_import_uses_batch_baseline_not_open_video_override(self):
        custom_editor_config = VideoConfig(
            project_type="batch",
            target_language="en",
            tts_voice="en-US-JennyNeural",
            watermark_text="custom card",
            remove_original_subtitles=False,
        )
        host = SimpleNamespace(
            _project_type="batch",
            _batch_video_ids=["baseline", "custom"],
            _build_config=Mock(return_value=custom_editor_config),
            _batch_settings_values=Mock(
                return_value={
                    "workflowMode": "A",
                    "targetLanguage": "vi",
                    "ttsVoice": "vi-VN-HoaiMyNeural",
                    "enableAudioSeparation": True,
                    "originalVolume": 45,
                    "backgroundMusicVolume": 20,
                    "ttsVolume": 90,
                    "watermarkText": "batch",
                    "removeOriginalSubtitles": True,
                    "originalSubtitleRemovalMode": "patch",
                    "subtitleStyle": {"font_size": 64, "manual": True},
                    "backgroundMusicPath": "music.mp3",
                }
            ),
        )

        config = ProjectImportController(host)._config_for_project_import()

        self.assertEqual(config.target_language, "vi")
        self.assertEqual(config.tts_voice, "vi-VN-HoaiMyNeural")
        self.assertEqual(config.watermark_text, "batch")
        self.assertTrue(config.remove_original_subtitles)
        self.assertEqual(config.original_subtitle_removal_mode, "patch")
        self.assertFalse(config.subtitle_layout_override)
        self.assertEqual(config.subtitle_style.font_size, 64)
        self.assertEqual(config.background_music_path, "music.mp3")

    def test_batch_card_opens_the_selected_video_settings(self):
        batch_page = (ROOT / "src" / "haizflow" / "desktop" / "qml" / "BatchPage.qml").read_text(encoding="utf-8")
        card = (ROOT / "src" / "haizflow" / "desktop" / "qml" / "BatchVideoCard.qml").read_text(encoding="utf-8")

        self.assertIn("AppController.selectBatchVideo(index)", batch_page)
        self.assertIn("root.openVideoDetail()", batch_page)
        self.assertIn('qsTr("Chỉnh cài đặt video")', card)
        self.assertIn("required property string videoSize", card)
        self.assertIn("id: sizeLabel", card)
        self.assertIn('glyph: "\\uE76C"', card)
        self.assertNotIn('glyph: "\\uE70F"', card)
        self.assertIn("ThumbnailFallback", card)

        project_card = (ROOT / "src" / "haizflow" / "desktop" / "qml" / "ProjectCard.qml").read_text(encoding="utf-8")
        self.assertIn("required property string videoSize", project_card)
        self.assertIn("id: sizeLabel", project_card)
        self.assertIn("root.videoSize.length > 0", project_card)
        self.assertIn("acceptedButtons: Qt.RightButton", project_card)
        self.assertIn("id: projectContextMenu", project_card)
        self.assertIn('qsTr("Mở thư mục dự án")', project_card)
        self.assertIn('qsTr("Xóa dự án")', project_card)

        projects_page = (ROOT / "src" / "haizflow" / "desktop" / "qml" / "ProjectsPage.qml").read_text(encoding="utf-8")
        self.assertIn("onProjectFolderRequested", projects_page)
        self.assertIn("onDeleteRequested", projects_page)

    def test_saving_batch_video_settings_updates_only_the_selected_video(self):
        selected = SimpleNamespace(video_id="video-custom", project_type="batch")
        host = SimpleNamespace(
            _selected_video_id=selected.video_id,
            _processing_queue=SimpleNamespace(contains=Mock(return_value=False)),
            _apply_setup_to_video=Mock(),
            refreshVideos=Mock(),
            selectedVideoChanged=SimpleNamespace(emit=Mock()),
            batchChanged=SimpleNamespace(emit=Mock()),
        )
        commands = ProjectCommandsController(host)

        with (
            patch("haizflow.desktop.project_commands_controller.video_store.get_video", return_value=selected),
            patch("haizflow.desktop.project_commands_controller.video_store.log_to_video") as log_to_video,
        ):
            self.assertTrue(commands.save_selected_video_settings())

        host._apply_setup_to_video.assert_called_once_with(selected)
        log_to_video.assert_called_once_with(selected.video_id, "Per-video dubbing settings saved.")
        host.refreshVideos.assert_called_once()
        host.batchChanged.emit.assert_called_once()

    def test_auto_saving_batch_video_settings_does_not_add_a_log_entry(self):
        selected = SimpleNamespace(video_id="video-custom", project_type="batch")
        host = SimpleNamespace(
            _selected_video_id=selected.video_id,
            _processing_queue=SimpleNamespace(contains=Mock(return_value=False)),
            _apply_setup_to_video=Mock(),
            refreshVideos=Mock(),
            selectedVideoChanged=SimpleNamespace(emit=Mock()),
            batchChanged=SimpleNamespace(emit=Mock()),
        )

        with (
            patch("haizflow.desktop.project_commands_controller.video_store.get_video", return_value=selected),
            patch("haizflow.desktop.project_commands_controller.video_store.log_to_video") as log_to_video,
        ):
            self.assertTrue(ProjectCommandsController(host).persist_selected_video_settings())

        host._apply_setup_to_video.assert_called_once_with(selected)
        log_to_video.assert_not_called()

    def test_auto_saving_single_video_settings_persists_without_treating_it_as_a_batch(self):
        selected = SimpleNamespace(video_id="video-single", project_type="single")
        host = SimpleNamespace(
            _selected_video_id=selected.video_id,
            _processing_queue=SimpleNamespace(contains=Mock(return_value=False)),
            _apply_setup_to_video=Mock(),
            refreshVideos=Mock(),
            selectedVideoChanged=SimpleNamespace(emit=Mock()),
            batchChanged=SimpleNamespace(emit=Mock()),
        )

        with (
            patch("haizflow.desktop.project_commands_controller.video_store.get_video", return_value=selected),
            patch("haizflow.desktop.project_commands_controller.video_store.log_to_video") as log_to_video,
        ):
            self.assertTrue(ProjectCommandsController(host).persist_selected_video_settings())

        host._apply_setup_to_video.assert_called_once_with(selected)
        host.refreshVideos.assert_called_once()
        host.batchChanged.emit.assert_not_called()
        log_to_video.assert_not_called()

    def test_start_batch_preserves_each_video_saved_settings(self):
        first = SimpleNamespace(video_id="video-vi", status="pending", target_language="vi")
        second = SimpleNamespace(video_id="video-en", status="pending", target_language="en")
        videos = {first.video_id: first, second.video_id: second}
        host = SimpleNamespace(
            _batch_video_ids=[first.video_id, second.video_id],
            _batch_running=False,
            _batch_stop_requested=False,
            _enqueue_videos=Mock(return_value=2),
            batchChanged=SimpleNamespace(emit=Mock()),
        )
        commands = ProjectCommandsController(host)

        with (
            patch(
                "haizflow.desktop.project_commands_controller.video_store.get_video",
                side_effect=lambda video_id: videos.get(video_id),
            ),
            patch("haizflow.desktop.project_commands_controller.video_store.update_video") as update_video,
        ):
            commands.start_batch()

        host._enqueue_videos.assert_called_once_with([first.video_id, second.video_id])
        update_video.assert_not_called()
        self.assertEqual(first.target_language, "vi")
        self.assertEqual(second.target_language, "en")
        self.assertTrue(host._batch_running)

    def test_resume_batch_requeues_paused_and_new_pending_videos(self):
        paused = SimpleNamespace(video_id="video-paused", status="paused")
        pending = SimpleNamespace(video_id="video-pending", status="pending")
        done = SimpleNamespace(video_id="video-done", status="done")
        videos = {video.video_id: video for video in (paused, pending, done)}
        host = SimpleNamespace(
            _batch_video_ids=list(videos),
            _batch_running=False,
            _batch_stop_requested=True,
            _processing_queue=SimpleNamespace(contains=Mock(return_value=False)),
            _enqueue_videos=Mock(return_value=2),
            batchChanged=SimpleNamespace(emit=Mock()),
        )

        with (
            patch(
                "haizflow.desktop.project_commands_controller.video_store.get_video",
                side_effect=lambda video_id: videos.get(video_id),
            ),
            patch("haizflow.desktop.project_commands_controller.video_store.log_to_video"),
        ):
            ProjectCommandsController(host).resume_batch()

        host._enqueue_videos.assert_called_once_with([paused.video_id, pending.video_id])
        self.assertTrue(host._batch_running)
        self.assertFalse(host._batch_stop_requested)

    def test_paused_video_clears_process_control_flags_only_when_requeued(self):
        video = SimpleNamespace(video_id="paused-video", status="paused")
        host = SimpleNamespace(
            _model_setup_state="ready",
            _processing_queue=SimpleNamespace(
                contains=Mock(return_value=False),
                enqueue=Mock(return_value=True),
                pending_ids=Mock(return_value=[video.video_id]),
            ),
            processingChanged=SimpleNamespace(emit=Mock()),
            selectedVideoChanged=SimpleNamespace(emit=Mock()),
            _log_queue=queue.Queue(),
        )
        with (
            patch(
                "haizflow.desktop.processing_lifecycle_controller.video_store.get_video",
                return_value=video,
            ),
            patch("haizflow.desktop.processing_lifecycle_controller.video_store.update_video"),
            patch("haizflow.desktop.processing_lifecycle_controller.video_store.log_to_video"),
            patch("haizflow.desktop.processing_lifecycle_controller.prepare_video_resume") as prepare_resume,
        ):
            self.assertTrue(ProcessingLifecycleController(host).enqueue_video(video.video_id))

        prepare_resume.assert_called_once_with(video.video_id)

    def test_stop_batch_pauses_active_and_waiting_videos_for_resume(self):
        active = SimpleNamespace(video_id="active", status="processing", step="translating", resume_step="")
        waiting = SimpleNamespace(video_id="waiting", status="pending", step="queued", resume_step="")
        videos = {active.video_id: active, waiting.video_id: waiting}
        host = SimpleNamespace(
            isBatchRunning=True,
            _batch_video_ids=list(videos),
            _batch_stop_requested=False,
            _processing_queue=SimpleNamespace(
                detach_pending=Mock(return_value=(active.video_id, [waiting.video_id])),
            ),
            _refresh_batch_model=Mock(),
            batchChanged=SimpleNamespace(emit=Mock()),
        )

        with (
            patch(
                "haizflow.desktop.project_commands_controller.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch(
                "haizflow.desktop.project_commands_controller.video_store.get_video",
                side_effect=lambda video_id: videos.get(video_id),
            ),
            patch("haizflow.desktop.project_commands_controller.video_store.update_video") as update_video,
            patch("haizflow.desktop.project_commands_controller.video_store.log_to_video"),
            patch("haizflow.desktop.project_commands_controller.pause_video") as pause_process,
        ):
            ProjectCommandsController(host).stop_batch()

        pause_process.assert_called_once_with(active.video_id)
        self.assertEqual(update_video.call_args_list[0].kwargs["status"], "paused")
        self.assertEqual(update_video.call_args_list[1].kwargs["status"], "paused")
        self.assertEqual(update_video.call_args_list[1].kwargs["resume_step"], "translating")
        self.assertTrue(host._batch_stop_requested)

    def test_batch_setting_overrides_identify_each_changed_video_and_field(self):
        common = dict(
            mode="A",
            target_language="vi",
            tts_voice="vi-VN-HoaiMyNeural",
            enable_audio_separation=False,
            original_video_volume=60,
            background_music_volume=30,
            tts_volume=100,
            watermark_text="",
        )
        first = SimpleNamespace(video_id="video-1", original_filename="first.mp4", **common)
        second = SimpleNamespace(video_id="video-2", original_filename="second.mp4", **common)
        custom = SimpleNamespace(
            video_id="video-3",
            original_filename="custom.mp4",
            **{**common, "target_language": "en", "tts_voice": "en-US-GuyNeural", "watermark_text": "HaizFlow"},
        )
        videos = {video.video_id: video for video in (first, second, custom)}
        host = SimpleNamespace(_batch_video_ids=list(videos))

        with patch(
            "haizflow.desktop.project_commands_controller.video_store.get_video",
            side_effect=lambda video_id: videos.get(video_id),
        ):
            overrides = ProjectCommandsController(host).batch_setting_overrides()

        self.assertEqual(
            overrides,
            [
                {
                    "videoId": "video-3",
                    "fileName": "custom.mp4",
                    "differences": ["targetLanguage", "voice", "watermark"],
                }
            ],
        )

    def test_batch_settings_apply_one_background_music_source_to_every_video(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            music = Path(temp_dir) / "music.mp3"
            music.write_bytes(b"music")
            videos = {
                "video-1": SimpleNamespace(video_id="video-1", files={}),
                "video-2": SimpleNamespace(video_id="video-2", files={}),
            }
            host = SimpleNamespace(
                _batch_video_ids=list(videos),
                _processing_queue=SimpleNamespace(contains=Mock(return_value=False)),
                _normalized_tts_provider=Mock(return_value="auto"),
                _normalized_voice_for_language=Mock(return_value="vi-VN-HoaiMyNeural"),
                refreshVideos=Mock(),
                batchChanged=SimpleNamespace(emit=Mock()),
            )
            with (
                patch(
                    "haizflow.desktop.project_commands_controller.video_store.get_video",
                    side_effect=lambda video_id: videos.get(video_id),
                ),
                patch("haizflow.desktop.project_commands_controller.video_store.update_video"),
                patch("haizflow.desktop.project_commands_controller.set_desktop_background_music") as set_music,
            ):
                applied = ProjectCommandsController(host).apply_batch_settings(
                    "A", "vi", "auto", "", False, 60, 25, 100, "", str(music)
                )

        self.assertTrue(applied)
        self.assertEqual(set_music.call_count, 2)
        self.assertEqual([call.args[1] for call in set_music.call_args_list], [str(music), str(music)])

    def test_batch_page_exposes_settings_resume_and_bottom_progress(self):
        batch_page = (ROOT / "src" / "haizflow" / "desktop" / "qml" / "BatchPage.qml").read_text(encoding="utf-8")
        settings = (ROOT / "src" / "haizflow" / "desktop" / "qml" / "BatchSettingsDialog.qml").read_text(
            encoding="utf-8"
        )
        shared_settings = (
            ROOT / "src" / "haizflow" / "desktop" / "qml" / "ProcessingSettingsForm.qml"
        ).read_text(encoding="utf-8")

        self.assertIn('text: qsTr("Cài đặt hàng loạt")', batch_page)
        self.assertNotIn("setupVisible: true", batch_page)
        self.assertIn("AppController.batchPausedCount > 0", batch_page)
        self.assertIn("AppController.resumeBatch()", batch_page)
        self.assertIn("id: importCard", batch_page)
        self.assertIn("id: batchProgressPanel", batch_page)
        self.assertIn("Layout.maximumWidth: 640", batch_page)
        self.assertLess(batch_page.index("id: importCard"), batch_page.index('text: qsTr("Cài đặt hàng loạt")'))
        self.assertLess(batch_page.index("id: importCard"), batch_page.index('qsTr("Hàng đợi xử lý")'))
        self.assertGreater(batch_page.index("id: batchProgressPanel"), batch_page.index("id: queueList"))
        self.assertIn('qsTr("Adding %1 / %2…")', batch_page)
        self.assertIn("readonly property real cardWidth: Math.min(220", batch_page)
        self.assertIn("readonly property real cardHeight: Math.round(cardWidth * 0.56 + 64)", batch_page)
        self.assertIn("AppController.chooseBatchBackgroundMusic()", settings)
        self.assertIn('batchBackgroundMusicLinkDialogLoader.invoke("open", [])', settings)
        self.assertIn("ProcessingSettingsForm", settings)
        self.assertIn('text: qsTr("Chỉnh phụ đề")', shared_settings)
        self.assertIn("enabled: root.editable && root.hasSource", shared_settings)
        self.assertIn("BatchAudioMixDialog", settings)
        self.assertIn('batchAudioMixDialogLoader.invoke("open", [])', settings)
        self.assertNotIn("AppSlider {", settings)
        self.assertIn("onClosed: saveDraft()", settings)
        self.assertNotIn('I18n.t("Apply to all videos")', settings)

        batch_audio_dialog = (ROOT / "src" / "haizflow" / "desktop" / "qml" / "BatchAudioMixDialog.qml").read_text(
            encoding="utf-8"
        )
        self.assertIn("AudioLevelControl", batch_audio_dialog)
        self.assertIn("root.audioSeparationEnabled", batch_audio_dialog)
        self.assertIn("backgroundMusicPath.length > 0", batch_audio_dialog)
        self.assertIn("AppController.previewBatchAudioMix(", batch_audio_dialog)
        self.assertIn("function pausePreview()", batch_audio_dialog)
        self.assertIn("onClosed: pausePreview()", batch_audio_dialog)
        self.assertIn('root.visible && AppController.audioPreviewState === "ready"', batch_audio_dialog)
        self.assertIn("readonly property bool previewPlaying", batch_audio_dialog)
        self.assertIn('iconName: root.previewPlaying ? "pause" : "play"', batch_audio_dialog)

        dubbing_setup = (ROOT / "src" / "haizflow" / "desktop" / "qml" / "DubbingSetupPanel.qml").read_text(
            encoding="utf-8"
        )
        self.assertIn("videoSettingsSaveTimer.restart()", dubbing_setup)
        self.assertIn("AppController.persistVideoSettingsFor(root.pendingSettingsVideoId)", dubbing_setup)
        self.assertIn("pendingSettingsVideoId = AppController.selectedVideoId", dubbing_setup)
        self.assertNotIn("AppController.saveSelectedVideoSettings()", dubbing_setup)

    def test_batch_audio_preview_uses_draft_without_applying_settings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.mp4"
            source.write_bytes(b"video")
            video = SimpleNamespace(video_id="batch-video", files={"video_input": str(source)})
            controller = SimpleNamespace(
                _batch_video_ids=[video.video_id],
                _audio_preview=Mock(start=Mock(return_value=True)),
                _status_message="",
                statusMessageChanged=SimpleNamespace(emit=Mock()),
            )
            with patch.object(qml_controller.video_store, "get_video", return_value=video):
                result = HaizFlowController.previewBatchAudioMix(
                    controller, "vi", "edge", "vi-VN-HoaiMyNeural", True, 40, 25, 90, "music.mp3"
                )

        self.assertTrue(result)
        controller._audio_preview.start.assert_called_once_with(
            video_id="batch-video",
            enable_audio_separation=True,
            background_music_path="music.mp3",
            original_volume=40,
            background_music_volume=25,
            tts_volume=90,
            voice="vi-VN-HoaiMyNeural",
            provider="edge",
            target_language="vi",
        )

    def test_project_import_shutdown_wait_is_bounded_and_reports_live_workers(self):
        importer = ProjectImportController(SimpleNamespace())
        release = threading.Event()
        worker = threading.Thread(target=release.wait, daemon=True)
        importer._task_threads[1] = worker
        worker.start()
        try:
            self.assertFalse(importer.shutdown(timeout_seconds=0.001))
            release.set()
            self.assertTrue(importer.shutdown(timeout_seconds=1.0))
        finally:
            release.set()
            worker.join(timeout=1.0)

    def test_media_picker_starts_in_the_native_windows_media_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_directory = Path(temp_dir) / "project"
            project_directory.mkdir()
            host = SimpleNamespace(
                _project_directory=str(project_directory),
                videoPath="",
                _selected_video_id=None,
            )
            importer = ProjectImportController(host)

            with patch.object(
                project_import_controller.QFileDialog, "getOpenFileName", return_value=("", "")
            ) as choose_video:
                importer.browse_video()

        self.assertEqual(
            choose_video.call_args.args[2],
            project_import_controller.native_media_dialog_directory(),
        )

    def test_batch_settings_draft_applies_without_mutating_editor_state(self):
        video = SimpleNamespace(video_id="batch-video")
        controller = SimpleNamespace(
            _batch_video_ids=[video.video_id],
            _processing_queue=SimpleNamespace(contains=Mock(return_value=False)),
            _voice_options_for_language=lambda language, provider="edge": {
                "vi": [{"voice": "vi-VN-HoaiMyNeural"}],
                "en": [{"voice": "en-US-JennyNeural"}],
            }[language],
            refreshVideos=Mock(),
            batchChanged=SimpleNamespace(emit=Mock()),
        )
        controller._normalized_tts_provider = HaizFlowController._normalized_tts_provider
        controller._normalized_voice_for_language = HaizFlowController._normalized_voice_for_language.__get__(
            controller
        )
        controller._apply_batch_settings = HaizFlowController._apply_batch_settings.__get__(controller)

        with (
            patch.object(qml_controller.video_store, "get_video", return_value=video),
            patch.object(qml_controller.video_store, "update_video") as update_video,
        ):
            applied = HaizFlowController.applyBatchSettingsDraft(
                controller,
                "review",
                "en",
                "edge",
                "vi-VN-HoaiMyNeural",
                True,
                35,
                30,
                100,
                "HaizFlow",
            )

        self.assertTrue(applied)
        update_video.assert_called_once_with(
            video.video_id,
            mode="A",
            source_language="auto",
            target_language="en",
            speech_recognition_model="small",
            tts_provider="edge",
            tts_voice="en-US-JennyNeural",
            speaker_mode="single",
            enable_audio_separation=True,
            original_video_volume=35,
            background_music_volume=30,
            tts_volume=100,
            watermark_text="HaizFlow",
        )
        self.assertFalse(hasattr(controller, "_target_language"))
        controller.refreshVideos.assert_called_once()
        controller.batchChanged.emit.assert_called_once()

    def test_batch_settings_dialog_keeps_edits_local_until_apply(self):
        dialog_qml = (ROOT / "src" / "haizflow" / "desktop" / "qml" / "BatchSettingsDialog.qml").read_text(
            encoding="utf-8"
        )
        self.assertIn("function loadDraft()", dialog_qml)
        self.assertIn("AppController.batchSettings()", dialog_qml)
        self.assertIn("AppController.applyBatchSettingsDraft(", dialog_qml)
        self.assertIn('draftSpeakerMode: "single"', dialog_qml)
        self.assertIn("AppController.batchSettingOverrides()", dialog_qml)
        self.assertIn("onBatchChanged()", dialog_qml)
        self.assertNotIn("AppController.workflowMode =", dialog_qml)
        self.assertNotIn("AppController.targetLanguage =", dialog_qml)
        self.assertNotIn("AppController.ttsVoice =", dialog_qml)
        self.assertNotIn("AppController.enableAudioSeparation =", dialog_qml)
        self.assertNotIn("AppController.originalVolume =", dialog_qml)

    def test_metadata_poll_skips_refresh_when_no_video_metadata_changed(self):
        controller = SimpleNamespace(
            _last_video_metadata_revision=7,
            refreshVideos=Mock(),
            batchChanged=SimpleNamespace(emit=Mock()),
        )
        with patch.object(qml_controller.video_store, "metadata_revision", return_value=7):
            HaizFlowController.poll_videos(controller)

        controller.refreshVideos.assert_not_called()
        controller.batchChanged.emit.assert_not_called()

        with patch.object(qml_controller.video_store, "metadata_revision", return_value=8):
            HaizFlowController.poll_videos(controller)

        controller.refreshVideos.assert_called_once()
        controller.batchChanged.emit.assert_called_once()
        self.assertEqual(controller._last_video_metadata_revision, 8)

    def test_metadata_poll_patches_changed_rows_without_catalog_refresh(self):
        controller = SimpleNamespace(
            _last_video_metadata_revision=7,
            _apply_video_metadata_changes=Mock(return_value=True),
            refreshVideos=Mock(),
            batchChanged=SimpleNamespace(emit=Mock()),
        )
        with (
            patch.object(qml_controller.video_store, "metadata_revision", return_value=8),
            patch.object(qml_controller.video_store, "metadata_changes_since", return_value=(8, {"video-1"})),
        ):
            HaizFlowController.poll_videos(controller)

        controller._apply_video_metadata_changes.assert_called_once_with({"video-1"})
        controller.refreshVideos.assert_not_called()
        controller.batchChanged.emit.assert_called_once()
        self.assertEqual(controller._last_video_metadata_revision, 8)

    def test_hardware_probe_is_inactive_until_settings_are_opened(self):
        controller = SimpleNamespace(_hardware_telemetry_active=False)
        with patch.object(qml_controller, "detect_hardware_capabilities") as detect:
            HaizFlowController._refresh_live_hardware(controller)
        detect.assert_not_called()

    def test_failed_thumbnail_is_not_requeued_until_its_source_changes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "clip.mp4"
            source.write_bytes(b"first")
            video = SimpleNamespace(video_id="thumbnail-video", files={"video_input": str(source)})
            controller = SimpleNamespace(
                _thumbnail_retry_failures={},
                _thumbnail_retry_lock=threading.Lock(),
                _resolve_video_file=Mock(return_value=str(source)),
                _thumbnail_retry_signature=HaizFlowController._thumbnail_retry_signature,
                _THUMBNAIL_RETRY_MAX_ATTEMPTS=HaizFlowController._THUMBNAIL_RETRY_MAX_ATTEMPTS,
                _THUMBNAIL_RETRY_INITIAL_DELAY_SECONDS=HaizFlowController._THUMBNAIL_RETRY_INITIAL_DELAY_SECONDS,
            )

            self.assertEqual(HaizFlowController._missing_thumbnail_ids(controller, [video]), ["thumbnail-video"])
            signature = HaizFlowController._thumbnail_retry_signature(str(source))
            HaizFlowController._record_thumbnail_failure(controller, video.video_id, signature)
            self.assertEqual(HaizFlowController._missing_thumbnail_ids(controller, [video]), [])

            source.write_bytes(b"changed source")
            os.utime(source, None)
            self.assertEqual(HaizFlowController._missing_thumbnail_ids(controller, [video]), ["thumbnail-video"])

    def test_close_confirmation_is_only_required_for_background_work(self):
        idle_controller = SimpleNamespace(
            _processing_queue=SimpleNamespace(has_work=False),
            _url_importer=SimpleNamespace(busy=False),
            _channel_importer=SimpleNamespace(busy=False),
            _close_confirmed=False,
        )
        self.assertTrue(HaizFlowController._confirm_application_close(idle_controller))

        busy_controller = SimpleNamespace(
            _processing_queue=SimpleNamespace(has_work=True),
            _url_importer=SimpleNamespace(busy=False),
            _channel_importer=SimpleNamespace(busy=False),
            _close_confirmed=False,
        )
        with patch.object(
            qml_controller.QMessageBox,
            "question",
            return_value=qml_controller.QMessageBox.StandardButton.Cancel,
        ):
            self.assertFalse(HaizFlowController._confirm_application_close(busy_controller))
        self.assertFalse(busy_controller._close_confirmed)

    def test_shutdown_pauses_active_video_and_closes_the_queue(self):
        active = SimpleNamespace(
            video_id="active-video",
            status="processing",
            step="rendering",
            resume_step="",
        )
        waiting = SimpleNamespace(video_id="waiting-video", status="pending")
        processing_queue = SimpleNamespace(
            active_video_id=active.video_id,
            pending_ids=Mock(return_value=[waiting.video_id]),
            shutdown=Mock(return_value=True),
        )
        controller = SimpleNamespace(
            _shutdown_started=False,
            _initial_model_warmup_done=threading.Event(),
            _processing_queue=processing_queue,
            _url_importer=SimpleNamespace(shutdown=Mock(return_value=True)),
            _channel_importer=SimpleNamespace(shutdown=Mock(return_value=True)),
            _dimension_probe=SimpleNamespace(shutdown=Mock()),
            _warmup_thread=None,
            _on_video_log=Mock(),
        )

        with (
            patch.object(qml_controller, "unsubscribe_log") as unsubscribe,
            patch.object(qml_controller, "pause_video") as pause,
            patch.object(qml_controller, "shutdown_hymt2_worker") as shutdown_translation,
            patch.object(
                qml_controller.video_store,
                "get_video",
                side_effect=lambda video_id: active if video_id == active.video_id else waiting,
            ),
            patch.object(qml_controller.video_store, "update_video") as update_video,
            patch.object(qml_controller.video_store, "log_to_video"),
            patch("haizflow.pipeline.transcribe.release_warm_whisperx_model") as release_whisper,
        ):
            HaizFlowController.shutdown(controller)
            HaizFlowController.shutdown(controller)

        self.assertTrue(controller._shutdown_started)
        self.assertTrue(controller._initial_model_warmup_done.is_set())
        unsubscribe.assert_called_once_with(controller._on_video_log)
        pause.assert_called_once_with(active.video_id)
        processing_queue.shutdown.assert_called_once_with(timeout_seconds=10.0)
        controller._dimension_probe.shutdown.assert_called_once_with()
        shutdown_translation.assert_called_once_with(permanent=True)
        release_whisper.assert_called_once()
        update_video.assert_any_call(
            active.video_id,
            status="paused",
            error=None,
            step="paused",
            resume_step="rendering",
            step_detail="Paused during application exit (rendering)",
            estimated_remaining_seconds=None,
        )
        update_video.assert_any_call(
            waiting.video_id,
            step="queued",
            step_detail="Waiting to be started after the application exited",
        )

    def test_target_language_replaces_an_incompatible_saved_voice(self):
        controller = SimpleNamespace(
            _target_language="vi",
            _tts_provider="edge",
            _tts_voice="vi-VN-NamMinhNeural",
            _voice_options_for_language=lambda language: {
                "vi": [{"voice": "vi-VN-HoaiMyNeural"}],
                "en": [{"voice": "en-US-JennyNeural"}, {"voice": "en-US-GuyNeural"}],
            }[language],
            targetLanguageChanged=SimpleNamespace(emit=Mock()),
            languageOptionsChanged=SimpleNamespace(emit=Mock()),
            ttsVoiceChanged=SimpleNamespace(emit=Mock()),
            ttsVoiceOptionsChanged=SimpleNamespace(emit=Mock()),
            ttsProviderChanged=SimpleNamespace(emit=Mock()),
            ttsProviderOptionsChanged=SimpleNamespace(emit=Mock()),
        )
        controller._normalized_voice_for_language = HaizFlowController._normalized_voice_for_language.__get__(
            controller
        )

        HaizFlowController.targetLanguage.fset(controller, "en")

        self.assertEqual(controller._target_language, "en")
        self.assertEqual(controller._tts_voice, "en-US-JennyNeural")
        controller.targetLanguageChanged.emit.assert_called_once()
        controller.ttsVoiceChanged.emit.assert_called_once()
        controller.ttsVoiceOptionsChanged.emit.assert_called_once()

    def test_omnivoice_remains_available_when_target_language_changes(self):
        preview = SimpleNamespace(invalidate=Mock())
        controller = SimpleNamespace(
            _target_language="vi",
            _tts_provider="omnivoice",
            _tts_voice="omnivoice:female",
            _audio_preview=preview,
            _voice_options_for_language=lambda language, provider="omnivoice": [
                {"voice": "omnivoice:female"},
                {"voice": "omnivoice:male"},
            ],
            targetLanguageChanged=SimpleNamespace(emit=Mock()),
            languageOptionsChanged=SimpleNamespace(emit=Mock()),
            ttsProviderChanged=SimpleNamespace(emit=Mock()),
            ttsProviderOptionsChanged=SimpleNamespace(emit=Mock()),
            ttsVoiceChanged=SimpleNamespace(emit=Mock()),
            ttsVoiceOptionsChanged=SimpleNamespace(emit=Mock()),
        )
        controller._normalized_voice_for_language = HaizFlowController._normalized_voice_for_language.__get__(
            controller
        )

        HaizFlowController.targetLanguage.fset(controller, "ja")

        self.assertEqual(controller._tts_provider, "omnivoice")
        self.assertEqual(controller._tts_voice, "omnivoice:female")
        preview.invalidate.assert_called_once_with()

    def test_voice_setter_rejects_a_voice_from_another_language(self):
        controller = SimpleNamespace(
            _target_language="en",
            _tts_provider="edge",
            _tts_voice="en-US-GuyNeural",
            _voice_options_for_language=lambda language: [
                {"voice": "en-US-JennyNeural"},
                {"voice": "en-US-GuyNeural"},
            ],
            ttsVoiceChanged=SimpleNamespace(emit=Mock()),
            ttsVoiceOptionsChanged=SimpleNamespace(emit=Mock()),
        )
        controller._normalized_voice_for_language = HaizFlowController._normalized_voice_for_language.__get__(
            controller
        )

        HaizFlowController.ttsVoice.fset(controller, "vi-VN-NamMinhNeural")

        self.assertEqual(controller._tts_voice, "en-US-JennyNeural")
        controller.ttsVoiceChanged.emit.assert_called_once()
        controller.ttsVoiceOptionsChanged.emit.assert_called_once()

    def test_tts_engine_change_invalidates_the_rendered_audio_preview(self):
        preview = SimpleNamespace(invalidate=Mock())
        controller = SimpleNamespace(
            _target_language="vi",
            _tts_provider="omnivoice",
            _tts_voice="omnivoice:female",
            _audio_preview=preview,
            _voice_options_for_language=lambda language, provider="omnivoice": (
                [{"voice": "omnivoice:female"}] if provider == "omnivoice" else [{"voice": "vi-VN-HoaiMyNeural"}]
            ),
            ttsProviderChanged=SimpleNamespace(emit=Mock()),
            ttsProviderOptionsChanged=SimpleNamespace(emit=Mock()),
            ttsVoiceChanged=SimpleNamespace(emit=Mock()),
            ttsVoiceOptionsChanged=SimpleNamespace(emit=Mock()),
        )
        controller._normalized_tts_provider = HaizFlowController._normalized_tts_provider
        controller._normalized_voice_for_language = HaizFlowController._normalized_voice_for_language.__get__(
            controller
        )

        HaizFlowController.ttsProvider.fset(controller, "edge")

        self.assertEqual(controller._tts_provider, "edge")
        self.assertEqual(controller._tts_voice, "vi-VN-HoaiMyNeural")
        preview.invalidate.assert_called_once()

    def test_pipeline_waits_for_startup_warmup_without_blocking_the_ui_thread(self):
        warmup_done = threading.Event()
        pipeline_started = threading.Event()
        selected_video = SimpleNamespace(status="pending")
        controller = SimpleNamespace(
            _deleted_video_ids=set(),
            _initial_model_warmup_done=warmup_done,
            _model_runtime_lock=threading.Lock(),
        )

        with (
            patch.object(qml_controller.video_store, "get_video", return_value=selected_video),
            patch.object(qml_controller.video_store, "log_to_video"),
            patch("haizflow.pipeline.process_video.process_video_sync") as process_video,
        ):
            process_video.side_effect = lambda _video_id: pipeline_started.set()
            worker = threading.Thread(
                target=HaizFlowController._execute_pipeline,
                args=(controller, "project-a-video"),
            )
            worker.start()
            time.sleep(0.03)
            self.assertTrue(worker.is_alive())
            process_video.assert_not_called()

            warmup_done.set()
            self.assertTrue(pipeline_started.wait(5), "Pipeline did not resume after model warm-up")
            worker.join(1)

        self.assertFalse(worker.is_alive())
        process_video.assert_called_once_with("project-a-video")

    def test_second_process_click_does_not_duplicate_an_already_queued_video(self):
        selected_video = SimpleNamespace(video_id="project-b-video", status="pending")
        controller = SimpleNamespace(
            _video_path="managed.mp4",
            _project_name="Project B",
            _project_directory="D:/Projects",
            _selected_video_id=selected_video.video_id,
            _processing_queue=SimpleNamespace(contains=Mock(return_value=True)),
            _status_message="",
            statusMessageChanged=SimpleNamespace(emit=Mock()),
        )

        with (
            patch.object(qml_controller.video_store, "get_video", return_value=selected_video),
            patch.object(qml_controller, "create_desktop_video") as create_video,
        ):
            started = HaizFlowController.startProjectVideo(controller)

        self.assertFalse(started)
        create_video.assert_not_called()
        self.assertIn("already", controller._status_message)

    def test_new_project_setup_is_saved_before_it_enters_the_shared_queue(self):
        selected_video = SimpleNamespace(video_id="project-b-video", status="pending")
        calls = []
        controller = SimpleNamespace(
            _video_path="managed.mp4",
            _project_name="Project B",
            _project_directory="D:/Projects",
            _selected_video_id=selected_video.video_id,
            _processing_queue=SimpleNamespace(contains=Mock(return_value=False)),
            _apply_setup_to_video=lambda video, review_approved: calls.append(
                ("setup", video.video_id, review_approved)
            ),
            _enqueue_video=lambda video_id: calls.append(("enqueue", video_id)),
            selectedVideoChanged=SimpleNamespace(emit=Mock()),
            refreshVideos=Mock(),
        )

        with (
            patch.object(qml_controller.video_store, "get_video", return_value=selected_video),
            patch.object(qml_controller.video_store, "log_to_video"),
        ):
            started = HaizFlowController.startProjectVideo(controller)

        self.assertTrue(started)
        self.assertEqual(
            calls,
            [("setup", "project-b-video", False), ("enqueue", "project-b-video")],
        )

    def test_delayed_log_line_cannot_leak_into_another_selected_project(self):
        controller = SimpleNamespace(
            _selected_video_id="project-b-video",
            _logs="Project B log",
            _log_queue=queue.Queue(),
            logsChanged=SimpleNamespace(emit=Mock()),
        )
        controller._log_queue.put(("video_log", "project-a-video", "Project A line"))

        HaizFlowController._drain_log_queue(controller)

        self.assertEqual(controller._logs, "Project B log")
        controller.logsChanged.emit.assert_not_called()

    def test_async_link_import_keeps_the_project_that_started_the_download(self):
        controller = SimpleNamespace(
            _selected_video_id=None,
            _selected_project_key="single:d:/projects:project-c",
            _batch_video_ids=[],
            _create_video_thumbnail_path=Mock(return_value=""),
            _video_thumbnail_path=Mock(return_value="thumbnail.jpg"),
            _select_video=Mock(),
            _refresh_batch_model=Mock(),
            batchChanged=SimpleNamespace(emit=Mock()),
            refreshVideos=Mock(),
        )
        target = {
            "project_key": "single:d:/projects:project-b",
            "project_name": "Project B",
            "project_directory": "D:/Projects",
            "project_type": "single",
            "selected_video_id": None,
            "config": VideoConfig(project_name="Project B", project_directory="D:/Projects"),
        }
        created_video = SimpleNamespace(video_id="video-b", files={"video_input": "managed.mp4"})

        with (
            patch.object(qml_controller.project_store, "list_projects", return_value=[{"key": target["project_key"]}]),
            patch.object(qml_controller, "create_desktop_video", return_value=created_video) as create_video,
        ):
            imported = HaizFlowController._import_downloaded_video(
                controller,
                "downloaded.mp4",
                "single",
                target,
            )

        self.assertTrue(imported)
        create_video.assert_called_once_with(
            "downloaded.mp4",
            target["config"],
            project_name="Project B",
            project_directory="D:/Projects",
            project_key_value=target["project_key"],
        )
        controller._select_video.assert_not_called()
        controller.refreshVideos.assert_called_once()

    def test_async_link_import_does_not_recreate_a_deleted_project(self):
        controller = SimpleNamespace(
            _selected_video_id=None,
            _selected_project_key="",
        )
        target = {
            "project_key": "single:d:/projects:deleted",
            "project_name": "Deleted",
            "project_directory": "D:/Projects",
            "selected_video_id": None,
            "config": VideoConfig(project_name="Deleted", project_directory="D:/Projects"),
        }

        with (
            patch.object(qml_controller.project_store, "list_projects", return_value=[]),
            patch.object(qml_controller.QMessageBox, "warning"),
            patch.object(qml_controller, "create_desktop_video") as create_video,
        ):
            imported = HaizFlowController._import_downloaded_video(
                controller,
                "downloaded.mp4",
                "single",
                target,
            )

        self.assertFalse(imported)
        create_video.assert_not_called()

    def test_channel_download_is_added_to_its_batch_without_starting_pipeline(self):
        project_key = "batch:d:/projects:campaign"
        target = {
            "project_key": project_key,
            "project_name": "Campaign",
            "project_directory": "D:/Projects",
            "project_type": "batch",
            "config": VideoConfig(
                project_name="Campaign",
                project_directory="D:/Projects",
                project_type="batch",
            ),
            "channel_url": "https://www.youtube.com/@creator/videos",
            "channel_name": "Creator",
        }
        created_video = SimpleNamespace(video_id="channel-video", files={"video_input": "managed.mp4"})
        importer = SimpleNamespace(complete_video=Mock())
        controller = SimpleNamespace(
            _channel_import_targets={"session": target},
            _channel_importer=importer,
            _selected_project_key=project_key,
            _project_type="batch",
            _batch_video_ids=[],
            _create_video_thumbnail_path=Mock(return_value=""),
            _video_thumbnail_path=Mock(return_value="thumbnail.jpg"),
            _refresh_batch_model=Mock(),
            batchChanged=SimpleNamespace(emit=Mock()),
            refreshVideos=Mock(),
        )
        candidate = {
            "remote_video_id": "abc",
            "source_url": "https://www.youtube.com/watch?v=abc",
            "platform": "YouTube",
            "uploader": "Creator",
        }

        with (
            patch.object(qml_controller.project_store, "list_projects", return_value=[{"key": project_key}]),
            patch.object(qml_controller, "create_desktop_video", return_value=created_video) as create_video,
        ):
            HaizFlowController._handle_channel_video_ready(
                controller,
                "downloaded.mp4",
                "workspace",
                candidate,
                project_key,
                "session",
            )

        self.assertEqual(controller._batch_video_ids, ["channel-video"])
        self.assertEqual(create_video.call_args.kwargs["project_name"], "Campaign")
        self.assertEqual(create_video.call_args.kwargs["project_directory"], "D:/Projects")
        self.assertTrue(create_video.call_args.kwargs["move_input"])
        media_source = create_video.call_args.kwargs["media_source"]
        self.assertEqual(media_source["type"], "channel")
        self.assertEqual(media_source["remote_video_id"], "abc")
        self.assertEqual(media_source["channel_url"], target["channel_url"])
        importer.complete_video.assert_called_once_with("session", "abc", True)
        controller.refreshVideos.assert_called_once()

    def test_translation_review_draft_is_saved_atomically_and_restored(self):
        with tempfile.TemporaryDirectory() as temporary:
            video = SimpleNamespace(
                video_id="video-1",
                status="awaiting_review",
                files={"transcript_json": str(Path(temporary) / "translated.json")},
            )
            host = SimpleNamespace(
                _selected_video_id="video-1",
                _status_message="",
                statusMessageChanged=SimpleNamespace(emit=Mock()),
                _selected_video=lambda: video,
            )

            def update_video(_video_id, **changes):
                for key, value in changes.items():
                    setattr(video, key, value)
                return video

            payload = '[{"start": 0.0, "end": 1.5, "text": "Draft translation"}]'
            with (
                patch.object(qml_controller.video_store, "get_video", return_value=video),
                patch.object(qml_controller.video_store, "get_video_dir", return_value=temporary),
                patch.object(qml_controller.video_store, "update_video", side_effect=update_video),
                patch.object(qml_controller.video_store, "log_to_video"),
            ):
                self.assertTrue(ProjectCommandsController(host).save_translation_review_draft(payload))
                restored = HaizFlowController.reviewSegments.fget(host)

            draft_path = Path(video.files["translation_review_draft"])
            self.assertTrue(draft_path.is_file())
            self.assertEqual(restored[0]["text"], "Draft translation")
            self.assertFalse(any(path.name.endswith(".tmp") for path in Path(temporary).iterdir()))

    def test_translation_editor_preview_uses_persisted_visual_and_audio_layers(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            background = workspace / "no_vocals.wav"
            music = workspace / "music.mp3"
            background.write_bytes(b"background")
            music.write_bytes(b"music")
            region_path = workspace / "temp" / "original_subtitle_region.json"
            region_path.parent.mkdir(parents=True)
            region_path.write_text(
                '{"region":{"x_percent":12,"y_percent":64,'
                '"width_percent":76,"height_percent":8}}',
                encoding="utf-8",
            )
            video = SimpleNamespace(
                files={
                    "background_audio": str(background),
                    "background_music": str(music),
                },
                enable_audio_separation=True,
                original_video_volume=55,
                background_music_volume=25,
                tts_volume=92,
                subtitle_style={
                    "font_size": 72,
                    "position_x_percent": 47,
                    "position_y_percent": 81,
                    "box_width_percent": 68,
                    "box_height_percent": 7,
                    "outline": 3,
                },
                subtitle_layout_override=True,
                output_format="keep_ratio",
                crop={"zoom_percent": 115, "pan_x_percent": 8, "pan_y_percent": -3},
                speaker_mode="single",
                tts_provider="omnivoice",
                tts_voice="omnivoice:male",
                remove_original_subtitles=True,
                original_subtitle_removal_mode="patch",
                watermark_text="@creator",
                video_width=1080,
                video_height=1920,
                video_id="preview-video",
            )
            host = SimpleNamespace(_selected_video=lambda: video)

            with patch.object(qml_controller.video_store, "get_video_dir", return_value=temporary):
                preview = HaizFlowController.reviewPreviewMedia.fget(host)

            self.assertFalse(preview["useVideoAudio"])
            self.assertTrue(preview["backgroundSource"].startswith("file:"))
            self.assertTrue(preview["musicSource"].startswith("file:"))
            self.assertEqual(preview["backgroundVolume"], 0.55)
            self.assertEqual(preview["musicVolume"], 0.25)
            self.assertEqual(preview["ttsVolume"], 0.92)
            self.assertEqual(preview["subtitleStyle"]["font_size"], 72)
            self.assertEqual(preview["subtitleStyle"]["position_y_percent"], 81)
            self.assertTrue(preview["subtitleLayoutOverride"])
            self.assertEqual(preview["crop"]["zoom_percent"], 115)
            self.assertEqual(preview["speakerMode"], "single")
            self.assertEqual(preview["ttsProvider"], "omnivoice")
            self.assertEqual(preview["watermarkText"], "@creator")
            self.assertEqual(preview["ocrRegion"]["height_percent"], 8)

    def test_browser_context_delete_uses_stable_project_key_without_opening_row(self):
        signal = lambda: SimpleNamespace(emit=Mock())
        host = SimpleNamespace(
            _media_downloader=SimpleNamespace(has_project_work=Mock(return_value=False)),
            _tiktok_publisher=SimpleNamespace(has_project_work=Mock(return_value=False)),
            _channel_importer=SimpleNamespace(cancel_project=Mock(return_value=True)),
            _channel_import_targets={},
            _processing_queue=SimpleNamespace(discard=Mock(), active_video_id=None),
            _deleted_video_ids=set(),
            _selected_project_key="another-project",
            _video_project_key=Mock(),
            appAlertRequested=signal(),
            refreshVideos=Mock(),
            videoDeleted=signal(),
        )
        project = {
            "key": "project-from-proxy",
            "project_name": "Project from proxy",
            "project_type": "single",
        }

        with (
            patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes),
            patch("haizflow.desktop.project_commands_controller.video_store.list_videos", return_value=[]),
            patch("haizflow.desktop.project_commands_controller.project_store.validate_project_deletion_by_key") as validate,
            patch("haizflow.desktop.project_commands_controller.project_store.delete_project_by_key") as delete,
        ):
            deleted = ProjectCommandsController(host).delete_project_summary(project)

        self.assertTrue(deleted)
        validate.assert_called_once_with("project-from-proxy")
        delete.assert_called_once_with("project-from-proxy")
        self.assertEqual(host._selected_project_key, "another-project")
        host.refreshVideos.assert_called_once()

    def test_typed_grid_context_delete_resolves_row_without_opening_project(self):
        project = {
            "key": "download-project",
            "project_name": "Download project",
            "project_type": "download",
        }
        model = SimpleNamespace(project_at=Mock(return_value=project))
        commands = SimpleNamespace(delete_project_summary=Mock(return_value=True))
        host = SimpleNamespace(_project_model_for_type=Mock(return_value=model))

        with patch.object(HaizFlowController, "_project_commands_for", return_value=commands):
            deleted = HaizFlowController.deleteProjectInMode(host, 3, "download")

        self.assertTrue(deleted)
        host._project_model_for_type.assert_called_once_with("download")
        model.project_at.assert_called_once_with(3)
        commands.delete_project_summary.assert_called_once_with(project)


if __name__ == "__main__":
    unittest.main()

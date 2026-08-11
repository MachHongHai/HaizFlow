import os
import json
import queue
import threading
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Property, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QmlNamedElement, QmlSingleton

from haizflow.desktop.activity_log import ActivityLogBuffer
from haizflow.desktop.catalog import POPULAR_TARGET_LANGUAGES
from haizflow.desktop.channel_import import ChannelImportCoordinator
from haizflow.desktop.localization import QMessageBox, _set_ui_language
from haizflow.desktop.media import (
    collect_batch_video_paths,
    create_video_thumbnail_path,
    normalize_video_path,
    open_path,
    resolve_video_file,
    thumbnail_source,
)
from haizflow.desktop.media_probe import VideoDimensionProbe
from haizflow.desktop.models import (
    ProjectGridModel,
    ProjectListModel,
    SocialProjectSourceListModel,
    SocialPublishListModel,
    VideoListModel,
)
from haizflow.desktop.preview_media_controller import PreviewMediaController
from haizflow.desktop.audio_preview_controller import AudioPreviewController
from haizflow.desktop.media_download_controller import MediaDownloadController
from haizflow.desktop.processing_lifecycle_controller import ProcessingLifecycleController
from haizflow.desktop.project_workspace_controller import ProjectWorkspaceController
from haizflow.desktop.project_commands_controller import ProjectCommandsController
from haizflow.desktop.project_import_controller import ProjectImportController
from haizflow.desktop.catalog_media_controller import CatalogMediaController
from haizflow.desktop.diagnostics_controller import DiagnosticsController
from haizflow.desktop.external_links import open_external_url
from haizflow.desktop.runtime_device_controller import RuntimeDeviceController
from haizflow.desktop.settings_controller import SettingsController
from haizflow.desktop.social_publish_controller import SocialPublishController
from haizflow.desktop.presenters import (
    build_project_summaries,
    format_duration,
    format_memory_size,
    language_label,
    voice_options_for_language,
)
from haizflow.desktop.url_import import VideoUrlImportCoordinator

from haizflow.config import MODELS_DIR, RUNTIME_DATA_DIR
from haizflow.core.events import subscribe_log, unsubscribe_log
from haizflow.core.hardware import (
    basic_hardware_capabilities,
    configure_processing_device,
    clear_runtime_profile_cache,
    detect_hardware_capabilities,
    recommended_processing_device,
    runtime_profile_for,
    validate_processing_device,
)
from haizflow.pipeline.process_registry import pause_video
from haizflow.schemas.video import CropSettings, VideoConfig, SubtitleStyle
from haizflow.services import desktop_settings, video_store, project_store
from haizflow.services.desktop_videos import create_desktop_video, migrate_legacy_single_export
from haizflow.services.processing_queue import SerialProcessingQueue
from haizflow.services.model_bootstrap import models_ready
from haizflow.services.translation import shutdown_hymt2_worker

QML_IMPORT_NAME = "HaizFlow"
QML_IMPORT_MAJOR_VERSION = 1


@QmlNamedElement("AppController")
@QmlSingleton
class HaizFlowController(QObject):
    _qml_instance = None
    _THUMBNAIL_RETRY_MAX_ATTEMPTS = 3
    _THUMBNAIL_RETRY_INITIAL_DELAY_SECONDS = 15.0

    videoPathChanged = Signal()
    videoThumbnailChanged = Signal()
    targetLanguageChanged = Signal()
    ttsVoiceChanged = Signal()
    ttsVoiceOptionsChanged = Signal()
    enableAudioSeparationChanged = Signal()
    originalVolumeChanged = Signal()
    backgroundMusicVolumeChanged = Signal()
    ttsVolumeChanged = Signal()
    watermarkTextChanged = Signal()
    subtitleSettingsChanged = Signal()
    backgroundMusicChanged = Signal()
    backgroundMusicImportChanged = Signal()
    batchBackgroundMusicDraftReady = Signal(str)
    audioPreviewChanged = Signal()
    workflowModeChanged = Signal()
    selectedVideoChanged = Signal()
    selectedElapsedChanged = Signal()
    processingChanged = Signal()
    logsChanged = Signal()
    statusMessageChanged = Signal()
    runtimeStateChanged = Signal()
    modelSetupChanged = Signal()
    videoDeleted = Signal()
    batchDeleted = Signal()
    batchChanged = Signal()
    settingsChanged = Signal()
    hardwareChanged = Signal()
    languageOptionsChanged = Signal()
    projectSetupChanged = Signal()
    projectPrepared = Signal()
    urlImportFinished = Signal()
    channelImportChanged = Signal()
    mediaImportChanged = Signal()
    socialPublishStateChanged = Signal()
    zernioAccountsChanged = Signal()
    zernioPostOptionsChanged = Signal()
    # Kept as a coarse compatibility signal for Python-side observers. QML
    # properties use the narrower signals above so upload progress does not
    # invalidate every Zernio binding on the page.
    tiktokPublishChanged = Signal()

    def __init__(self):
        super().__init__()
        type(self)._qml_instance = self
        self.videos = VideoListModel()
        self.projects = ProjectListModel()
        self.single_projects = ProjectGridModel()
        self.batch_projects = ProjectGridModel()
        self.download_projects = ProjectGridModel()
        self.publish_projects = ProjectGridModel()
        self.batch_videos = VideoListModel()
        self.tiktok_publish_items = SocialPublishListModel()
        self.tiktok_project_sources = SocialProjectSourceListModel()
        self._video_path = ""
        self._video_thumbnail_source = ""
        self._target_language = "vi"
        self._tts_voice = "vi-VN-HoaiMyNeural"
        self._enable_audio_separation = False
        self._original_volume = 60
        self._background_music_volume = 30
        self._tts_volume = 100
        self._watermark_text = ""
        self._remove_original_subtitles = True
        self._subtitle_style = SubtitleStyle()
        self._subtitle_layout_override = False
        self._background_music_path = ""
        self._background_music_import_busy = False
        self._background_music_import_status = ""
        self._audio_preview_events = queue.Queue()
        self._audio_preview_source = ""
        self._audio_preview_original_source = ""
        self._audio_preview_background_music_source = ""
        self._audio_preview_state = "idle"
        self._workflow_mode = "A"
        self._selected_video_id = None
        self._selected_video_snapshot = None
        self.selectedVideoChanged.connect(self._refresh_selected_video_snapshot)
        self.selectedVideoChanged.connect(self.selectedElapsedChanged.emit)
        self._selected_project_key = ""
        self._device_switching = False
        self._pending_processing_device = ""
        self._model_runtime_lock = threading.Lock()
        self._initial_model_warmup_done = threading.Event()
        self._runtime_probe_error = ""
        self._deleted_video_ids = set()
        self._shutdown_started = False
        self._close_confirmed = False
        self._warmup_thread: threading.Thread | None = None
        self._model_setup_cancel_event = threading.Event()
        self._model_setup_events = queue.Queue()
        self._model_setup_state = "ready" if os.getenv("HAIZFLOW_SMOKE_TEST") == "1" else "checking"
        self._model_setup_component = ""
        self._model_setup_detail = "Checking installed models"
        self._model_setup_completed_bytes = 0
        self._model_setup_total_bytes = 0
        self._model_setup_target_device = ""
        self._startup_maintenance_thread: threading.Thread | None = None
        self._startup_maintenance_events = queue.Queue()
        self._hardware_probe_events = queue.Queue()
        self._hardware_probe_lock = threading.Lock()
        self._hardware_probe_running = False
        self._startup_hardware_resolved = False
        self._background_shutdown_event = threading.Event()
        self._processing_lifecycle = ProcessingLifecycleController(self)
        self._processing_queue = SerialProcessingQueue(
            self._execute_pipeline,
            on_started=self._on_queue_video_started,
            on_finished=self._on_queue_video_finished,
            on_idle=self._on_processing_queue_idle,
            on_error=self._on_processing_queue_error,
        )
        self._batch_video_ids = []
        self._catalog_videos = {}
        self._project_summaries_by_key = {}
        self._batch_running = False
        self._batch_stop_requested = False
        self._log_buffer = ActivityLogBuffer()
        self._logs = ""
        self._status_message = "Ready"
        self._runtime_state = "ready" if os.getenv("HAIZFLOW_SMOKE_TEST") == "1" else "warming"
        self._preview_media = PreviewMediaController(self)
        self._audio_preview = AudioPreviewController(self)
        self._media_downloader = MediaDownloadController(self)
        self._tiktok_publisher = SocialPublishController(self)
        self._settings_controller = SettingsController(self)
        self._project_workspace = ProjectWorkspaceController(self)
        self._project_commands = ProjectCommandsController(self)
        self._project_import = ProjectImportController(self)
        self._catalog_media = CatalogMediaController(self)
        self._diagnostics = DiagnosticsController(self)
        self._runtime_device = RuntimeDeviceController(self)
        settings = desktop_settings.load_settings()
        self._settings_theme = settings["theme"]
        self._settings_language = settings["language"]
        self._settings_processing_device = settings["processing_device"]
        self._processing_device_origin = settings["processing_device_origin"]
        _set_ui_language(self._settings_language)
        # Keep the first frame independent from Torch/CUDA initialization.  The
        # warm-up worker replaces this cheap snapshot with a full probe before
        # it selects or loads any model runtime.
        clear_runtime_profile_cache()
        capabilities = basic_hardware_capabilities()
        self._hardware_capabilities = capabilities
        self._hardware_telemetry_active = False
        configure_processing_device(self._settings_processing_device)
        self._active_processing_device = self._settings_processing_device
        if os.getenv("HAIZFLOW_SMOKE_TEST") != "1" and models_ready(
            Path(MODELS_DIR), self._active_processing_device
        ):
            # Integrity markers make this a small local check. A completed
            # installation goes straight to background warm-up with no setup UI.
            self._model_setup_state = "ready"
            self._model_setup_detail = "Models are ready"
        self._project_directory = os.path.join(RUNTIME_DATA_DIR, "projects")
        self._project_name = ""
        self._project_type = "single"
        self._log_queue = queue.Queue()
        self._media_import_events = queue.Queue()
        self._media_import_busy = False
        self._media_import_total = 0
        self._media_import_completed = 0
        self._media_import_status = ""
        self._thumbnail_refresh_running = False
        self._thumbnail_refresh_thread: threading.Thread | None = None
        self._thumbnail_retry_failures: dict[str, tuple[str, int, float]] = {}
        self._thumbnail_retry_lock = threading.Lock()
        self._dimension_probe = VideoDimensionProbe(self._on_video_dimensions_ready)
        self._url_importer = VideoUrlImportCoordinator(self)
        self._url_import_target = None
        self._url_importer.downloadReady.connect(self._handle_url_download_ready)
        self._url_importer.importFinished.connect(self.urlImportFinished.emit)
        self._channel_importer = ChannelImportCoordinator(self)
        self._channel_importer.set_worker_limit_provider(
            lambda: 1 if self._processing_queue.active_video_id else 2
        )
        self._channel_import_targets = {}
        self._channel_importer.changed.connect(self.channelImportChanged.emit)
        self._channel_importer.videoReady.connect(self._handle_channel_video_ready)
        self._channel_importer.downloadsFinished.connect(self._finish_channel_import_target)

        if os.getenv("HAIZFLOW_SMOKE_TEST") == "1":
            self._initial_model_warmup_done.set()
        else:
            self._warmup_thread = threading.Thread(
                target=self._warm_models_at_startup,
                name="haizflow-model-warmup",
                daemon=True,
            )
            self._warmup_thread.start()

        subscribe_log(self._on_video_log)
        self._log_timer = QTimer(self)
        self._log_timer.timeout.connect(self._drain_log_queue)
        self._log_timer.start(500)

        # These coordinators only transfer already-computed worker results to
        # Qt.  One dispatcher avoids five independent 100 ms wake-ups on the
        # GUI thread while preserving the same response latency.
        self._background_events_timer = QTimer(self)
        self._background_events_timer.timeout.connect(self._drain_background_events)
        self._background_events_timer.start(100)

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self.poll_videos)
        self._status_timer.start(1000)

        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.timeout.connect(self._refresh_selected_elapsed)
        self._elapsed_timer.start(1000)

        self._hardware_timer = QTimer(self)
        self._hardware_timer.timeout.connect(self._refresh_live_hardware)
        self._hardware_timer.start(5000)

        self.refreshVideos()
        self._last_video_metadata_revision = video_store.metadata_revision()
        # Let Qt render the first frame before migrations touch large workspaces or invoke FFmpeg.
        QTimer.singleShot(0, self._start_startup_maintenance)

    def _drain_media_import_events(self) -> None:
        self._project_import.drain_background_events()

    def _drain_tiktok_publish_events(self) -> None:
        self._tiktok_publisher.drain_events()

    def _drain_audio_preview_events(self) -> None:
        self._audio_preview.drain_events()

    def _drain_background_events(self) -> None:
        self._drain_media_import_events()
        self._drain_tiktok_publish_events()
        self._drain_audio_preview_events()
        self._drain_startup_maintenance_events()
        self._drain_model_setup_events()
        HaizFlowController._runtime_device_for(self).drain_hardware_events()

    def _refresh_selected_elapsed(self) -> None:
        video = self._selected_video()
        if video and video.status == "processing" and video.started_at:
            self.selectedElapsedChanged.emit()

    def _start_startup_maintenance(self) -> None:
        if self._shutdown_started or self._startup_maintenance_thread:
            return
        self._startup_maintenance_thread = threading.Thread(
            target=self._run_startup_maintenance,
            name="haizflow-startup-maintenance",
            daemon=True,
        )
        self._startup_maintenance_thread.start()

    def _run_startup_maintenance(self) -> None:
        try:
            migrated = video_store.migrate_legacy_project_data()
            if self._background_shutdown_event.is_set():
                return
            recovered = video_store.recover_interrupted_videos()
            if self._background_shutdown_event.is_set():
                return
            self._migrate_legacy_project_thumbnails()
            if self._background_shutdown_event.is_set():
                return
            self._startup_maintenance_events.put({"migrated": migrated, "recovered": recovered})
        except Exception as exc:
            self._startup_maintenance_events.put({"error": str(exc)})

    def _drain_startup_maintenance_events(self) -> None:
        try:
            result = self._startup_maintenance_events.get_nowait()
        except queue.Empty:
            return
        if result.get("error"):
            self._status_message = f"Startup maintenance could not finish: {result['error']}"
        else:
            migrated = result.get("migrated") or []
            recovered = result.get("recovered") or []
            if recovered:
                self._status_message = (
                    f"Recovered {len(recovered)} interrupted video(s). They are paused and ready to resume."
                )
            elif migrated:
                self._status_message = f"Organized {len(migrated)} video workspace(s) into their projects."
            self.refreshVideos()
        self.statusMessageChanged.emit()

    def _drain_model_setup_events(self) -> None:
        changed = False
        while True:
            try:
                event = self._model_setup_events.get_nowait()
            except queue.Empty:
                break
            state = event.get("state", self._model_setup_state)
            self._model_setup_state = state
            self._model_setup_component = event.get("component", "")
            self._model_setup_detail = event.get("detail", "")
            self._model_setup_completed_bytes = max(
                0, int(event.get("completed_bytes", self._model_setup_completed_bytes))
            )
            self._model_setup_total_bytes = max(
                0, int(event.get("total_bytes", self._model_setup_total_bytes))
            )
            changed = True
        if changed:
            self.modelSetupChanged.emit()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Close and not self._close_confirmed:
            if not self._confirm_application_close():
                event.ignore()
                return True
        return super().eventFilter(watched, event)

    def _confirm_application_close(self) -> bool:
        return HaizFlowController._runtime_device_for(self)._confirm_application_close()

    def shutdown(self):
        publisher = getattr(self, "_tiktok_publisher", None)
        if publisher is not None:
            publisher.shutdown()
        return HaizFlowController._runtime_device_for(self).shutdown()

    def _warm_models(self):
        return HaizFlowController._runtime_device_for(self)._warm_models()

    def _warm_models_at_startup(self):
        return HaizFlowController._runtime_device_for(self)._warm_models_at_startup()

    def _warm_models_unlocked(self):
        return HaizFlowController._runtime_device_for(self)._warm_models_unlocked()

    def _switch_processing_device(self, preference: str):
        return HaizFlowController._runtime_device_for(self)._switch_processing_device(preference)

    def _pipeline_is_active(self) -> bool:
        return HaizFlowController._runtime_device_for(self)._pipeline_is_active()

    def _activate_pending_device_for_next_video(self, video_id: str) -> None:
        return HaizFlowController._runtime_device_for(self)._activate_pending_device_for_next_video(video_id)

    def _refresh_live_hardware(self):
        return HaizFlowController._runtime_device_for(self)._refresh_live_hardware()

    @Slot(bool)
    def setHardwareTelemetryActive(self, active: bool):
        return HaizFlowController._runtime_device_for(self).setHardwareTelemetryActive(active)

    def _apply_detected_processing_device(self, device: str):
        return HaizFlowController._runtime_device_for(self)._apply_detected_processing_device(device)

    def _set_warmup_status(self, detail: str):
        return HaizFlowController._runtime_device_for(self)._set_warmup_status(detail)

    @Slot()
    def retryModelSetup(self):
        return HaizFlowController._runtime_device_for(self).retryModelSetup()

    @Slot()
    def cancelModelSetup(self):
        return HaizFlowController._runtime_device_for(self).cancelModelSetup()

    @Property(QObject, constant=True)
    def videoModel(self):
        return self.videos

    @Property(QObject, constant=True)
    def projectModel(self):
        return self.projects

    @Property(QObject, constant=True)
    def singleProjectModel(self):
        return self.single_projects

    @Property(QObject, constant=True)
    def batchProjectModel(self):
        return self.batch_projects

    @Property(QObject, constant=True)
    def downloadProjectModel(self):
        return self.download_projects

    @Property(QObject, constant=True)
    def publishProjectModel(self):
        return self.publish_projects

    @Property(QObject, constant=True)
    def tiktokPublishModel(self):
        return self.tiktok_publish_items

    @Property(QObject, constant=True)
    def tiktokProjectSourceModel(self):
        return self.tiktok_project_sources

    @Property(bool, notify=socialPublishStateChanged)
    def tiktokPublishBusy(self):
        return self._tiktok_publisher.busy

    @Property(bool, notify=zernioAccountsChanged)
    def zernioAccountSyncing(self):
        return self._tiktok_publisher.account_syncing

    @Property(str, notify=socialPublishStateChanged)
    def tiktokPublishStatus(self):
        return self._tiktok_publisher.status

    @Property(str, notify=socialPublishStateChanged)
    def tiktokDefaultCaption(self):
        return self._tiktok_publisher.default_caption

    @Property(str, notify=socialPublishStateChanged)
    def tiktokDefaultHashtags(self):
        return self._tiktok_publisher.default_hashtags

    @Property(int, notify=socialPublishStateChanged)
    def tiktokPublishCount(self):
        return self._tiktok_publisher.count

    @Property(int, notify=socialPublishStateChanged)
    def tiktokPostedCount(self):
        return self._tiktok_publisher.posted_count

    @Property(int, notify=socialPublishStateChanged)
    def tiktokProjectSourceSelectedCount(self):
        return self._tiktok_publisher.project_source_selected_count

    @Property(bool, notify=zernioAccountsChanged)
    def zernioApiKeyConfigured(self):
        return self._tiktok_publisher.api_key_configured

    @Property(bool, notify=zernioAccountsChanged)
    def zernioApiKeyVerified(self):
        return self._tiktok_publisher.api_key_verified

    @Property(int, notify=zernioAccountsChanged)
    def zernioConnectedAccountCount(self):
        return self._tiktok_publisher.connected_account_count

    @Property(int, notify=zernioAccountsChanged)
    def zernioProfileCount(self):
        return self._tiktok_publisher.profile_count

    @Property(str, notify=zernioAccountsChanged)
    def zernioConnectionProfileName(self):
        return self._tiktok_publisher.connection_profile_name

    @Property(bool, notify=zernioAccountsChanged)
    def zernioOauthSyncPending(self):
        return self._tiktok_publisher.oauth_sync_pending

    @Property(bool, notify=zernioAccountsChanged)
    def zernioAccountReady(self):
        return self._tiktok_publisher.account_ready

    @Property(bool, notify=zernioAccountsChanged)
    def zernioCanPostMore(self):
        return self._tiktok_publisher.can_post_more

    @Property("QStringList", notify=zernioAccountsChanged)
    def zernioTikTokAccounts(self):
        return self._tiktok_publisher.account_names

    @Property("QStringList", notify=zernioAccountsChanged)
    def zernioConnections(self):
        return self._tiktok_publisher.account_names

    @Property("QStringList", notify=zernioAccountsChanged)
    def zernioConnectionPlatforms(self):
        return self._tiktok_publisher.account_platforms

    @Property(str, notify=zernioAccountsChanged)
    def zernioSelectedPlatform(self):
        return self._tiktok_publisher.selected_platform

    @Property(str, notify=zernioAccountsChanged)
    def zernioSelectedPlatformLabel(self):
        return self._tiktok_publisher.selected_platform_label

    @Property(int, notify=zernioAccountsChanged)
    def zernioSelectedAccountIndex(self):
        return self._tiktok_publisher.selected_account_index

    @Property(str, notify=zernioAccountsChanged)
    def zernioSelectedAccountName(self):
        return self._tiktok_publisher.selected_account_name

    @Property("QStringList", notify=zernioPostOptionsChanged)
    def zernioPrivacyLevels(self):
        return self._tiktok_publisher.privacy_levels

    @Property(str, notify=zernioPostOptionsChanged)
    def zernioPrivacyLevel(self):
        return self._tiktok_publisher.privacy_level

    @Property(bool, notify=zernioPostOptionsChanged)
    def zernioPublishNow(self):
        return self._tiktok_publisher.publish_now

    @Property(bool, notify=zernioPostOptionsChanged)
    def zernioAllowComment(self):
        return self._tiktok_publisher.allow_comment

    @Property(bool, notify=zernioPostOptionsChanged)
    def zernioAllowDuet(self):
        return self._tiktok_publisher.allow_duet

    @Property(bool, notify=zernioPostOptionsChanged)
    def zernioAllowStitch(self):
        return self._tiktok_publisher.allow_stitch

    @Property(bool, notify=zernioPostOptionsChanged)
    def zernioShareToFeed(self):
        return self._tiktok_publisher.share_to_feed

    @Property(bool, notify=zernioPostOptionsChanged)
    def zernioAiGenerated(self):
        return self._tiktok_publisher.ai_generated

    @Property(str, notify=zernioPostOptionsChanged)
    def zernioFirstComment(self):
        return self._tiktok_publisher.first_comment

    @Property(bool, notify=zernioPostOptionsChanged)
    def zernioCommentAvailable(self):
        return self._tiktok_publisher.comment_available

    @Property(bool, notify=zernioPostOptionsChanged)
    def zernioDuetAvailable(self):
        return self._tiktok_publisher.duet_available

    @Property(bool, notify=zernioPostOptionsChanged)
    def zernioStitchAvailable(self):
        return self._tiktok_publisher.stitch_available

    @Property(bool, notify=socialPublishStateChanged)
    def zernioPublishConsentConfirmed(self):
        return self._tiktok_publisher.consent_confirmed

    @Property(QObject, constant=True)
    def channelImporter(self):
        return self._channel_importer

    @Property(QObject, constant=True)
    def mediaDownloader(self):
        return self._media_downloader

    @Property(bool, notify=mediaImportChanged)
    def mediaImportBusy(self):
        return self._media_import_busy

    @Property(int, notify=mediaImportChanged)
    def mediaImportTotal(self):
        return self._media_import_total

    @Property(int, notify=mediaImportChanged)
    def mediaImportCompleted(self):
        return self._media_import_completed

    @Property(str, notify=mediaImportChanged)
    def mediaImportStatus(self):
        return self._media_import_status

    @Property(bool, notify=channelImportChanged)
    def hasChannelImportSession(self):
        return bool(self._channel_importer.sessionId)

    @Property(bool, notify=channelImportChanged)
    def channelImportBusy(self):
        return self._channel_importer.busy

    @Property(int, notify=channelImportChanged)
    def channelImportProgress(self):
        return self._channel_importer.progress

    @Property(str, notify=channelImportChanged)
    def channelImportStatus(self):
        return self._channel_importer.status

    @Property(str, notify=channelImportChanged)
    def channelImportName(self):
        return self._channel_importer.channelName

    @Property(int, notify=channelImportChanged)
    def channelImportCandidateCount(self):
        return self._channel_importer.candidateCount

    @Property(int, notify=channelImportChanged)
    def channelImportImportedCount(self):
        return self._channel_importer.importedCount

    @Property(int, notify=channelImportChanged)
    def channelImportFailedCount(self):
        return self._channel_importer.failedCount

    @Property(QObject, constant=True)
    def batchVideoModel(self):
        return self.batch_videos

    @Property(bool, notify=batchChanged)
    def isBatchRunning(self):
        return any(self._processing_queue.contains(video_id) for video_id in self._batch_video_ids)

    @Property(int, notify=batchChanged)
    def batchCount(self):
        return len(self._batch_video_ids)

    def _batch_catalog_videos(self):
        catalog = getattr(self, "_catalog_videos", {})
        videos = []
        for video_id in self._batch_video_ids:
            video = catalog.get(video_id)
            if video is None:
                video = video_store.get_video(video_id)
            if video is not None:
                videos.append(video)
        return videos

    @Property(int, notify=batchChanged)
    def batchCompletedCount(self):
        completed_states = {"done", "failed", "cancelled"}
        videos = self._batch_catalog_videos()
        return sum(1 for video in videos if video and video.status in completed_states)

    @Property(int, notify=batchChanged)
    def batchPendingCount(self):
        videos = self._batch_catalog_videos()
        return sum(
            1
            for video in videos
            if video and video.status == "pending" and not self._processing_queue.contains(video.video_id)
        )

    @Property(int, notify=batchChanged)
    def batchPausedCount(self):
        videos = self._batch_catalog_videos()
        return sum(1 for video in videos if video and video.status == "paused")

    @Property(int, notify=batchChanged)
    def batchProgress(self):
        videos = self._batch_catalog_videos()
        return round(sum(video.progress for video in videos) / len(videos)) if videos else 0

    @Property(str, notify=batchChanged)
    def batchTargetLanguageLabel(self):
        if not self._batch_video_ids:
            return self._language_label(self._target_language)
        videos = self._batch_catalog_videos()
        languages = {video.target_language for video in videos if video}
        if len(languages) > 1:
            return "Mixed settings"
        return self._language_label(next(iter(languages))) if languages else self._language_label(self._target_language)

    @Property(str, notify=videoPathChanged)
    def videoPath(self):
        return self._video_path

    @videoPath.setter
    def videoPath(self, value):
        self._set_video_path(value)

    def _set_video_path(self, value: str, *, refresh_thumbnail: bool = False) -> None:
        path_changed = self._video_path != value
        if not path_changed and not refresh_thumbnail:
            return
        self._video_path = value
        thumbnail_path = (
            self._video_thumbnail_path(self._selected_video_id)
            if self._selected_video_id
            else self._draft_thumbnail_path()
        )
        self._video_thumbnail_source = self._create_video_thumbnail(value, thumbnail_path)
        self.videoPathChanged.emit()
        self.videoThumbnailChanged.emit()

    @Property(str, notify=videoThumbnailChanged)
    def videoThumbnailSource(self):
        return self._video_thumbnail_source

    @Property("QVariantList", notify=languageOptionsChanged)
    def targetLanguageOptions(self):
        return [
            {
                "code": code,
                "englishName": english_name,
                "nativeName": native_name,
                "label": self._language_label(code),
                "search": f"{code} {english_name} {native_name}".lower(),
            }
            for code, english_name, native_name in POPULAR_TARGET_LANGUAGES
        ]

    @Property(str, notify=targetLanguageChanged)
    def targetLanguage(self):
        return self._target_language

    @targetLanguage.setter
    def targetLanguage(self, value):
        language = str(value or "vi")
        language_changed = self._target_language != language
        normalized_voice = self._normalized_voice_for_language(language, self._tts_voice)
        voice_changed = self._tts_voice != normalized_voice
        if not language_changed and not voice_changed:
            return

        self._target_language = language
        self._tts_voice = normalized_voice
        if language_changed:
            self.targetLanguageChanged.emit()
            self.languageOptionsChanged.emit()
        if voice_changed:
            self.ttsVoiceChanged.emit()
        # The option model and selected index depend on both language and voice.
        self.ttsVoiceOptionsChanged.emit()

    @Property(str, notify=languageOptionsChanged)
    def targetLanguageLabel(self):
        return self._language_label(self._target_language)

    @Property(str, notify=ttsVoiceChanged)
    def ttsVoice(self):
        return self._tts_voice

    @ttsVoice.setter
    def ttsVoice(self, value):
        normalized_voice = self._normalized_voice_for_language(self._target_language, value)
        if self._tts_voice != normalized_voice:
            self._tts_voice = normalized_voice
            self.ttsVoiceChanged.emit()
            self.ttsVoiceOptionsChanged.emit()

    @Property("QVariantList", notify=ttsVoiceOptionsChanged)
    def ttsVoiceOptions(self):
        return self._voice_options_for_language(self._target_language)

    @Slot(str, result="QVariantList")
    def voiceOptionsForLanguage(self, language_code: str):
        return self._voice_options_for_language(str(language_code or "vi"))

    @Property(int, notify=ttsVoiceOptionsChanged)
    def ttsVoiceIndex(self):
        voices = self._voice_options_for_language(self._target_language)
        for index, item in enumerate(voices):
            if item["voice"] == self._tts_voice:
                return index
        return 0

    @Property(bool, notify=enableAudioSeparationChanged)
    def enableAudioSeparation(self):
        return self._enable_audio_separation

    @enableAudioSeparation.setter
    def enableAudioSeparation(self, value):
        if self._enable_audio_separation != value:
            self._enable_audio_separation = value
            self.enableAudioSeparationChanged.emit()

    @Property(int, notify=originalVolumeChanged)
    def originalVolume(self):
        return self._original_volume

    @originalVolume.setter
    def originalVolume(self, value):
        value = max(0, min(100, int(value)))
        if self._original_volume != value:
            self._original_volume = value
            self.originalVolumeChanged.emit()

    @Property(int, notify=backgroundMusicVolumeChanged)
    def backgroundMusicVolume(self):
        return self._background_music_volume

    @backgroundMusicVolume.setter
    def backgroundMusicVolume(self, value):
        value = max(0, min(100, int(value)))
        if self._background_music_volume != value:
            self._background_music_volume = value
            self.backgroundMusicVolumeChanged.emit()

    @Property(int, notify=ttsVolumeChanged)
    def ttsVolume(self):
        return self._tts_volume

    @ttsVolume.setter
    def ttsVolume(self, value):
        value = max(0, min(100, int(value)))
        if self._tts_volume != value:
            self._tts_volume = value
            self.ttsVolumeChanged.emit()

    @Property(str, notify=watermarkTextChanged)
    def watermarkText(self):
        return self._watermark_text

    @watermarkText.setter
    def watermarkText(self, value):
        normalized = " ".join(str(value or "").split())[:80]
        if self._watermark_text != normalized:
            self._watermark_text = normalized
            self.watermarkTextChanged.emit()

    @Property(bool, notify=subtitleSettingsChanged)
    def removeOriginalSubtitles(self):
        return self._remove_original_subtitles

    @removeOriginalSubtitles.setter
    def removeOriginalSubtitles(self, value):
        normalized = bool(value)
        changed = self._remove_original_subtitles != normalized
        # A manually positioned subtitle is only meaningful when the original
        # frame is kept.  Leaving this flag enabled lets a stale preview layout
        # override the OCR region after the user switches back to covering the
        # original subtitles.
        layout_changed = normalized and self._subtitle_layout_override
        if changed or layout_changed:
            self._remove_original_subtitles = normalized
            if layout_changed:
                self._subtitle_layout_override = False
            self.subtitleSettingsChanged.emit()

    def _set_subtitle_style_value(self, key: str, value: int, minimum: int, maximum: int) -> None:
        normalized = max(minimum, min(maximum, int(value)))
        if int(getattr(self._subtitle_style, key)) == normalized:
            return
        style = self._subtitle_style.model_dump()
        style[key] = normalized
        self._subtitle_style = SubtitleStyle(**style)
        self._subtitle_layout_override = True
        self.subtitleSettingsChanged.emit()

    @Property(int, notify=subtitleSettingsChanged)
    def subtitleFontSize(self):
        return self._subtitle_style.font_size

    @subtitleFontSize.setter
    def subtitleFontSize(self, value):
        self._set_subtitle_style_value("font_size", value, 10, 160)

    @Property(int, notify=subtitleSettingsChanged)
    def subtitlePositionXPercent(self):
        return self._subtitle_style.position_x_percent

    @subtitlePositionXPercent.setter
    def subtitlePositionXPercent(self, value):
        self._set_subtitle_style_value("position_x_percent", value, 0, 100)

    @Property(int, notify=subtitleSettingsChanged)
    def subtitlePositionYPercent(self):
        return self._subtitle_style.position_y_percent

    @subtitlePositionYPercent.setter
    def subtitlePositionYPercent(self, value):
        self._set_subtitle_style_value("position_y_percent", value, 0, 100)

    @Property(int, notify=subtitleSettingsChanged)
    def subtitleBoxWidthPercent(self):
        return self._subtitle_style.box_width_percent

    @subtitleBoxWidthPercent.setter
    def subtitleBoxWidthPercent(self, value):
        self._set_subtitle_style_value("box_width_percent", value, 20, 100)

    @Property(int, notify=subtitleSettingsChanged)
    def subtitleBoxHeightPercent(self):
        return self._subtitle_style.box_height_percent

    @subtitleBoxHeightPercent.setter
    def subtitleBoxHeightPercent(self, value):
        self._set_subtitle_style_value("box_height_percent", value, 1, 100)

    @Property(str, notify=backgroundMusicChanged)
    def backgroundMusicPath(self):
        return self._background_music_path

    @Property(bool, notify=backgroundMusicImportChanged)
    def backgroundMusicImportBusy(self):
        return self._background_music_import_busy

    @Property(str, notify=backgroundMusicImportChanged)
    def backgroundMusicImportStatus(self):
        return self._background_music_import_status

    @Property(str, notify=audioPreviewChanged)
    def audioPreviewSource(self):
        return self._audio_preview_source

    @Property(str, notify=audioPreviewChanged)
    def audioPreviewOriginalSource(self):
        return self._audio_preview_original_source

    @Property(str, notify=audioPreviewChanged)
    def audioPreviewBackgroundMusicSource(self):
        return self._audio_preview_background_music_source

    @Property(str, notify=audioPreviewChanged)
    def audioPreviewState(self):
        return self._audio_preview_state

    @Property(str, notify=workflowModeChanged)
    def workflowMode(self): return self._workflow_mode

    @workflowMode.setter
    def workflowMode(self, value):
        value = "review" if value == "review" else "A"
        if self._workflow_mode != value:
            self._workflow_mode = value
            self.workflowModeChanged.emit()

    @Property(bool, notify=processingChanged)
    def isProcessing(self):
        return self._processing_queue.has_work or self._device_switching

    @Property(bool, notify=processingChanged)
    def isSelectedVideoProcessing(self):
        return bool(
            self._selected_video_id
            and self._selected_video_id == self._processing_queue.active_video_id
        )

    @Property(bool, notify=selectedVideoChanged)
    def isSelectedVideoQueued(self):
        return bool(self._selected_video_id and self._processing_queue.contains(self._selected_video_id))

    @Property(bool, notify=selectedVideoChanged)
    def canEditSelectedVideo(self):
        """Only freeze the video whose immutable pipeline snapshot is queued."""
        return not (
            self._selected_video_id
            and self._processing_queue.contains(self._selected_video_id)
        )

    @Property(str, notify=processingChanged)
    def processingText(self):
        active_video_id = self._processing_queue.active_video_id
        video = video_store.get_video(active_video_id) if active_video_id else None
        return f"{video.original_filename} | {video.step_detail or video.status}" if video else "No active video"

    def _refresh_selected_video_snapshot(self) -> None:
        self._selected_video_snapshot = (
            video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        )

    def _selected_video(self):
        if not self._selected_video_id:
            return None
        if (
            self._selected_video_snapshot is not None
            and self._selected_video_snapshot.video_id == self._selected_video_id
        ):
            return self._selected_video_snapshot
        self._refresh_selected_video_snapshot()
        return self._selected_video_snapshot

    @Property(str, notify=selectedVideoChanged)
    def selectedTitle(self):
        video = self._selected_video()
        return f"{video.original_filename} | {video.status}" if video else "No video selected"

    @Property(bool, notify=selectedVideoChanged)
    def hasSelectedVideo(self):
        return self._selected_video() is not None

    @Property(bool, notify=projectSetupChanged)
    def hasOpenProject(self):
        if not self._selected_project_key:
            return False
        try:
            return os.path.isdir(project_store.project_root_for_key(self._selected_project_key))
        except (RuntimeError, ValueError):
            return False

    @staticmethod
    def _video_project_key(video) -> str:
        key = str(getattr(video, "project_key", "") or "")
        if key:
            return key
        return project_store.resolve_project_key(
            str(getattr(video, "project_name", "") or ""),
            str(getattr(video, "project_directory", "") or ""),
            "batch" if getattr(video, "project_type", "single") == "batch" else "single",
        )

    def _selected_project_root(self) -> str:
        return project_store.project_root_for_key(self._selected_project_key)

    @Property(bool, notify=selectedVideoChanged)
    def isSelectedBatchVideo(self):
        video = self._selected_video()
        return bool(video and video.project_type == "batch" and video.video_id in self._batch_video_ids)

    @Property("QVariantList", notify=selectedVideoChanged)
    def reviewSegments(self):
        video = self._selected_video()
        if not video or video.status != "awaiting_review":
            return []
        transcript_path = (video.files or {}).get("transcript_json")
        if not isinstance(transcript_path, str) or not transcript_path.strip():
            return []
        try:
            with open(transcript_path, "r", encoding="utf-8") as file:
                segments = json.load(file)
            return segments if isinstance(segments, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    @Property(str, notify=selectedVideoChanged)
    def selectedFileName(self):
        video = self._selected_video()
        return video.original_filename if video else ""

    @Property(str, notify=selectedVideoChanged)
    def selectedStatus(self):
        video = self._selected_video()
        return video.status if video else "none"

    @Property(str, notify=selectedVideoChanged)
    def selectedStep(self):
        video = self._selected_video()
        return video.step_detail or video.step if video else "pending"

    @Property(int, notify=selectedVideoChanged)
    def selectedProgress(self):
        video = self._selected_video()
        return video.progress if video else 0

    @Property(str, notify=selectedVideoChanged)
    def selectedStageLabel(self):
        video = self._selected_video()
        if not video:
            return "Ready"
        labels = {
            "starting": "Preparing project",
            "extracting_audio": "Extracting audio",
            "separating_audio": "Separating vocals",
            "transcribing": "Transcribing speech",
            "translating": "Translating",
            "review_translation": "Waiting for translation review",
            "creating_subtitle": "Creating subtitles",
            "creating_voice": "Generating voice",
            "building_audio_timeline": "Mixing audio",
            "rendering": "Rendering video",
            "paused": "Paused",
            "done": "Export complete",
        }
        return labels.get(video.step, video.step_detail or video.status)

    @Property(str, notify=selectedVideoChanged)
    def selectedProgressDetail(self):
        video = self._selected_video()
        if not video:
            return ""
        item_detail = f"{video.current_item}/{video.total_items}" if video.total_items else ""
        return " | ".join(part for part in (video.step_detail, item_detail) if part)

    @Property(str, notify=selectedElapsedChanged)
    def selectedElapsed(self):
        video = self._selected_video()
        if not video or not video.started_at:
            return ""
        try:
            started_at = datetime.fromisoformat(video.started_at.replace("Z", "+00:00"))
            if video.status == "processing":
                seconds = (datetime.now(timezone.utc) - started_at).total_seconds()
            else:
                finished_at = datetime.fromisoformat(video.updated_at.replace("Z", "+00:00"))
                seconds = (finished_at - started_at).total_seconds()
            return self._format_duration(max(0, seconds))
        except ValueError:
            return ""

    @Property(str, notify=selectedVideoChanged)
    def selectedUpdatedAt(self):
        video = self._selected_video()
        return video.updated_at if video else ""

    @Property(str, notify=selectedVideoChanged)
    def selectedOutputFormat(self):
        video = self._selected_video()
        return video.output_format if video else ""

    @Property(str, notify=selectedVideoChanged)
    def selectedTargetLanguageLabel(self):
        video = self._selected_video()
        return self._language_label(video.target_language) if video else ""

    @Property(str, notify=selectedVideoChanged)
    def selectedTranslatorProvider(self):
        video = self._selected_video()
        return video.translator_provider if video else ""

    @Property(str, notify=selectedVideoChanged)
    def selectedInputPath(self):
        video = self._selected_video()
        return self._resolve_video_file(video, ("video_input", "input_video"), ("input", "video.mp4"))

    @Property(str, notify=selectedVideoChanged)
    def selectedOutputPath(self):
        video = self._selected_video()
        return self._resolve_video_file(video, ("final_video", "output_video"), ("output", "final.mp4"))

    @Property(bool, notify=selectedVideoChanged)
    def hasSelectedOutput(self):
        video = self._selected_video()
        if not video or video.status != "done":
            return False
        output_path = self._resolve_video_file(video, ("final_video", "output_video"), ("output", "final.mp4"))
        return bool(output_path and os.path.isfile(output_path) and os.path.getsize(output_path) > 0)

    @Property(str, notify=selectedVideoChanged)
    def selectedSrtPath(self):
        video = self._selected_video()
        return self._resolve_video_file(video, ("srt_output", "subtitle_output"), ("temp", "vi.srt"))

    @Property(str, notify=selectedVideoChanged)
    def selectedVoicePath(self):
        video = self._selected_video()
        return self._resolve_video_file(video, ("voice_output", "dubbed_audio"), ("temp", "voice_final.wav"))

    @Property(str, notify=selectedVideoChanged)
    def selectedLogsPath(self):
        return video_store.get_video_logs_path(self._selected_video_id) if self._selected_video_id else ""

    @Property(str, notify=logsChanged)
    def logs(self):
        return self._logs

    @Property(str, notify=statusMessageChanged)
    def statusMessage(self):
        return self._status_message

    @Property(str, notify=runtimeStateChanged)
    def runtimeState(self):
        return self._runtime_state

    @Property(bool, notify=modelSetupChanged)
    def modelSetupVisible(self):
        return self._model_setup_state != "ready"

    @Property(bool, notify=modelSetupChanged)
    def modelSetupBusy(self):
        return self._model_setup_state in {"checking", "downloading", "verifying", "warming"}

    @Property(bool, notify=modelSetupChanged)
    def modelSetupCanCancel(self):
        return self._model_setup_state in {"checking", "downloading", "verifying"}

    @Property(int, notify=modelSetupChanged)
    def modelSetupProgress(self):
        if self._model_setup_total_bytes <= 0:
            return 0
        return min(
            100,
            round(self._model_setup_completed_bytes * 100 / self._model_setup_total_bytes),
        )

    @Property(str, notify=modelSetupChanged)
    def modelSetupState(self):
        return self._model_setup_state

    @Property(str, notify=modelSetupChanged)
    def modelSetupComponent(self):
        return self._model_setup_component

    @Property(str, notify=modelSetupChanged)
    def modelSetupDetail(self):
        return self._model_setup_detail

    @Property(str, notify=modelSetupChanged)
    def modelSetupSizeText(self):
        completed = format_memory_size(self._model_setup_completed_bytes)
        total = format_memory_size(self._model_setup_total_bytes)
        return f"{completed} / {total}"

    @Property(str, notify=modelSetupChanged)
    def modelSetupDirectory(self):
        from haizflow.config import MODELS_DIR

        return MODELS_DIR

    @Property(QObject, constant=True)
    def urlImporter(self):
        return self._url_importer

    @Property(str, notify=settingsChanged)
    def settingsTheme(self):
        return self._settings_theme

    @Property(str, notify=settingsChanged)
    def settingsLanguage(self):
        return self._settings_language

    @Property(str, notify=settingsChanged)
    def processingDevice(self):
        return self._settings_processing_device

    @Property(bool, notify=settingsChanged)
    def cpuOnly(self):
        return self._active_processing_device != "gpu"

    @Property(str, notify=settingsChanged)
    def performanceProfileLabel(self):
        return runtime_profile_for(
            self._hardware_capabilities,
            self._active_processing_device,
        ).label

    @Property(str, notify=settingsChanged)
    def performanceProfileDetail(self):
        profile = runtime_profile_for(
            self._hardware_capabilities,
            self._active_processing_device,
        )
        if self._settings_language == "vi":
            if profile.cuda_available:
                return f"Tăng tốc GPU - {profile.cuda_name or 'CUDA'}"
            ram = f"{profile.total_ram_gib:.0f} GB RAM" if profile.total_ram_bytes else "không rõ RAM"
            return f"Chế độ CPU - {ram}, {profile.cpu_threads} luồng"
        return profile.summary

    @Property("QVariantMap", notify=hardwareChanged)
    def hardwareInfo(self):
        """Expose the active graphics adapter and detailed CPU telemetry."""
        capabilities = self._hardware_capabilities
        profile = runtime_profile_for(capabilities, self._active_processing_device)
        active_gpu_name = capabilities.cuda_name if profile.cuda_available else capabilities.active_display_gpu_name
        return {
            "activeGpuName": active_gpu_name,
            "activeGpuRole": "GPU compute" if profile.cuda_available else "Windows display adapter",
            "activeGpuResolution": capabilities.active_display_gpu_resolution,
            "usingGpu": profile.cuda_available,
            "gpuSafe": capabilities.gpu_supported,
            "availableGpuName": capabilities.cuda_name if capabilities.gpu_supported else "",
            "totalVram": self._format_memory_size(capabilities.total_vram_bytes) if profile.cuda_available else "--",
            "freeVram": self._format_memory_size(capabilities.free_vram_bytes) if profile.cuda_available else "--",
            "systemRam": self._format_memory_size(capabilities.total_ram_bytes),
            "logicalCpuCount": capabilities.logical_cpu_count,
            "cpuName": capabilities.cpu_name or "CPU information loading...",
            "cpuPhysicalCores": capabilities.cpu_physical_cores or 0,
            "cpuMaxMhz": capabilities.cpu_max_mhz or 0,
            "acPowered": capabilities.ac_powered,
            "batteryPercent": capabilities.battery_percent if capabilities.battery_percent is not None else -1,
            "recommendedDevice": recommended_processing_device(capabilities),
            "profileLabel": profile.label,
        }

    @Slot(str, result=bool)
    def processingDeviceCompatible(self, preference):
        compatible, _message = validate_processing_device(str(preference), self._hardware_capabilities)
        return compatible

    @Slot(str, result=str)
    def processingDeviceStatus(self, preference):
        preference = str(preference)
        capabilities = self._hardware_capabilities
        compatible, message = validate_processing_device(preference, capabilities)
        if self._settings_language != "vi":
            return message
        if preference == "gpu":
            if not capabilities.cuda_available:
                return "Không phát hiện GPU NVIDIA tương thích CUDA."
            if capabilities.total_vram_bytes < 7 * 1024 ** 3:
                return f"GPU cần ít nhất 7 GB VRAM; hiện có {capabilities.total_vram_bytes / (1024 ** 3):.1f} GB."
            if capabilities.free_vram_bytes and capabilities.free_vram_bytes < 5 * 1024 ** 3:
                return f"GPU cần ít nhất 5 GB VRAM trống; hiện có {capabilities.free_vram_bytes / (1024 ** 3):.1f} GB trống."
            if capabilities.total_ram_bytes and capabilities.total_ram_bytes < 8 * 1024 ** 3:
                return f"GPU cần ít nhất 8 GB RAM hệ thống; hiện có {capabilities.total_ram_bytes / (1024 ** 3):.1f} GB."
            return f"GPU sẵn sàng: {capabilities.cuda_name}, {capabilities.total_vram_bytes / (1024 ** 3):.0f} GB VRAM."
        if preference == "cpu":
            if not compatible:
                return f"Chế độ CPU cần khoảng 6 GB RAM; hiện có {capabilities.total_ram_bytes / (1024 ** 3):.1f} GB."
            return f"CPU sẵn sàng: {capabilities.total_ram_bytes / (1024 ** 3):.0f} GB RAM, {capabilities.logical_cpu_count} luồng logic."
        if capabilities.gpu_supported:
            return f"Chế độ tự động sẽ dùng {capabilities.cuda_name}."
        if capabilities.cpu_supported:
            return "Chế độ tự động sẽ dùng CPU vì GPU hiện không đủ an toàn."
        return "Máy không đáp ứng yêu cầu bộ nhớ tối thiểu của CPU hoặc GPU."

    @Property(str, notify=projectSetupChanged)
    def projectDirectory(self):
        return self._project_directory

    @Property(str, notify=projectSetupChanged)
    def projectName(self):
        return self._project_name

    @Property(str, notify=projectSetupChanged)
    def projectType(self):
        return self._project_type

    @Property(str, notify=projectSetupChanged)
    def projectRoot(self):
        if not self._selected_project_key:
            return ""
        try:
            return project_store.project_root_for_key(self._selected_project_key)
        except (RuntimeError, ValueError):
            return ""

    @Property(str, notify=projectSetupChanged)
    def downloadOutputRoot(self):
        if self._project_type != "download" or not self._selected_project_key:
            return ""
        try:
            return project_store.project_downloads_dir_for_key(self._selected_project_key)
        except (RuntimeError, ValueError):
            return ""

    @Slot()
    def downloadInspectedVideo(self):
        HaizFlowController._project_import_for(self).download_inspected_video()

    def _handle_url_download_ready(self, path, _workspace, mode):
        HaizFlowController._project_import_for(self).handle_url_download_ready(path, _workspace, mode)

    def _import_downloaded_video(self, path: str, mode: str, target) -> bool:
        return HaizFlowController._project_import_for(self).import_downloaded_video(path, mode, target)

    def _current_project_media_keys(self) -> set[str]:
        return HaizFlowController._project_import_for(self).current_project_media_keys()

    @Slot(result=bool)
    def prepareChannelImport(self):
        return HaizFlowController._project_import_for(self).prepare_channel_import()

    @Slot(result=bool)
    def startChannelDownloads(self):
        return HaizFlowController._project_import_for(self).start_channel_downloads()

    def _remember_channel_import_target(self, session_id: str) -> None:
        HaizFlowController._project_import_for(self).remember_channel_import_target(session_id)

    @Slot(int, result=bool)
    def retryChannelVideo(self, row):
        return HaizFlowController._project_import_for(self).retry_channel_video(row)

    def _handle_channel_video_ready(self, path, _workspace, candidate_payload, project_key, session_id):
        HaizFlowController._project_import_for(self).handle_channel_video_ready(path, _workspace, candidate_payload, project_key, session_id)

    @Slot(str)
    def _finish_channel_import_target(self, session_id):
        HaizFlowController._project_import_for(self).finish_channel_import_target(session_id)

    @Slot()
    def browseVideo(self):
        HaizFlowController._project_import_for(self).browse_video()

    @Slot()
    def browseBackgroundMusic(self):
        HaizFlowController._project_import_for(self).browse_background_music()

    @Slot(result=str)
    def chooseBatchBackgroundMusic(self):
        return HaizFlowController._project_import_for(self).choose_batch_background_music()

    @Slot(str, result=bool)
    def importBackgroundMusicFromLink(self, url):
        return HaizFlowController._project_import_for(self).import_background_music_link(url)

    @Slot(str, result=bool)
    def importBatchBackgroundMusicFromLink(self, url):
        return HaizFlowController._project_import_for(self).import_batch_background_music_link(url)

    @Slot()
    def cancelBackgroundMusicLinkImport(self):
        HaizFlowController._project_import_for(self).cancel_background_music_link_import()

    @Slot(result=bool)
    def clearBackgroundMusic(self):
        return HaizFlowController._project_import_for(self).set_background_music("")

    @Slot(result=bool)
    def previewAudioMix(self):
        return self._audio_preview.start()

    @Slot(str, str, bool, int, int, int, str, result=bool)
    def previewBatchAudioMix(
        self,
        target_language: str,
        tts_voice: str,
        enable_audio_separation: bool,
        original_volume: int,
        background_music_volume: int,
        tts_volume: int,
        background_music_path: str,
    ):
        """Preview a batch draft without applying it to each video."""
        preview_video_id = next(
            (
                video_id for video_id in self._batch_video_ids
                if (video := video_store.get_video(video_id))
                and os.path.isfile(str((video.files or {}).get("video_input") or ""))
            ),
            "",
        )
        if not preview_video_id:
            self._status_message = "Add a video to the batch before previewing the audio mix."
            self.statusMessageChanged.emit()
            return False
        return self._audio_preview.start(
            video_id=preview_video_id,
            enable_audio_separation=enable_audio_separation,
            background_music_path=background_music_path,
            original_volume=original_volume,
            background_music_volume=background_music_volume,
            tts_volume=tts_volume,
            voice=tts_voice,
            target_language=target_language,
        )

    @Slot(str, result=bool)
    def replaceSelectedVideoVideo(self, path):
        return HaizFlowController._project_import_for(self).replace_video(self._selected_video_id, path)

    def _replace_video_video(self, video_id, path, media_source=None):
        return HaizFlowController._project_import_for(self).replace_video(video_id, path, media_source)

    @Slot()
    def browseProjectDirectory(self):
        HaizFlowController._project_import_for(self).browse_project_directory()

    @Slot(str)
    def browseProjectDirectoryForType(self, project_type):
        HaizFlowController._project_import_for(self).browse_project_directory(project_type)

    @Slot(str, str, str, result=bool)
    def prepareProject(self, project_name, project_directory, project_type):
        return HaizFlowController._project_import_for(self).prepare_project(project_name, project_directory, project_type)

    @Slot(str, str, str, result=bool)
    def applySettings(self, theme, language, processing_device):
        return HaizFlowController._settings_delegate_for(self).apply(theme, language, processing_device)

    @staticmethod
    def _settings_delegate_for(host):
        return getattr(host, "_settings_controller", None) or SettingsController(host)

    @Slot()
    def resetSettings(self):
        HaizFlowController._settings_delegate_for(self).reset()

    @staticmethod
    def _diagnostics_for(host):
        return getattr(host, "_diagnostics", None) or DiagnosticsController(host)

    @Slot(result=bool)
    def exportDiagnostics(self):
        return HaizFlowController._diagnostics_for(self).export()

    @Slot(str, result=bool)
    def importVideo(self, path):
        return HaizFlowController._project_import_for(self).import_video(path)

    @Slot()
    def browseBatchVideos(self):
        HaizFlowController._project_import_for(self).browse_batch_videos()

    @Slot()
    def browseBatchFolder(self):
        HaizFlowController._project_import_for(self).browse_batch_folder()

    @Slot("QVariantList")
    def importBatchVideos(self, paths):
        HaizFlowController._project_import_for(self).import_batch_videos(paths)

    def _batch_rejection_message(self, rejected) -> str:
        return HaizFlowController._project_import_for(self).batch_rejection_message(rejected)

    @staticmethod
    def _project_commands_for(host):
        return getattr(host, "_project_commands", None) or ProjectCommandsController(
            host, create_video=create_desktop_video
        )

    @staticmethod
    def _project_import_for(host):
        return getattr(host, "_project_import", None) or ProjectImportController(
            host, create_video=create_desktop_video
        )

    @staticmethod
    def _catalog_media_for(host):
        return getattr(host, "_catalog_media", None) or CatalogMediaController(host)

    @staticmethod
    def _runtime_device_for(host):
        return getattr(host, "_runtime_device", None) or RuntimeDeviceController(
            host,
            unsubscribe=unsubscribe_log,
            pause=pause_video,
            shutdown_translation=shutdown_hymt2_worker,
            detect_hardware=detect_hardware_capabilities,
        )

    @Slot()
    def startBatch(self):
        HaizFlowController._project_commands_for(self).start_batch()

    @Slot()
    def resumeBatch(self):
        HaizFlowController._project_commands_for(self).resume_batch()

    def _batch_settings_values(self) -> dict[str, object]:
        return HaizFlowController._project_commands_for(self).batch_settings_values()

    @Slot(result="QVariantMap")
    def batchSettings(self):
        """Return a batch draft without mutating shared editor state."""
        return self._batch_settings_values()

    @Slot(result="QVariantList")
    def batchSettingOverrides(self):
        return HaizFlowController._project_commands_for(self).batch_setting_overrides()

    def _apply_batch_settings(
        self,
        workflow_mode: str,
        target_language: str,
        tts_voice: str,
        enable_audio_separation: bool,
        original_volume: int,
        background_music_volume=None,
        tts_volume=None,
        watermark_text=None,
        background_music_path=None,
        remove_original_subtitles=None,
        subtitle_style=None,
    ) -> bool:
        return HaizFlowController._project_commands_for(self).apply_batch_settings(
            workflow_mode, target_language, tts_voice, enable_audio_separation, original_volume,
            background_music_volume, tts_volume, watermark_text, background_music_path,
            remove_original_subtitles, subtitle_style,
        )

    @Slot(result=bool)
    def applyBatchSettings(self):
        return self._apply_batch_settings(
            self._workflow_mode,
            self._target_language,
            self._tts_voice,
            self._enable_audio_separation,
            self._original_volume,
            self._background_music_volume,
            self._tts_volume,
            self._watermark_text,
            None,
            self._remove_original_subtitles,
            self._subtitle_style.model_dump(),
        )

    @Slot(str, str, str, bool, int, int, int, str, str, bool, "QVariantMap", result=bool)
    def applyBatchSettingsDraft(
        self,
        workflow_mode: str,
        target_language: str,
        tts_voice: str,
        enable_audio_separation: bool,
        original_volume: int,
        background_music_volume: int | None = None,
        tts_volume: int | None = None,
        watermark_text: str | None = None,
        background_music_path: str | None = None,
        remove_original_subtitles: bool | None = None,
        subtitle_style=None,
    ):
        return self._apply_batch_settings(
            workflow_mode,
            target_language,
            tts_voice,
            enable_audio_separation,
            original_volume,
            background_music_volume,
            tts_volume,
            watermark_text,
            background_music_path,
            remove_original_subtitles,
            subtitle_style,
        )

    @Slot()
    def loadBatchSettings(self):
        HaizFlowController._project_commands_for(self).load_batch_settings()

    @Slot(result=bool)
    def saveSelectedVideoSettings(self):
        return HaizFlowController._project_commands_for(self).save_selected_video_settings()

    @Slot(result=bool)
    def persistSelectedBatchVideoSettings(self):
        """Backward-compatible alias for QML built before single-video autosave."""
        return HaizFlowController._project_commands_for(self).persist_selected_video_settings()

    @Slot(result=bool)
    def persistSelectedVideoSettings(self):
        """Persist setup edits for the selected single or batch video."""
        return HaizFlowController._project_commands_for(self).persist_selected_video_settings()

    @Slot()
    def stopBatch(self):
        HaizFlowController._project_commands_for(self).stop_batch()

    @Slot()
    def clearBatch(self):
        HaizFlowController._project_commands_for(self).clear_batch()

    @staticmethod
    def _batch_output_directory(video):
        """Return only the app-owned per-video output directory, if it is safe to remove."""
        project_directory = (video.project_directory or "").strip()
        output_path = (video.files or {}).get("final_video", "")
        if not project_directory or not output_path:
            return ""
        project_root = (
            project_store.project_root_for_key(video.project_key)
            if getattr(video, "project_key", "")
            else project_store.project_root(video.project_name, project_directory, video.project_type)
        )
        export_roots = (
            os.path.abspath(
                project_store.project_exports_dir_for_key(video.project_key)
                if getattr(video, "project_key", "")
                else project_store.project_exports_dir(video.project_name, project_directory, video.project_type)
            ),
            os.path.abspath(os.path.join(project_root, "outputs")),
        )
        output_directory = os.path.abspath(os.path.dirname(output_path))
        try:
            if not any(os.path.commonpath([exports_root, output_directory]) == exports_root for exports_root in export_roots):
                return ""
        except ValueError:
            return ""
        return output_directory

    @staticmethod
    def _remove_empty_batch_output_parents(video):
        output_directory = HaizFlowController._batch_output_directory(video)
        if not output_directory:
            return
        outputs_root = os.path.dirname(output_directory)
        project_root = os.path.dirname(outputs_root)
        for directory in (outputs_root, project_root):
            try:
                os.rmdir(directory)
            except OSError:
                # Keep non-empty folders and any folder currently in use.
                pass

    @Slot()
    def deleteCurrentBatch(self):
        HaizFlowController._project_commands_for(self).delete_current_batch()

    @Slot()
    def startVideo(self):
        HaizFlowController._project_commands_for(self).start_video()

    @Slot(result=bool)
    def startProjectVideo(self):
        return HaizFlowController._project_commands_for(self).start_project_video()

    @Slot()
    def stopVideo(self):
        HaizFlowController._project_commands_for(self).stop_video()

    @Slot()
    def resumeSelectedVideo(self):
        HaizFlowController._project_commands_for(self).resume_selected_video()

    @Slot()
    def restartSelectedVideo(self):
        HaizFlowController._project_commands_for(self).restart_selected_video()

    @Slot(str)
    def approveTranslationReview(self, payload):
        HaizFlowController._project_commands_for(self).approve_translation_review(payload)

    @Slot(int)
    def selectVideo(self, row: int):
        video = self.videos.video_at(row)
        if not video:
            return
        self._select_video(video)

    def _select_video(self, video):
        HaizFlowController._project_workspace_for(self).select_video(video)

    @Slot(int)
    def selectBatchVideo(self, row: int):
        video = self.batch_videos.video_at(row)
        if not video:
            return
        self._select_video(video)

    @Slot(int)
    def selectProject(self, row: int):
        project = self.projects.project_at(row)
        if not project:
            return
        self._open_project_summary(project)

    @Slot(int, str, result=bool)
    def selectProjectInMode(self, row: int, project_type: str):
        model = (
            self.batch_projects if project_type == "batch"
            else self.download_projects if project_type == "download"
            else self.publish_projects if project_type == "publish"
            else self.single_projects
        )
        project = model.project_at(row)
        if not project:
            return False
        if not self._tiktok_publisher.can_switch_project(project["key"]):
            QMessageBox.information(
                None,
                "Social publishing",
                "Wait for the active Zernio upload or request to finish before opening another project.",
            )
            return False
        if (
            project_type == "download"
            and not self._media_downloader.can_switch_project(project["key"])
        ):
            QMessageBox.information(
                None,
                "Download project",
                "Wait for the current channel task to finish or cancel it before opening another download project.",
            )
            return False
        self._open_project_summary(project)
        return True

    def _open_project_summary(self, project):
        HaizFlowController._project_workspace_for(self).open_project_summary(project)

    @staticmethod
    def _project_workspace_for(host):
        return getattr(host, "_project_workspace", None) or ProjectWorkspaceController(host)

    @Slot()
    def deleteSelectedVideo(self):
        HaizFlowController._project_commands_for(self).delete_selected_video()

    @Slot()
    def openProjectFolder(self):
        if not self.hasOpenProject:
            QMessageBox.information(None, "Project folder", "This project's folder is not available yet.")
            return
        self._open_path(
            self._selected_project_root()
        )

    @Slot()
    def openDownloadOutputFolder(self):
        if self._project_type != "download" or not self.hasOpenProject:
            QMessageBox.information(None, "Download folder", "Open a download project first.")
            return
        self._open_path(project_store.project_downloads_dir_for_key(self._selected_project_key))

    @Slot()
    def browseTikTokPublishVideos(self):
        self._tiktok_publisher.browse_videos()

    @Slot()
    def browseTikTokPublishFolder(self):
        self._tiktok_publisher.browse_folder()

    @Slot()
    def refreshTikTokProjectSources(self):
        self._tiktok_publisher.refresh_project_sources()

    @Slot(int, bool, result=bool)
    def setTikTokProjectSourceSelected(self, row: int, selected: bool):
        return self._tiktok_publisher.set_project_source_selected(row, selected)

    @Slot(result=bool)
    def addSelectedTikTokProjectVideos(self):
        return self._tiktok_publisher.add_selected_project_videos()

    @Slot("QVariantList", result=bool)
    def addTikTokPublishVideos(self, paths):
        return self._tiktok_publisher.add_videos(paths)

    @Slot(str, str, bool, result=bool)
    def saveTikTokPublishDefaults(self, caption: str, hashtags: str, apply_to_existing: bool):
        return self._tiktok_publisher.save_defaults(caption, hashtags, apply_to_existing)

    @Slot(int, str, str, result=bool)
    def updateTikTokPublishItem(self, row: int, caption: str, hashtags: str):
        return self._tiktok_publisher.update_item(row, caption, hashtags)

    @Slot(str, result=bool)
    def saveZernioApiKey(self, api_key: str):
        return self._tiktok_publisher.save_api_key(api_key)

    @Slot(result=bool)
    def clearZernioApiKey(self):
        return self._tiktok_publisher.clear_api_key()

    @Slot(result=bool)
    def connectZernioTikTok(self):
        return self._tiktok_publisher.connect_tiktok()

    @Slot(str, result=bool)
    def connectZernioPlatform(self, platform: str):
        return self._tiktok_publisher.connect_platform(platform)

    @Slot(result=bool)
    def openZernioSignUp(self):
        return self._tiktok_publisher.open_zernio_sign_up()

    @Slot(result=bool)
    def openZernioSignIn(self):
        return self._tiktok_publisher.open_zernio_sign_in()

    @Slot(result=bool)
    def openZernioApiKeys(self):
        return self._tiktok_publisher.open_zernio_api_keys()

    @Slot(result=bool)
    def openZernioPostingDocs(self):
        return self._tiktok_publisher.open_zernio_posting_docs()

    @Slot(result=bool)
    def openZernioDashboard(self):
        return self._tiktok_publisher.open_zernio_dashboard()

    @Slot(result=bool)
    def refreshZernioTikTokAccounts(self):
        return self._tiktok_publisher.refresh_accounts()

    @Slot(result=bool)
    def refreshZernioConnections(self):
        return self._tiktok_publisher.refresh_accounts()

    @Slot(result=bool)
    def reconcileZernioConnections(self):
        return self._tiktok_publisher.reconcile_accounts()

    @Slot(int, result=bool)
    def selectZernioTikTokAccount(self, index: int):
        return self._tiktok_publisher.select_account(index)

    @Slot(int, result=bool)
    def selectZernioConnection(self, index: int):
        return self._tiktok_publisher.select_account(index)

    @Slot(int, result=bool)
    def disconnectZernioConnection(self, index: int):
        return self._tiktok_publisher.disconnect_account(index)

    @Slot(str, bool, bool, bool, bool, bool, bool, str, result=bool)
    def saveZernioPublishSettings(
        self,
        privacy_level: str,
        publish_now: bool,
        allow_comment: bool,
        allow_duet: bool,
        allow_stitch: bool,
        share_to_feed: bool,
        ai_generated: bool,
        first_comment: str,
    ):
        return self._tiktok_publisher.set_publish_settings(
            privacy_level,
            publish_now,
            allow_comment,
            allow_duet,
            allow_stitch,
            share_to_feed,
            ai_generated,
            first_comment,
        )

    @Slot(bool)
    def setZernioPublishConsent(self, confirmed: bool):
        self._tiktok_publisher.set_consent_confirmed(confirmed)

    @Slot(int, result=bool)
    def publishTikTokItem(self, row: int):
        return self._tiktok_publisher.publish_item(row)

    @Slot(result=bool)
    def publishNextTikTokItem(self):
        return self._tiktok_publisher.publish_next()

    @Slot(result=bool)
    def publishAllTikTokItems(self):
        return self._tiktok_publisher.publish_all()

    @Slot(result=bool)
    def refreshTikTokPostStatuses(self):
        return self._tiktok_publisher.refresh_post_statuses()

    @Slot()
    def cancelTikTokPublishing(self):
        self._tiktok_publisher.cancel()

    @Slot(int, result=bool)
    def copyTikTokPublishCaption(self, row: int):
        return self._tiktok_publisher.copy_caption(row)

    @Slot(int, result=bool)
    def openTikTokPublishedPost(self, row: int):
        return self._tiktok_publisher.open_post(row)

    @Slot(int, result=bool)
    def removeTikTokPublishItem(self, row: int):
        return self._tiktok_publisher.remove_item(row)

    @Slot(str, result=bool)
    def openExternalUrl(self, url: str) -> bool:
        return open_external_url(url)

    @Slot(str)
    def copyText(self, text: str) -> None:
        QGuiApplication.clipboard().setText(str(text or ""))

    @Slot()
    def deleteCurrentProject(self):
        HaizFlowController._project_commands_for(self).delete_current_project()

    @Slot()
    def refreshVideos(self):
        HaizFlowController._project_workspace_for(self).refresh_videos()

    def _apply_video_metadata_changes(self, video_ids: set[str]) -> bool:
        return HaizFlowController._project_workspace_for(self).apply_video_metadata_changes(video_ids)

    @staticmethod
    def _thumbnail_retry_signature(source_path: str) -> str:
        return CatalogMediaController.thumbnail_retry_signature(source_path)

    def _missing_thumbnail_ids(self, videos) -> list[str]:
        return HaizFlowController._catalog_media_for(self).missing_thumbnail_ids(videos)

    def _record_thumbnail_failure(self, video_id: str, signature: str) -> None:
        HaizFlowController._catalog_media_for(self).record_thumbnail_failure(video_id, signature)

    def _clear_thumbnail_failure(self, video_id: str) -> None:
        HaizFlowController._catalog_media_for(self).clear_thumbnail_failure(video_id)

    def _create_missing_thumbnails(self, video_ids):
        HaizFlowController._catalog_media_for(self).create_missing_thumbnails(video_ids)

    @Slot()
    def openInputFile(self):
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        input_path = self._resolve_video_file(video, ("video_input", "input_video"), ("input", "video.mp4"))
        if not input_path or not os.path.exists(input_path):
            QMessageBox.information(None, "Open input video", "Input video is not available yet.")
            return
        self._open_path(input_path)

    @Slot()
    def openOutputFile(self):
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        if not video or video.status != "done":
            QMessageBox.information(None, "Open output", "Final video is not available yet.")
            return
        output_path = self._resolve_video_file(video, ("final_video", "output_video"), ("output", "final.mp4"))
        if not output_path or not os.path.exists(output_path):
            QMessageBox.information(None, "Open output", "Final video is not available yet.")
            return
        self._open_path(output_path)

    @Slot()
    def openOutputFolder(self):
        video = video_store.get_video(self._selected_video_id) if self._selected_video_id else None
        if video and migrate_legacy_single_export(video):
            video = video_store.get_video(video.video_id) or video
        output_path = self._resolve_video_file(video, ("final_video", "output_video"), ("output", "final.mp4"))
        folder = os.path.dirname(output_path) if output_path else ""
        fallback_folder = os.path.join(video_store.get_video_dir(video.video_id), "output") if video else ""
        if folder and os.path.isdir(folder):
            self._open_path(folder)
            return
        if fallback_folder and os.path.isdir(fallback_folder):
            self._open_path(fallback_folder)
            return
        if self.hasOpenProject:
            export_folder = project_store.project_exports_dir_for_key(self._selected_project_key)
            os.makedirs(export_folder, exist_ok=True)
            self._open_path(export_folder)
            return
        QMessageBox.information(None, "Open export folder", "The export folder is not available yet.")

    @Slot()
    def openVideoFolder(self):
        if self._selected_video_id:
            self._open_path(video_store.get_video_dir(self._selected_video_id))

    def poll_videos(self):
        revision = video_store.metadata_revision()
        if revision == self._last_video_metadata_revision:
            return
        if not hasattr(self, "_apply_video_metadata_changes"):
            self.refreshVideos()
            self._last_video_metadata_revision = revision
            self.batchChanged.emit()
            return
        changes = video_store.metadata_changes_since(self._last_video_metadata_revision)
        if changes is None:
            self.refreshVideos()
        else:
            revision, video_ids = changes
            if not self._apply_video_metadata_changes(video_ids):
                self.refreshVideos()
            else:
                self._last_video_metadata_revision = revision
        self.batchChanged.emit()

    def _build_config(self):
        manual_subtitle_layout = bool(
            self._subtitle_layout_override and not self._remove_original_subtitles
        )
        return VideoConfig(
            mode=self._workflow_mode,
            source_language="auto",
            target_language=self._target_language,
            translator_provider="hymt2",
            tts_voice=self._tts_voice,
            subtitle_style=self._subtitle_style,
            subtitle_layout_override=manual_subtitle_layout,
            remove_original_subtitles=self._remove_original_subtitles,
            output_format="keep_ratio",
            crop=CropSettings(),
            enable_audio_separation=self._enable_audio_separation,
            original_video_volume=self._original_volume,
            background_music_volume=self._background_music_volume,
            tts_volume=self._tts_volume,
            watermark_text=self._watermark_text,
            background_music_path=self._background_music_path,
            project_name=self._project_name,
            project_directory=self._project_directory,
            project_type=self._project_type,
            project_key=self._selected_project_key,
            project_id=str((project_store.get_project(self._selected_project_key) or {}).get("project_id") or ""),
        )

    def _apply_setup_to_video(self, video, review_approved=None):
        config = self._build_config()
        changes = {
            "mode": config.mode,
            "source_language": config.source_language,
            "target_language": config.target_language,
            "tts_voice": config.tts_voice,
            "subtitle_style": config.subtitle_style,
            "subtitle_layout_override": config.subtitle_layout_override,
            "remove_original_subtitles": config.remove_original_subtitles,
            "output_format": config.output_format,
            "crop": config.crop,
            "enable_audio_separation": config.enable_audio_separation,
            "original_video_volume": config.original_video_volume,
            "background_music_volume": config.background_music_volume,
            "tts_volume": config.tts_volume,
            "watermark_text": config.watermark_text,
            "project_type": config.project_type,
        }
        if review_approved is not None:
            changes["review_approved"] = review_approved
        video_store.update_video(video.video_id, **changes)

    @staticmethod
    def _processing_delegate_for(host):
        return getattr(host, "_processing_lifecycle", None) or ProcessingLifecycleController(host)

    def _enqueue_video(self, video_id: str) -> bool:
        return HaizFlowController._processing_delegate_for(self).enqueue_video(video_id)

    def _enqueue_videos(self, video_ids) -> int:
        return HaizFlowController._processing_delegate_for(self).enqueue_videos(video_ids)

    def _update_queue_positions(self) -> None:
        HaizFlowController._processing_delegate_for(self).update_queue_positions()

    def _on_queue_video_started(self, video_id: str) -> None:
        HaizFlowController._processing_delegate_for(self).on_queue_video_started(video_id)

    def _on_queue_video_finished(self, video_id: str) -> None:
        HaizFlowController._processing_delegate_for(self).on_queue_video_finished(video_id)

    def _on_processing_queue_idle(self) -> None:
        HaizFlowController._processing_delegate_for(self).on_processing_queue_idle()

    def _on_processing_queue_error(self, video_id: str, exc: Exception) -> None:
        HaizFlowController._processing_delegate_for(self).on_processing_queue_error(video_id, exc)

    def _execute_pipeline(self, video_id):
        HaizFlowController._processing_delegate_for(self).execute_pipeline(video_id)

    def _prepare_batch_models(self, video_id):
        HaizFlowController._processing_delegate_for(self).prepare_batch_models(video_id)

    def _on_video_log(self, video_id, line):
        HaizFlowController._processing_delegate_for(self).on_video_log(video_id, line)

    def _drain_log_queue(self):
        HaizFlowController._processing_delegate_for(self).drain_log_queue()

    def _read_video_logs(self, video_id):
        return HaizFlowController._processing_delegate_for(self).read_video_logs(video_id)

    def _replace_logs(self, text: str) -> None:
        HaizFlowController._processing_delegate_for(self).replace_logs(text)

    def _clear_logs(self) -> None:
        HaizFlowController._processing_delegate_for(self).clear_logs()

    def _append_logs(self, lines) -> bool:
        return HaizFlowController._processing_delegate_for(self).append_logs(lines)

    def _refresh_batch_model(self):
        HaizFlowController._catalog_media_for(self).refresh_batch_model()

    def _ensure_video_dimensions(self, video):
        return HaizFlowController._catalog_media_for(self).ensure_video_dimensions(video)

    def _on_video_dimensions_ready(self, video_id: str, width: int, height: int) -> None:
        HaizFlowController._catalog_media_for(self).on_video_dimensions_ready(video_id, width, height)

    _build_project_summaries = staticmethod(build_project_summaries)
    _normalize_video_path = staticmethod(normalize_video_path)
    _collect_batch_video_paths = staticmethod(collect_batch_video_paths)
    _resolve_video_file = staticmethod(resolve_video_file)

    def _language_label(self, code):
        return language_label(code, self._settings_language)

    _format_duration = staticmethod(format_duration)
    _format_memory_size = staticmethod(format_memory_size)

    def _voice_options_for_language(self, language_code):
        return voice_options_for_language(language_code, self._settings_language)

    def _voice_codes_for_language(self, language_code):
        return [item["voice"] for item in self._voice_options_for_language(language_code)]

    def _normalized_voice_for_language(self, language_code, voice):
        """Return a valid Edge voice for the selected output language."""
        options = self._voice_options_for_language(language_code)
        supported_voices = [item["voice"] for item in options]
        if voice in supported_voices:
            return voice
        return supported_voices[0] if supported_voices else ""

    def _draft_thumbnail_path(self) -> str:
        return self._preview_media.draft_thumbnail_path()

    @staticmethod
    def _video_thumbnail_path(video_id: str) -> str:
        return os.path.join(video_store.get_video_dir(video_id), "thumbnail.jpg")

    def _assign_project_thumbnail(self, video) -> None:
        self._preview_media.assign_project_thumbnail(video)

    @staticmethod
    def _create_video_thumbnail(path: str, output_path: str = "") -> str:
        output_path = HaizFlowController._create_video_thumbnail_path(path, output_path)
        return thumbnail_source(output_path)

    _create_video_thumbnail_path = staticmethod(create_video_thumbnail_path)

    def _migrate_legacy_project_thumbnails(self) -> None:
        self._preview_media.migrate_legacy_project_thumbnails()

    _open_path = staticmethod(open_path)

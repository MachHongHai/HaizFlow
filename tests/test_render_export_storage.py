"""Real filesystem regression tests for the render/export ownership boundary."""

import ctypes
import errno
import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from haizflow.core.storage_ownership import owned_path, safe_tree
from haizflow.desktop.video_export_controller import VideoExportController
from haizflow.schemas.video import VIDEO_METADATA_SCHEMA_VERSION, VideoConfig
from haizflow.services import desktop_settings, manual_artifacts, project_store, video_export, video_store


class _Host(QObject):
    exportStateChanged = Signal()
    videoExportCompleted = Signal(str, str)
    appAlertRequested = Signal(str, str, str)
    batchChanged = Signal()

    def __init__(self):
        super().__init__()
        self._settings_language = "vi"
        self._processing_queue = SimpleNamespace(contains=lambda _identifier: False)
        self._selected_video_id = ""
        self._batch_video_ids = []
        self._selected_project_key = ""
        self._enqueue_videos = Mock(return_value=1)
        self.refreshVideos = Mock()
        self.runManualTool = Mock(return_value=False)
        self._enqueue_video = Mock(return_value=False)


class RenderExportStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.qt_application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="haizflow-export-test-")
        self.root = Path(self.temporary.name)
        self.external = self.root / "Thành phẩm"
        self.external.mkdir()
        self.patches = [
            patch.object(project_store, "PROJECT_INDEX_PATH", str(self.root / "runtime" / "projects.json")),
            patch.object(video_store, "LEGACY_VIDEO_WORKSPACES_DIR", str(self.root / "legacy")),
            patch.object(desktop_settings, "SETTINGS_PATH", self.root / "settings.json"),
            patch.dict(video_store._VIDEO_DIR_CACHE, {}, clear=True),
            patch.dict(video_store._VIDEO_METADATA_CACHE, {}, clear=True),
            patch.dict(manual_artifacts._VALIDATED_DIGESTS, {}, clear=True),
            patch.dict(manual_artifacts._RUNTIME_PINS, {}, clear=True),
        ]
        for item in self.patches:
            item.start()
        self.host = _Host()
        self.exporter = VideoExportController(self.host)

    def tearDown(self):
        self.exporter.shutdown()
        # A previous Qt fixture may still drain background index reads. Swap
        # paths only after those metadata handles have been closed.
        with project_store._INDEX_LOCK:
            for item in reversed(self.patches):
                item.stop()
            self.temporary.cleanup()

    def make_video(self, *, kind="single", name="Dự án", content=b"managed-render"):
        directory = self.root / "projects"
        project = project_store.create_project(name, str(directory), kind)
        config = VideoConfig(project_name=name, project_directory=str(directory), project_key=project["key"],
                             project_id=project["project_id"], project_type=kind)
        video = video_store.create_video(str(uuid.uuid4()), "Video nguồn.mp4", config)
        Path(video.files["video_input"]).write_bytes(b"owned-source")
        video = video_store.update_video(video.video_id, status="done", checkpoints={"render": "completed-render"})
        revision = video_export.render_revision(video)
        staging = manual_artifacts.create_staging_directory(video.video_id, "export")
        (staging / "video.mp4").write_bytes(content)
        record = manual_artifacts.publish(video.video_id, "export", revision, staging, {"video": "video.mp4"}, config_fingerprint=revision)
        files = dict(video.files, final_video=record["resolved_outputs"]["video"])
        return project, video_store.update_video(video.video_id, files=files)

    def test_external_move_rename_edit_and_delete_do_not_affect_render_or_checkpoint(self):
        _project, video = self.make_video()
        checkpoint = dict(video.checkpoints)
        source = Path(video_export.render_path(video, verify=True))
        destination = self.external / "Dự án.mp4"
        video_export.export_video(video, destination)
        renamed = destination.with_name("Đã đổi tên.mp4")
        destination.rename(renamed)
        moved = self.root / "moved.mp4"
        renamed.rename(moved)
        moved.write_bytes(b"user-edited")
        moved.unlink()
        self.assertEqual(source.read_bytes(), b"managed-render")
        refreshed = video_store.get_video(video.video_id)
        self.assertEqual(refreshed.status, "done")
        self.assertEqual(refreshed.checkpoints, checkpoint)
        self.assertIsNotNone(video_export.current_render(refreshed))
        video_export.export_video(refreshed, destination)
        self.assertEqual(destination.read_bytes(), source.read_bytes())
        self.assertEqual(len(video_store.get_video(video.video_id).export_history), 2)

    def test_no_overwrite_without_confirmation(self):
        _, video = self.make_video()
        target = self.external / "old.mp4"
        target.write_bytes(b"old")
        with self.assertRaises(FileExistsError):
            video_export.export_video(video, target)
        self.assertEqual(target.read_bytes(), b"old")

    def test_confirmed_destination_changed_during_copy_is_not_replaced(self):
        _, video = self.make_video()
        target = self.external / "changed.mp4"
        target.write_bytes(b"old")
        def changed(_value):
            target.write_bytes(b"another applications update")
        with self.assertRaises(FileExistsError):
            video_export.export_video(video, target, overwrite=True, progress=changed)
        self.assertEqual(target.read_bytes(), b"another applications update")
        self.assertEqual(list(self.external.glob(".haizflow-export-*")), [])

    def test_source_tampering_with_preserved_mtime_fails_checksum(self):
        _, video = self.make_video(content=b"a" * (3 * 1024**2))
        source = Path(video.files["final_video"])
        video_export.current_render(video)  # Populate the fast validation cache.
        info = source.stat()
        with source.open("r+b") as handle:
            handle.seek(2 * 1024**2)
            handle.write(b"b" * 1024)
        os.utime(source, ns=(info.st_atime_ns, info.st_mtime_ns))
        with self.assertRaises(OSError):
            video_export.export_video(video, self.external / "tampered.mp4")
        self.assertFalse((self.external / "tampered.mp4").exists())

    def test_locked_inactive_cache_retains_manifest_for_later_cleanup(self):
        _, video = self.make_video()
        staging = manual_artifacts.create_staging_directory(video.video_id, "export")
        (staging / "video.mp4").write_bytes(b"old-cache")
        manual_artifacts.publish(video.video_id, "export", "old-version", staging, {"video": "video.mp4"}, activate_artifact=False)
        with patch.object(manual_artifacts.shutil, "rmtree", return_value=None):
            manual_artifacts.prune(video.video_id, limit_bytes=0)
        self.assertIn("export:old-version", manual_artifacts.load_manifest(video.video_id)["artifacts"])
        manual_artifacts.prune(video.video_id, limit_bytes=0)
        self.assertNotIn("export:old-version", manual_artifacts.load_manifest(video.video_id)["artifacts"])

    def test_rename_index_failure_preserves_canonical_name(self):
        project, _video = self.make_video()
        with patch.object(project_store, "_save_index", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                project_store.rename_project_by_key(project["key"], "New name")
        self.assertEqual(project_store.get_project(project["key"])["project_name"], project["project_name"])

    def test_rename_manifest_failure_is_repaired_from_committed_index(self):
        project, _video = self.make_video()
        original = project_store._write_json_atomic
        def fail_mirror(path, value):
            if Path(path).name == project_store.PROJECT_MANIFEST_NAME:
                raise PermissionError("manifest temporarily locked")
            return original(path, value)
        with patch.object(project_store, "_write_json_atomic", side_effect=fail_mirror):
            project_store.rename_project_by_key(project["key"], "New name")
        self.assertEqual(project_store.get_project(project["key"])["project_name"], "New name")
        manifest = Path(project["project_root"]) / project_store.PROJECT_MANIFEST_NAME
        self.assertEqual(json.loads(manifest.read_text(encoding="utf-8"))["project_name"], "New name")

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "Real FFmpeg integration needs installed binaries")
    def test_real_mp4_quality_copy_keeps_stereo_48khz_and_does_not_upscale(self):
        from haizflow.pipeline.sequence_compiler import finish_export_resolution
        from haizflow.utils.ffmpeg import validate_video_integrity

        _project, video = self.make_video()
        working = video_export.export_destination(video)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        "color=c=blue:s=320x180:d=0.6", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=0.6",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ac", "2", "-ar", "48000",
                        "-shortest", str(working)], check=True, capture_output=True, timeout=30)
        scaled = working.with_name("quality-test.mp4")
        finish_export_resolution(str(working), str(scaled), "1080p-high", video.video_id)
        validate_video_integrity(str(scaled))
        video = video_store.update_video(video.video_id, active_artifacts={}, checkpoints={"render": "real-render"})
        revision = video_export.render_revision(video)
        record = manual_artifacts.register_existing(video.video_id, "export", revision, {"video": str(scaled)}, config_fingerprint=revision)
        video = video_store.get_video(video.video_id)
        target = self.external / "Real video.mp4"
        video_export.export_video(video, target)
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(target)],
                               check=True, capture_output=True, text=True, timeout=20)
        streams = json.loads(probe.stdout)["streams"]
        picture = next(stream for stream in streams if stream["codec_type"] == "video")
        audio = next(stream for stream in streams if stream["codec_type"] == "audio")
        self.assertEqual((picture["width"], picture["height"]), (320, 180))
        self.assertEqual((audio["channels"], audio["sample_rate"]), (2, "48000"))
        self.assertEqual(target.read_bytes(), Path(record["resolved_outputs"]["video"]).read_bytes())

    @unittest.skipUnless(os.name == "nt" and Path("D:/").is_dir() and Path("C:/").is_dir(), "Cross-volume Windows integration")
    def test_project_on_d_drive_exports_to_c_drive(self):
        with tempfile.TemporaryDirectory(prefix="haizflow-cross-drive-", dir=Path.cwd() / "build") as directory:
            self.assertEqual(Path(directory).drive.casefold(), "d:")
            if self.external.drive.casefold() != "c:":
                self.skipTest("Cross-volume test requires TEMP on C: and workspace on D:")
            project = project_store.create_project("Cross drive", directory, "single")
            config = VideoConfig(project_name=project["project_name"], project_directory=directory, project_key=project["key"],
                                 project_id=project["project_id"], project_type="single")
            video = video_store.create_video(str(uuid.uuid4()), "source.mp4", config)
            Path(video.files["video_input"]).write_bytes(b"source")
            video = video_store.update_video(video.video_id, status="done", checkpoints={"render": "rendered"})
            revision = video_export.render_revision(video)
            staging = manual_artifacts.create_staging_directory(video.video_id, "export")
            (staging / "video.mp4").write_bytes(b"cross-drive-render")
            manual_artifacts.publish(video.video_id, "export", revision, staging, {"video": "video.mp4"}, config_fingerprint=revision)
            video = video_store.get_video(video.video_id)
            target = self.external / "Cross drive.mp4"
            video_export.export_video(video, target)
            self.assertEqual(target.read_bytes(), b"cross-drive-render")
            project_store.delete_project_by_key(project["key"])
            self.assertTrue(target.is_file())

    def test_failed_overwrite_preserves_existing_file_and_render(self):
        _, video = self.make_video()
        target = self.external / "old.mp4"
        target.write_bytes(b"old")
        with patch.object(video_export.os, "replace", side_effect=PermissionError("file locked")):
            with self.assertRaises(PermissionError):
                video_export.export_video(video, target, overwrite=True)
        self.assertEqual(target.read_bytes(), b"old")
        self.assertIsNotNone(video_export.current_render(video))
        self.assertEqual(list(self.external.glob("*.partial")), [])
        self.assertEqual(list(self.external.glob(".haizflow-export-*")), [])

    def test_racing_destination_creation_is_not_overwritten(self):
        _, video = self.make_video()
        target = self.external / "race.mp4"

        def create_racer(value):
            if value < 100:
                target.write_bytes(b"another-user-file")

        with self.assertRaises(FileExistsError):
            video_export.export_video(video, target, progress=create_racer)
        self.assertEqual(target.read_bytes(), b"another-user-file")

    def test_cancel_mid_copy_leaves_no_partial_final_and_keeps_old_target(self):
        _, video = self.make_video(content=b"x" * (3 * 1024**2))
        target = self.external / "cancel.mp4"
        target.write_bytes(b"old")
        cancel = threading.Event()
        with self.assertRaises(video_export.ExportCancelled):
            video_export.export_video(video, target, overwrite=True, cancel=cancel, progress=lambda _value: cancel.set())
        self.assertEqual(target.read_bytes(), b"old")
        self.assertEqual(list(self.external.glob(".haizflow-export-*")), [])
        self.assertIsNotNone(video_export.current_render(video))

    def test_full_disk_and_unavailable_destination_are_export_only_failures(self):
        _, video = self.make_video()
        with patch.object(video_export.shutil, "disk_usage", return_value=SimpleNamespace(free=1)):
            with self.assertRaises(OSError) as error:
                video_export.export_video(video, self.external / "full.mp4")
        self.assertEqual(error.exception.errno, errno.ENOSPC)
        with self.assertRaises(FileNotFoundError):
            video_export.export_video(video, self.root / "disconnected" / "out.mp4")
        self.assertEqual(video_store.get_video(video.video_id).status, "done")

    def test_artifact_and_all_project_roots_are_rejected_as_export_destinations(self):
        project, video = self.make_video()
        other = project_store.create_project("Other", str(self.root / "projects"), "manual")
        for target in (video.files["final_video"], Path(project["project_root"]) / "keep.mp4",
                       Path(other["project_root"]) / "keep.mp4"):
            with self.subTest(target=str(target)), self.assertRaises(ValueError):
                video_export.export_video(video, target, overwrite=True)

    def test_missing_or_corrupt_artifact_does_not_destroy_project_metadata(self):
        _, video = self.make_video()
        Path(video.files["final_video"]).write_bytes(b"corrupt")
        self.assertIsNone(video_export.current_render(video))
        with self.assertRaises(FileNotFoundError):
            video_export.export_video(video, self.external / "out.mp4")
        saved = video_store.get_video(video.video_id)
        self.assertEqual(saved.status, "done")
        self.assertTrue(Path(video_store.get_video_json_path(video.video_id)).is_file())

    def test_auto_configuration_change_invalidates_current_render(self):
        _, video = self.make_video()
        changed = video_store.update_video(video.video_id, watermark_text="New watermark")
        self.assertIsNone(video_export.current_render(changed))
        self.assertTrue(Path(video.files["final_video"]).is_file())

    def test_manual_revision_and_quality_invalidate_only_render(self):
        _, video = self.make_video(kind="manual")
        self.assertIsNotNone(video_export.current_render(video))
        changed = video_store.update_video(video.video_id, export_preset="720p")
        self.assertIsNone(video_export.current_render(changed))
        self.assertEqual(changed.checkpoints, video.checkpoints)
        self.assertEqual(changed.editor_document_revision, video.editor_document_revision)

    def test_manual_export_reuses_artifact_without_queue_or_tts(self):
        _, video = self.make_video(kind="manual")
        self.host._selected_video_id = video.video_id
        target = self.external / "manual.mp4"
        self.assertTrue(self.exporter.start(video.video_id, "source", str(target)))
        self.exporter.worker.join(timeout=10)
        self.exporter.poll()
        self.assertEqual(self.exporter.jobs[0]["status"], "done")
        self.host.runManualTool.assert_not_called()
        self.host._enqueue_video.assert_not_called()
        self.assertEqual(target.read_bytes(), b"managed-render")

    def test_batch_files_are_unique_and_retry_only_failed_exports(self):
        _, first = self.make_video(kind="batch")
        _, second = self.make_video(kind="batch")
        self.host._batch_video_ids = [first.video_id, second.video_id]
        seen = []

        def fail_first(video, target, **kwargs):
            seen.append(video.video_id)
            if video.video_id == first.video_id:
                raise OSError(errno.ENOSPC, "full")
            return video_export.export_video(video, target, **kwargs)

        self.exporter.copier = fail_first
        with patch("haizflow.desktop.video_export_controller.QFileDialog.getExistingDirectory", return_value=str(self.external)):
            self.assertTrue(self.exporter.start_batch())
        self.exporter.worker.join(timeout=10)
        self.exporter.poll()
        self.assertEqual([job["status"] for job in self.exporter.jobs], ["failed", "done"])
        self.assertNotEqual(*[job["name"] for job in self.exporter.jobs])
        self.exporter.copier = lambda video, target, **kwargs: (seen.append(video.video_id), video_export.export_video(video, target, **kwargs))[1]
        self.assertTrue(self.exporter.retry_failed())
        self.exporter.worker.join(timeout=10)
        self.exporter.poll()
        self.assertEqual(seen, [first.video_id, second.video_id, first.video_id])
        self.assertEqual([job["status"] for job in self.exporter.jobs], ["done", "done"])
        self.assertEqual(video_store.get_video(first.video_id).status, "done")

    def test_batch_export_skips_unfinished_and_outdated_videos(self):
        _, ready = self.make_video(kind="batch")
        _, pending = self.make_video(kind="batch")
        _, stale = self.make_video(kind="batch")
        video_store.update_video(pending.video_id, status="paused")
        video_store.update_video(stale.video_id, watermark_text="changed")
        self.host._batch_video_ids = [ready.video_id, pending.video_id, stale.video_id]
        with patch("haizflow.desktop.video_export_controller.QFileDialog.getExistingDirectory", return_value=str(self.external)):
            self.assertTrue(self.exporter.start_batch())
        self.exporter.worker.join(timeout=10)
        self.exporter.poll()
        self.assertEqual([job["videoId"] for job in self.exporter.jobs], [ready.video_id])
        self.assertEqual(self.exporter.jobs[0]["status"], "done")
        self.host._enqueue_video.assert_not_called()

    def test_batch_export_without_finished_video_does_not_open_picker(self):
        _, video = self.make_video(kind="batch")
        video_store.update_video(video.video_id, status="pending")
        self.host._batch_video_ids = [video.video_id]
        with patch("haizflow.desktop.video_export_controller.QFileDialog.getExistingDirectory") as choose:
            self.assertFalse(self.exporter.start_batch())
        choose.assert_not_called()

    def test_batch_destination_replacement_requires_confirmation(self):
        from haizflow.desktop.localization import QMessageBox

        _, video = self.make_video(kind="batch")
        self.host._batch_video_ids = [video.video_id]
        target = self.external / video_export.batch_filename(video)
        target.write_bytes(b"existing-export")
        with patch("haizflow.desktop.video_export_controller.QFileDialog.getExistingDirectory", return_value=str(self.external)), \
             patch("haizflow.desktop.video_export_controller.QMessageBox.question", return_value=QMessageBox.StandardButton.No) as confirm:
            self.assertEqual(self.exporter.choose_batch_directory(), "")
        confirm.assert_called_once()
        self.assertNotIn(str(target), self.exporter._chosen_targets)
        self.assertEqual(target.read_bytes(), b"existing-export")

    def test_batch_destination_approval_captures_identity_before_processing(self):
        from haizflow.desktop.localization import QMessageBox

        _, video = self.make_video(kind="batch")
        self.host._batch_video_ids = [video.video_id]
        target = self.external / video_export.batch_filename(video)
        target.write_bytes(b"existing-export")
        identity = video_export.destination_identity(target)
        with patch("haizflow.desktop.video_export_controller.QFileDialog.getExistingDirectory", return_value=str(self.external)), \
             patch("haizflow.desktop.video_export_controller.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            self.assertEqual(self.exporter.choose_batch_directory(), str(self.external.resolve()))
        self.assertEqual(self.exporter._chosen_targets[str(target)], identity)
        self.assertEqual(target.read_bytes(), b"existing-export")

    def test_process_export_waits_for_completed_run_and_preserves_quality(self):
        _, video = self.make_video()
        self.host._selected_video_id = video.video_id
        target = self.external / "processed.mp4"
        with patch("haizflow.desktop.project_commands_controller.ProjectCommandsController.process_for_export", return_value=True) as process:
            self.assertTrue(self.exporter.start(video.video_id, "720p", str(target), process=True))
        process.assert_called_once_with(video.video_id)
        self.assertEqual(video_store.get_video(video.video_id).export_preset, "720p")
        self.assertIsNone(self.exporter.worker)
        self.assertEqual(self.exporter.jobs[0]["status"], "rendering")
        self.assertFalse(target.exists())

    def test_batch_processing_checks_owner_and_destinations_before_enqueue(self):
        project, video = self.make_video(kind="batch")
        self.host._selected_project_key = project["key"]
        self.host._batch_video_ids = [video.video_id]
        with patch("haizflow.desktop.project_commands_controller.ProjectCommandsController._resources_ready_for_videos", return_value=True):
            self.assertFalse(self.exporter.start_batch_to("another-project", [video.video_id], "720p", str(self.external)))
            self.assertFalse(self.exporter.start_batch_to(project["key"], [video.video_id], "720p", str(self.external / "missing")))
            self.host._enqueue_videos.assert_not_called()
            self.assertTrue(self.exporter.start_batch_to(project["key"], [video.video_id], "720p", str(self.external)))
        self.host._enqueue_videos.assert_called_once_with([video.video_id])
        self.assertTrue(self.host._batch_running)
        self.assertEqual(video_store.get_video(video.video_id).export_preset, "720p")
        self.assertEqual(self.exporter.jobs[0]["status"], "rendering")
        self.assertIsNone(self.exporter.worker)

    def test_batch_processing_preflight_failure_keeps_preset_and_status(self):
        project, video = self.make_video(kind="batch")
        self.host._selected_project_key = project["key"]
        self.host._batch_video_ids = [video.video_id]
        with patch("haizflow.desktop.project_commands_controller.ProjectCommandsController._resources_ready_for_videos", return_value=False):
            self.assertFalse(self.exporter.start_batch_to(project["key"], [video.video_id], "720p", str(self.external)))
        self.assertEqual(video_store.get_video(video.video_id).export_preset, "source")
        self.assertEqual(video_store.get_video(video.video_id).status, "done")
        self.assertEqual(self.exporter.jobs, [])

    def test_batch_runtime_pin_preflight_never_clears_another_video(self):
        project, first = self.make_video(kind="batch")
        config = VideoConfig(project_type="batch", project_key=project["key"], project_id=project["project_id"],
                             project_name=project["project_name"], project_directory=project["project_directory"])
        second = video_store.create_video(str(uuid.uuid4()), "second.mp4", config)
        self.host._selected_project_key = project["key"]
        self.host._batch_video_ids = [first.video_id, second.video_id]
        old_render = Path(first.files["final_video"])
        with patch("haizflow.desktop.project_commands_controller.ProjectCommandsController._resources_ready_for_videos", return_value=True), \
             patch.object(manual_artifacts, "has_runtime_pins", side_effect=lambda key: key == second.video_id):
            self.assertFalse(self.exporter.start_batch_to(project["key"], self.host._batch_video_ids, "source", str(self.external)))
        self.assertTrue(old_render.exists())
        self.assertEqual(video_store.get_video(first.video_id).checkpoints, first.checkpoints)
        self.host._enqueue_videos.assert_not_called()

    def test_fresh_batch_discards_temp_and_published_cache_but_keeps_external_export(self):
        project, video = self.make_video(kind="batch")
        external = self.external / "already-exported.mp4"
        video_export.export_video(video, external)
        temp = Path(video.files["transcript_json"]).parent
        (temp / "original_subtitle_region.json").write_text("old OCR", encoding="utf-8")
        (temp / "voice_parts" / "voice_0001.mp3").write_bytes(b"old voice")
        video_store.update_video(video.video_id, status="paused", resume_step="creating_voice", processing_elapsed_seconds=130)
        self.host._selected_project_key = project["key"]
        self.host._batch_video_ids = [video.video_id]
        with patch("haizflow.desktop.project_commands_controller.ProjectCommandsController._resources_ready_for_videos", return_value=True):
            self.assertTrue(self.exporter.start_batch_to(project["key"], self.host._batch_video_ids, "source", str(self.external)))
        fresh = video_store.get_video(video.video_id)
        self.assertEqual(fresh.checkpoints, {})
        self.assertEqual(fresh.resume_step, "")
        self.assertEqual(fresh.processing_elapsed_seconds, 0)
        self.assertEqual(fresh.active_artifacts, {})
        self.assertIsNone(video_export.current_render(fresh))
        self.assertFalse((temp / "original_subtitle_region.json").exists())
        self.assertFalse((temp / "voice_parts" / "voice_0001.mp3").exists())
        self.assertFalse(manual_artifacts.cache_root(video.video_id).exists())
        self.assertEqual(Path(fresh.files["video_input"]).read_bytes(), b"owned-source")
        self.assertEqual(external.read_bytes(), b"managed-render")

    def test_new_job_in_other_project_preserves_paused_export_destination(self):
        _, first = self.make_video()
        _, second = self.make_video(name="Second")
        self.host._selected_video_id = first.video_id
        with patch("haizflow.desktop.project_commands_controller.ProjectCommandsController.process_for_export", return_value=True):
            self.assertTrue(self.exporter.start(first.video_id, "source", str(self.external / "first.mp4"), process=True))
        video_store.update_video(first.video_id, status="paused")
        self.exporter.poll()
        self.assertTrue(self.exporter.start(second.video_id, "source", str(self.external / "second.mp4")))
        self.exporter.worker.join(timeout=10)
        self.exporter.poll()
        self.assertEqual(self.exporter.jobs[0]["videoId"], first.video_id)
        self.assertEqual(self.exporter.jobs[0]["status"], "paused")
        video_store.update_video(first.video_id, status="done")
        self.exporter.poll()
        self.exporter.worker.join(timeout=10)
        self.exporter.poll()
        self.assertEqual((self.external / "first.mp4").read_bytes(), b"managed-render")

    def test_batch_default_is_stable_when_most_videos_are_customized(self):
        from haizflow.services import batch_settings
        project, video = self.make_video(kind="batch")
        original = batch_settings.stable_values(project["key"], {}, [video])
        video = video_store.update_video(video.video_id, target_language="en", background_music_loop=False)
        actual = batch_settings.stable_values(project["key"], {}, [video])
        self.assertEqual(actual, original)
        self.assertEqual(batch_settings.differences(batch_settings.values_for(video), actual),
                         ["targetLanguage", "backgroundMusicLoop"])
        renamed = project_store.rename_project_by_key(project["key"], "Renamed")
        self.assertEqual(renamed["batch_settings"]["values"], original)

    def test_batch_assets_compare_content_not_same_size_or_copied_path(self):
        from haizflow.services import batch_settings
        project, _video = self.make_video(kind="batch")
        first = self.external / "first.wav"
        second = self.external / "second.wav"
        first.write_bytes(b"same-size-A")
        second.write_bytes(b"same-size-B")
        staged = batch_settings.stage_asset(project["key"], "voiceReferencePath", str(first))
        self.assertEqual(batch_settings.differences({"voiceReferencePath": staged}, {"voiceReferencePath": str(first)}), [])
        self.assertEqual(batch_settings.differences({"voiceReferencePath": str(second)}, {"voiceReferencePath": str(first)}), ["voiceReferencePath"])
        first.unlink()
        self.assertEqual(Path(staged).read_bytes(), b"same-size-A")

    def test_batch_config_includes_gemini_music_and_watermark_settings(self):
        from haizflow.services import batch_settings
        config = batch_settings.config_for({
            "translationModel": "gemini-3.1-flash-lite", "backgroundMusicLoop": False,
            "audioDuckingEnabled": True, "audioDuckingReductionDb": -18,
            "watermarkKind": "image", "watermarkImagePath": "watermark.png",
            "watermarkOpacityPercent": 75, "watermarkScalePercent": 120,
            "ttsVoice": "omnivoice:clone", "voiceReferencePath": "sample.wav",
        })
        self.assertEqual(config.translator_provider, "gemini")
        self.assertFalse(config.background_music_loop)
        self.assertTrue(config.audio_ducking_enabled)
        self.assertEqual(config.audio_ducking_reduction_db, -18)
        self.assertEqual(config.watermark_image_path, "watermark.png")
        self.assertEqual(config.voice_reference_path, "sample.wav")
        self.assertEqual(config.watermark_opacity_percent, 75)
        with self.assertRaises(ValueError):
            batch_settings.config_for({"ttsVoice": "omnivoice:clone"})

    def test_shared_batch_apply_preserves_private_video_until_explicit_replace(self):
        from haizflow.desktop.project_commands_controller import ProjectCommandsController
        from haizflow.services import batch_settings
        project, first = self.make_video(kind="batch")
        config = VideoConfig(project_type="batch", project_key=project["key"],
                             project_id=project["project_id"], project_name=project["project_name"],
                             project_directory=project["project_directory"])
        second = video_store.create_video(str(uuid.uuid4()), "second.mp4", config)
        self.host._selected_project_key = project["key"]
        self.host._batch_video_ids = [first.video_id, second.video_id]
        self.host._normalized_tts_provider = lambda language, provider: provider
        self.host._normalized_voice_for_language = lambda language, voice, provider: voice
        self.host._capture_video_asset_snapshot = Mock(return_value={})
        self.host._record_batch_asset_change = Mock()
        self.host._restore_video_asset_snapshot = Mock()
        self.host._show_app_alert = Mock()
        command = ProjectCommandsController(self.host)
        baseline = command.batch_settings_values()
        video_store.update_video(second.video_id, original_video_volume=11)
        changed = dict(baseline, backgroundMusicLoop=False, audioDuckingEnabled=True, originalVolume=42)
        self.assertTrue(command.apply_batch_settings_values(project["key"], changed))
        self.assertEqual(video_store.get_video(first.video_id).original_video_volume, 42)
        self.assertFalse(video_store.get_video(first.video_id).background_music_loop)
        self.assertTrue(video_store.get_video(first.video_id).audio_ducking_enabled)
        self.assertEqual(video_store.get_video(second.video_id).original_video_volume, 11)
        self.assertEqual(command.batch_setting_overrides()[0]["videoId"], second.video_id)
        self.assertEqual(batch_settings.stable_values(project["key"], {}, [second])["originalVolume"], 42)
        self.assertTrue(command.apply_batch_settings_values(project["key"], changed, True))
        self.assertEqual(video_store.get_video(second.video_id).original_video_volume, 42)
        self.assertEqual(command.batch_setting_overrides(), [])
        self.assertFalse(command.apply_batch_settings_values("wrong-owner", changed, True))

    def test_batch_fresh_processing_exports_only_new_renders_for_each_video(self):
        project, first = self.make_video(kind="batch")
        config = VideoConfig(project_type="batch", project_key=project["key"], project_id=project["project_id"],
                             project_name=project["project_name"], project_directory=project["project_directory"])
        second = video_store.create_video(str(uuid.uuid4()), "second.mp4", config)
        self.host._selected_project_key = project["key"]
        self.host._batch_video_ids = [first.video_id, second.video_id]
        with patch("haizflow.desktop.project_commands_controller.ProjectCommandsController._resources_ready_for_videos", return_value=True):
            self.assertTrue(self.exporter.start_batch_to(project["key"], self.host._batch_video_ids, "source", str(self.external)))
        first = video_store.get_video(first.video_id)
        self.assertEqual(first.checkpoints, {})
        self.assertEqual(first.resume_step, "")
        revision = video_export.render_revision(first)
        staging = manual_artifacts.create_staging_directory(first.video_id, "export")
        (staging / "video.mp4").write_bytes(b"first-new-render")
        record = manual_artifacts.publish(first.video_id, "export", revision, staging, {"video": "video.mp4"}, config_fingerprint=revision)
        video_store.update_video(first.video_id, status="done", files=dict(first.files, final_video=record["resolved_outputs"]["video"]))
        video_store.update_video(second.video_id, status="paused")
        self.exporter.poll()
        self.exporter.worker.join(timeout=10)
        self.exporter.poll()
        self.assertEqual(self.exporter.jobs[0]["status"], "done")
        self.assertEqual(self.exporter.jobs[1]["status"], "paused")
        revision = video_export.render_revision(second)
        staging = manual_artifacts.create_staging_directory(second.video_id, "export")
        (staging / "video.mp4").write_bytes(b"second-render")
        record = manual_artifacts.publish(second.video_id, "export", revision, staging, {"video": "video.mp4"}, config_fingerprint=revision)
        video_store.update_video(second.video_id, status="done", files=dict(second.files, final_video=record["resolved_outputs"]["video"]))
        self.exporter.poll()
        self.exporter.worker.join(timeout=10)
        self.exporter.poll()
        self.assertEqual([job["status"] for job in self.exporter.jobs], ["done", "done"])
        self.assertEqual(Path(self.exporter.jobs[1]["path"]).read_bytes(), b"second-render")

    def test_pausing_process_export_never_copies_previous_render(self):
        _, video = self.make_video()
        self.host._selected_video_id = video.video_id
        target = self.external / "paused.mp4"
        with patch("haizflow.desktop.project_commands_controller.ProjectCommandsController.process_for_export", return_value=True):
            self.assertTrue(self.exporter.start(video.video_id, "source", str(target), process=True))
        video_store.update_video(video.video_id, status="paused")
        self.exporter.poll()
        self.assertEqual(self.exporter.jobs[0]["status"], "paused")
        self.assertFalse(self.exporter.busy)
        self.assertFalse(target.exists())
        video_store.update_video(video.video_id, status="done")
        self.exporter.poll()
        self.exporter.worker.join(timeout=10)
        self.exporter.poll()
        self.assertEqual(self.exporter.jobs[0]["status"], "done")
        self.assertEqual(target.read_bytes(), b"managed-render")

    def test_cancelled_waiting_export_does_not_resume_copy(self):
        _, video = self.make_video()
        self.host._selected_video_id = video.video_id
        target = self.external / "cancelled.mp4"
        with patch("haizflow.desktop.project_commands_controller.ProjectCommandsController.process_for_export", return_value=True):
            self.assertTrue(self.exporter.start(video.video_id, "source", str(target), process=True))
        video_store.update_video(video.video_id, status="paused")
        self.exporter.poll()
        self.exporter.cancel_all()
        video_store.update_video(video.video_id, status="done")
        self.exporter.poll()
        self.assertEqual(self.exporter.jobs[0]["status"], "cancelled")
        self.assertFalse(target.exists())

    def test_undrained_copy_events_cannot_be_applied_to_a_new_job(self):
        _, video = self.make_video()
        self.assertTrue(self.exporter.start(video.video_id, "source", str(self.external / "first.mp4")))
        self.exporter.worker.join(timeout=10)
        self.assertTrue(self.exporter.busy)
        self.assertFalse(self.exporter.start(video.video_id, "source", str(self.external / "second.mp4")))
        self.exporter.poll()
        self.assertFalse(self.exporter.busy)

    def test_project_deletion_keeps_external_export_and_shared_resources(self):
        project, video = self.make_video()
        output = self.external / "keep.mp4"
        shared = self.root / "shared-model.bin"
        shared.write_bytes(b"shared")
        video_export.export_video(video, output)
        self.assertTrue(project_store.delete_project_by_key(project["key"]))
        self.assertEqual(output.read_bytes(), b"managed-render")
        self.assertEqual(shared.read_bytes(), b"shared")

    def test_video_deletion_from_batch_keeps_external_export(self):
        _, video = self.make_video(kind="batch")
        output = self.external / "keep.mp4"
        video_export.export_video(video, output)
        self.assertTrue(video_store.delete_video(video.video_id, attempts=1, delay_seconds=0))
        self.assertEqual(output.read_bytes(), b"managed-render")

    def test_pin_protects_render_from_cache_clear_and_project_deletion(self):
        project, video = self.make_video()
        with video_export.render_lease(video):
            manual_artifacts.clear(video.video_id, include_active=True)
            self.assertTrue(Path(video.files["final_video"]).exists())
            with self.assertRaises(RuntimeError):
                project_store.delete_project_by_key(project["key"])
            with self.assertRaises(RuntimeError):
                video_store.delete_video(video.video_id, attempts=1, delay_seconds=0)
        self.assertTrue(project_store.delete_project_by_key(project["key"]))

    def test_prune_keeps_current_render_and_removes_old_revision(self):
        _, video = self.make_video()
        old = manual_artifacts.create_staging_directory(video.video_id, "export")
        (old / "video.mp4").write_bytes(b"old")
        record = manual_artifacts.publish(video.video_id, "export", "old-revision", old, {"video": "video.mp4"}, activate_artifact=False)
        manual_artifacts.prune(video.video_id, limit_bytes=0)
        self.assertFalse(Path(record["resolved_outputs"]["video"]).exists())
        self.assertIsNotNone(video_export.current_render(video))

    def test_rename_keeps_identity_root_video_paths_checkpoint_and_render(self):
        project, video = self.make_video()
        updated = project_store.rename_project_by_key(project["key"], "Tên mới")
        self.assertEqual(updated["project_id"], project["project_id"])
        self.assertEqual(updated["project_root"], project["project_root"])
        self.assertEqual(video_store.get_video(video.video_id).files, video.files)
        self.assertEqual(video_export.export_filename(video_export.project_display_name(video)), "Tên mới.mp4")
        self.assertIsNotNone(video_export.current_render(video_store.get_video(video.video_id)))

    def test_duplicate_project_names_use_distinct_roots(self):
        first = project_store.create_project("Same", str(self.root / "projects"), "single")
        second = project_store.create_project("Same", str(self.root / "projects"), "single")
        self.assertNotEqual(first["key"], second["key"])
        self.assertNotEqual(first["project_root"], second["project_root"])

    def test_unavailable_project_root_is_retained_without_replacement(self):
        project, video = self.make_video()
        root = Path(project["project_root"])
        moved = root.with_name("moved-project")
        root.rename(moved)
        self.assertIsNotNone(project_store.get_project(project["key"]))
        with self.assertRaises((OSError, ValueError)):
            video_store.save_video(video)
        self.assertFalse(root.exists())
        self.assertFalse((self.root / "legacy" / video.video_id).exists())

    def test_change_default_only_affects_new_project_suggestion(self):
        project, _video = self.make_video()
        desktop_settings.save_settings({"default_project_directory": str(self.external)})
        self.assertEqual(project_store.get_project(project["key"])["project_root"], project["project_root"])
        self.assertEqual(desktop_settings.load_settings()["default_project_directory"], str(self.external))

    def test_metadata_schema_upgrade_has_recovery_backup(self):
        _, video = self.make_video()
        path = Path(video_store.get_video_json_path(video.video_id))
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["schema_version"] = 18
        payload.pop("export_history")
        path.write_text(json.dumps(payload), encoding="utf-8")
        video_store._VIDEO_METADATA_CACHE.clear()
        restored = video_store.get_video(video.video_id)
        self.assertEqual(restored.schema_version, VIDEO_METADATA_SCHEMA_VERSION)
        self.assertTrue(Path(str(path) + ".schema-migration.bak").is_file())

    def test_unsafe_artifact_signature_and_path_traversal_are_rejected(self):
        _, video = self.make_video()
        with self.assertRaises(ValueError):
            manual_artifacts.artifact_directory(video.video_id, "export", "../../other-project")
        with self.assertRaises(ValueError):
            owned_path(self.root / "escape.bin", video_store.get_video_dir(video.video_id))
        with self.assertRaises(ValueError):
            video_store.get_video_dir("../../escape")

    @unittest.skipUnless(os.name == "nt", "Windows junction integration")
    def test_windows_junction_cannot_export_into_or_delete_managed_data(self):
        project, video = self.make_video()
        alias = self.external / "redirect"
        subprocess.run(["cmd", "/c", "mklink", "/J", str(alias), project["project_root"]], check=True, capture_output=True)
        try:
            with self.assertRaises(ValueError):
                video_export.export_video(video, alias / "out.mp4")
            with self.assertRaises(ValueError):
                safe_tree(self.external)
        finally:
            os.rmdir(alias)  # Only the verified test junction, never its target.
        self.assertTrue(Path(video.files["final_video"]).is_file())

    @unittest.skipUnless(os.name == "nt", "Windows sharing-lock integration")
    def test_windows_locked_output_preserves_old_file(self):
        _, video = self.make_video()
        target = self.external / "locked.mp4"
        target.write_bytes(b"old-video")
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
                                      ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
        kernel.CreateFileW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.CreateFileW(str(target), 0x80000000, 0, None, 3, 0x80, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        try:
            with self.assertRaises(OSError):
                video_export.export_video(video, target, overwrite=True)
        finally:
            kernel.CloseHandle(handle)
        self.assertEqual(target.read_bytes(), b"old-video")
        self.assertEqual(list(self.external.glob(".haizflow-export-*")), [])

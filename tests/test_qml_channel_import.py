import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QGuiApplication


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
QML_DIR = SRC / "hflow" / "desktop" / "qml"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hflow.desktop.channel_import import ChannelImportCoordinator
from hflow.schemas.channel_import import ChannelImportRequest, ChannelVideoCandidate
from hflow.services.channel_import import new_session
from hflow.services.video_download import DownloadCancelled


class ChannelImportQmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def test_incomplete_scan_is_partial_and_results_survive_project_reopen(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            coordinator = ChannelImportCoordinator()
            request = ChannelImportRequest(url="https://www.douyin.com/user/creator", platform="douyin")
            session = new_session("project:test", temp_dir, request)
            coordinator._sessions[session.session_id] = session
            coordinator._active_session_id = session.session_id
            row = ChannelVideoCandidate(remote_video_id="one", source_url="https://www.douyin.com/video/one",
                                        title="Video", platform="Douyin")
            warning = "Quét chưa hoàn tất: đã quét 22/300 bài đăng."
            coordinator._handle_scan_resolved(session.session_id, {
                "platform": "Douyin", "candidates": [row.model_dump(mode="json")],
                "warning": warning, "scan_progress": 7,
            })
            self.assertEqual(coordinator.state, "partial")
            self.assertFalse(coordinator.busy)
            self.assertEqual(coordinator._scan_progress, 7)
            self.assertEqual(coordinator.selectedCount, 1)
            restored = ChannelImportCoordinator()
            restored.attach_project("project:test", temp_dir, set())
            self.assertEqual(restored.state, "partial")
            self.assertEqual(restored.status, warning)
            self.assertEqual(restored.candidateCount, 1)
            coordinator.shutdown()
            restored.shutdown()

    def test_all_scan_counts_are_shown_and_shortfall_notice_survives_reopen(self):
        for count in (0, 1, 22, 50, 100):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as temp_dir:
                coordinator = ChannelImportCoordinator()
                request = ChannelImportRequest(url="https://www.douyin.com/user/creator", platform="douyin",
                                               limit=100, duration_filter="all")
                session = new_session("project:test", temp_dir, request)
                coordinator._sessions[session.session_id] = session
                coordinator._active_session_id = session.session_id
                rows = [ChannelVideoCandidate(remote_video_id=str(index),
                        source_url=f"https://www.douyin.com/video/{index}", title="Video", platform="Douyin")
                        for index in range(count)]
                warning = f"Tìm thấy {count}/100 video phù hợp." if count < 100 else ""
                coordinator._handle_scan_resolved(session.session_id, {
                    "platform": "Douyin", "candidates": [row.model_dump(mode="json") for row in rows],
                    "warning": warning, "scan_progress": 7,
                })
                self.assertFalse(coordinator.busy)
                self.assertEqual(coordinator.candidates.rowCount(), count)
                self.assertEqual(coordinator.selectedCount, count)
                self.assertTrue(coordinator.status)
                restored = ChannelImportCoordinator()
                restored.attach_project("project:test", temp_dir, set())
                self.assertEqual(restored.candidates.rowCount(), count)
                self.assertEqual(restored.status, coordinator.status)
                coordinator.shutdown()
                restored.shutdown()

    def test_failed_rescan_preserves_detached_old_rows_only_for_same_channel(self):
        for same_channel in (True, False):
            with self.subTest(same_channel=same_channel), tempfile.TemporaryDirectory() as temp_dir:
                coordinator = ChannelImportCoordinator()
                request = ChannelImportRequest(url="https://www.douyin.com/user/creator", platform="douyin",
                                               ranking="popular", limit=20, duration_filter="all")
                session = new_session("project:test", temp_dir, request)
                session.platform = "Douyin"
                session.state = "ready"
                session.candidates = [ChannelVideoCandidate(remote_video_id="one",
                    source_url="https://www.douyin.com/video/one", title="Video", platform="Douyin")]
                coordinator._sessions[session.session_id] = session
                coordinator._project_sessions[session.project_key] = session.session_id
                coordinator.attach_project(session.project_key, temp_dir, set())
                url = request.url if same_channel else "https://www.douyin.com/user/another"
                with mock.patch("hflow.desktop.channel_import.threading.Thread.start"):
                    coordinator.inspect(url, "douyin", "popular", 50, "all", 300)
                active = coordinator._active_session()
                self.assertIsNot(active, session)
                if same_channel:
                    self.assertIsNot(active.candidates[0], session.candidates[0])
                coordinator._handle_scan_rejected(active.session_id, "Douyin không trả dữ liệu", False)
                self.assertFalse(coordinator.busy)
                self.assertEqual(coordinator.candidateCount, int(same_channel))
                self.assertEqual(coordinator.state, "partial" if same_channel else "error")
                if same_channel:
                    self.assertIn("từ lần quét trước", coordinator.status)
                    self.assertEqual(coordinator.selectedCount, 1)
                    restored = ChannelImportCoordinator()
                    restored.attach_project("project:test", temp_dir, set())
                    self.assertEqual(restored.candidateCount, 1)
                    self.assertEqual(restored.status, coordinator.status)
                    restored.shutdown()
                coordinator.shutdown()

    def test_channel_download_is_owned_by_downloads_page_not_batch(self):
        main_qml = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
        batch_qml = (QML_DIR / "BatchPage.qml").read_text(encoding="utf-8")
        downloads_qml = (QML_DIR / "DownloadsPage.qml").read_text(encoding="utf-8")
        channel_download_qml = (QML_DIR / "ChannelDownloadPage.qml").read_text(encoding="utf-8")
        self.assertNotIn("routeChannelImport", main_qml)
        self.assertNotIn("requestChannelImport", batch_qml)
        self.assertIn("ChannelDownloadPage", downloads_qml)
        self.assertIn("inspectChannel", channel_download_qml)
        self.assertIn("downloadSelectedChannel", channel_download_qml)
        self.assertIn("AppComboBox", channel_download_qml)
        self.assertIn('"Bilibili", "value": "bilibili"', channel_download_qml)
        self.assertNotIn("SegmentedControl", channel_download_qml)

    def test_downloads_has_queue_feedback_without_redundant_background_badge(self):
        downloads_qml = (QML_DIR / "DownloadsPage.qml").read_text(encoding="utf-8")
        self.assertNotIn("Tác vụ nền đang chạy", downloads_qml)
        self.assertNotIn("StatusBadge", downloads_qml)
        self.assertIn("DownloadQueueStatus", downloads_qml)
        self.assertIn("currentProjectHasWork", downloads_qml)  # deletion remains guarded

    def test_progress_does_not_invalidate_session_authentication_or_counts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            coordinator = ChannelImportCoordinator()
            request = ChannelImportRequest(url="https://www.youtube.com/@creator")
            session = new_session("project:test", temp_dir, request)
            coordinator._sessions[session.session_id] = session
            coordinator._project_sessions[session.project_key] = session.session_id
            coordinator._active_session_id = session.session_id
            coordinator._rebuild_session_cache(session)
            observed = {
                "progress": 0,
                "status": 0,
                "session": 0,
                "authentication": 0,
                "counts": 0,
            }
            coordinator.progressChanged.connect(
                lambda: observed.__setitem__("progress", observed["progress"] + 1)
            )
            coordinator.statusChanged.connect(
                lambda: observed.__setitem__("status", observed["status"] + 1)
            )
            coordinator.sessionChanged.connect(
                lambda: observed.__setitem__("session", observed["session"] + 1)
            )
            coordinator.authenticationChanged.connect(
                lambda: observed.__setitem__("authentication", observed["authentication"] + 1)
            )
            coordinator.countsChanged.connect(
                lambda: observed.__setitem__("counts", observed["counts"] + 1)
            )
            try:
                coordinator._handle_download_progress(session.session_id, "", 37, "Reading video details")
            finally:
                coordinator.shutdown()

            self.assertEqual(observed["progress"], 1)
            self.assertEqual(observed["status"], 1)
            self.assertEqual(observed["session"], 0)
            self.assertEqual(observed["authentication"], 0)
            self.assertEqual(observed["counts"], 0)

    def test_channel_download_workers_are_daemons_and_cancellable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            coordinator = ChannelImportCoordinator()
            request = ChannelImportRequest(url="https://www.youtube.com/@creator")
            session = new_session("project:test", temp_dir, request)
            session.candidates = [
                ChannelVideoCandidate(
                    remote_video_id="video-1",
                    source_url="https://www.youtube.com/watch?v=video-1",
                    title="Video",
                    platform="YouTube",
                )
            ]
            session.state = "ready"
            session.status = "Ready"
            coordinator.attach_project("project:test", temp_dir, set())
            coordinator._sessions[session.session_id] = session
            coordinator._project_sessions[session.project_key] = session.session_id
            coordinator._active_session_id = session.session_id
            coordinator._rebuild_session_cache(session)
            coordinator._refresh_active_model()
            started = threading.Event()
            release = threading.Event()

            def blocked_download(*_args, **_kwargs):
                started.set()
                release.wait(3)
                raise DownloadCancelled("cancelled")

            try:
                with mock.patch(
                    "hflow.desktop.channel_import.download_candidate",
                    side_effect=blocked_download,
                ):
                    self.assertEqual(coordinator.start_downloads(), session.session_id)
                    self.assertTrue(started.wait(1))
                    workers = [
                        thread
                        for thread in threading.enumerate()
                        if thread.name == "channel-download-video-1"
                    ]
                    self.assertTrue(workers)
                    self.assertTrue(all(thread.daemon for thread in workers))
                    coordinator.cancel()
                    release.set()
                    self.assertTrue(coordinator.shutdown(timeout_seconds=2))
            finally:
                release.set()
                coordinator.shutdown(timeout_seconds=2)


if __name__ == "__main__":
    unittest.main()

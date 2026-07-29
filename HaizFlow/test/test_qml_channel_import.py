import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Property, QUrl, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
QML_DIR = SRC / "haizflow" / "desktop" / "qml"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.desktop.channel_import import ChannelImportCoordinator
from haizflow.schemas.channel_import import ChannelImportRequest, ChannelVideoCandidate
from haizflow.services.channel_import import new_session
from haizflow.services.video_download import DownloadCancelled


class _FakeController(QObject):
    def __init__(self):
        super().__init__()
        self._importer = ChannelImportCoordinator(self)

    @Property(QObject, constant=True)
    def channelImporter(self):
        return self._importer

    @Property(str, constant=True)
    def projectName(self):
        return "Channel test"

    @Slot(result=bool)
    def prepareChannelImport(self):
        return True

    @Slot(result=bool)
    def startChannelDownloads(self):
        return False

    @Slot(int, result=bool)
    def retryChannelVideo(self, _row):
        return False


class ChannelImportQmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def test_channel_import_page_loads_with_an_empty_session(self):
        engine = QQmlEngine()
        engine.addImportPath(str(QML_DIR))
        controller = _FakeController()
        component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_DIR / "ChannelImportPage.qml")))
        self.assertTrue(component.isReady(), "\n".join(error.toString() for error in component.errors()))
        page = component.createWithInitialProperties({"appController": controller})
        self.assertIsNotNone(page, "\n".join(error.toString() for error in component.errors()))
        try:
            self.app.processEvents()
            self.assertEqual(page.property("hasResults"), False)
        finally:
            controller._importer.shutdown()
            page.deleteLater()
            engine.deleteLater()
            self.app.processEvents()

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

    def test_channel_import_form_resyncs_only_when_the_project_session_changes(self):
        page_qml = (QML_DIR / "ChannelImportPage.qml").read_text(encoding="utf-8")
        self.assertIn("property string syncedSessionId", page_qml)
        self.assertIn("if (syncedSessionId === sessionId)", page_qml)
        self.assertIn("function onSessionChanged()", page_qml)
        self.assertIn("function onAuthenticationChanged()", page_qml)
        self.assertNotIn("function onChanged()", page_qml)
        self.assertIn("const request = importer.requestData", page_qml)
        self.assertIn("channelUrl.text = String(request.url || importer.channelUrl || \"\")", page_qml)

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
                    "haizflow.desktop.channel_import.download_candidate",
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

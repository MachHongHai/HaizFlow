import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.desktop.media_download_controller import MediaDownloadController
from haizflow.desktop.presenters import build_project_summaries
from haizflow.services import project_store


class DownloadProjectTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.original_index = project_store.PROJECT_INDEX_PATH
        project_store.PROJECT_INDEX_PATH = str(self.root / "runtime" / "projects.json")

    def tearDown(self):
        project_store.PROJECT_INDEX_PATH = self.original_index
        self.temporary.cleanup()

    def test_download_project_is_persisted_with_owned_output_directories(self):
        project = project_store.create_project(
            "Creator archive", str(self.root / "outputs"), "download",
        )

        restored = project_store.list_projects()[0]
        downloads = Path(project_store.project_downloads_dir_for_key(project["key"]))

        self.assertEqual(restored["project_type"], "download")
        self.assertEqual(project["key"], restored["key"])
        self.assertTrue((downloads / "channel").is_dir())
        self.assertTrue((downloads / "video").is_dir())
        self.assertTrue((downloads / "audio").is_dir())
        self.assertEqual(
            build_project_summaries([], [restored])[0]["status"],
            "ready",
        )

    def test_each_queued_task_keeps_the_output_of_its_download_project(self):
        first = project_store.create_project("First", str(self.root / "outputs"), "download")
        second = project_store.create_project("Second", str(self.root / "outputs"), "download")
        controller = MediaDownloadController()
        try:
            controller.attach_project(first["key"], first["project_root"])
            first_video_output = controller.videoOutputDirectory
            with mock.patch.object(controller, "_start_next"):
                controller._queue_download(
                    "https://example.com/video", "video",
                    controller.videoOutputDirectory, "video download",
                )
                controller.attach_project(second["key"], second["project_root"])

            self.assertEqual(controller._pending_tasks[0]["project_key"], first["key"])
            self.assertEqual(controller._pending_tasks[0]["output"], first_video_output)
            self.assertEqual(
                controller.videoOutputDirectory,
                os.path.join(second["project_root"], "downloads", "video"),
            )
        finally:
            controller.shutdown()

    def test_channel_task_prevents_switching_projects_until_it_finishes(self):
        first = project_store.create_project("First", str(self.root / "outputs"), "download")
        second = project_store.create_project("Second", str(self.root / "outputs"), "download")
        controller = MediaDownloadController()
        try:
            controller.attach_project(first["key"], first["project_root"])
            with mock.patch.object(controller, "_start_next"):
                controller.inspectChannel(
                    "https://www.youtube.com/@creator", "youtube", "newest", 20, "all", 0,
                )

            self.assertFalse(controller.can_switch_project(second["key"]))
            self.assertTrue(controller.currentProjectHasWork)
            controller.clearQueuedDownloads()
            self.assertTrue(controller.can_switch_project(second["key"]))
            self.assertFalse(controller.currentProjectHasWork)
        finally:
            controller.shutdown()


if __name__ == "__main__":
    unittest.main()

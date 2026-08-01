import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.services import project_store, tiktok_publish, tiktok_studio
from haizflow.desktop.localization import QMessageBox
from haizflow.desktop.models import TikTokProjectSourceListModel, TikTokPublishListModel
from haizflow.desktop.tiktok_publish_controller import TikTokPublishController


class _Signal:
    def emit(self):
        pass


class TikTokPublishTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.original_index = project_store.PROJECT_INDEX_PATH
        self.original_browser_data_dir = tiktok_publish.TIKTOK_BROWSER_DATA_DIR
        project_store.PROJECT_INDEX_PATH = str(self.root / "runtime" / "projects.json")
        tiktok_publish.TIKTOK_BROWSER_DATA_DIR = str(self.root / "runtime" / "browser-sessions" / "tiktok")
        self.project = project_store.create_project(
            "Social queue",
            str(self.root / "projects"),
            "publish",
        )

    def tearDown(self):
        project_store.PROJECT_INDEX_PATH = self.original_index
        tiktok_publish.TIKTOK_BROWSER_DATA_DIR = self.original_browser_data_dir
        self.temporary.cleanup()

    def test_publish_project_owns_media_and_thumbnail_directories(self):
        publishing = Path(project_store.project_publishing_dir_for_key(self.project["key"]))

        self.assertEqual(self.project["project_type"], "publish")
        self.assertTrue((publishing / "media").is_dir())
        self.assertTrue((publishing / "thumbnails").is_dir())

    def test_caption_and_hashtags_are_normalized_within_tiktok_limit(self):
        caption = "A" * 2300
        hashtags = "review, #Video review; fyp!"

        composed = tiktok_publish.compose_post_text(caption, hashtags)

        self.assertLessEqual(tiktok_publish.utf16_length(composed), 2200)
        self.assertTrue(composed.endswith("#review #Video #fyp"))

    def test_queue_persists_order_edits_defaults_and_completion(self):
        project_root = self.project["project_root"]
        media = Path(tiktok_publish.media_directory(project_root))
        first_path = media / "first.mp4"
        second_path = media / "second.mp4"
        first_path.write_bytes(b"first")
        second_path.write_bytes(b"second")
        first = tiktok_publish.new_item(str(first_path), "", 0, "First", "one")
        second = tiktok_publish.new_item(str(second_path), "", 1, "Second", "two")

        tiktok_publish.append_items(project_root, [first, second])
        tiktok_publish.update_item(project_root, first["id"], status="posted")
        state = tiktok_publish.update_defaults(
            project_root,
            "Shared caption",
            "shared, queue",
            apply_to_ready_items=True,
        )

        self.assertEqual([item["file_name"] for item in state["items"]], ["first.mp4", "second.mp4"])
        self.assertEqual(state["items"][0]["caption"], "First")
        self.assertEqual(state["items"][0]["status"], "posted")
        self.assertEqual(state["items"][1]["caption"], "Shared caption")
        self.assertEqual(state["items"][1]["hashtags"], "#shared #queue")
        summary = tiktok_publish.summarize(project_root)
        self.assertEqual(summary["item_count"], 2)
        self.assertEqual(summary["posted_count"], 1)
        self.assertEqual(summary["progress"], 50)

        removed = tiktok_publish.remove_item(project_root, first["id"])
        self.assertEqual(removed["file_name"], "first.mp4")
        self.assertEqual([item["order"] for item in tiktok_publish.load_state(project_root)["items"]], [0])

    def test_missing_video_is_recovered_as_missing_instead_of_ready(self):
        missing = tiktok_publish.new_item(
            os.path.join(self.project["project_root"], "publishing", "media", "missing.mp4"),
            "",
            0,
            "",
            "",
        )
        tiktok_publish.append_items(self.project["project_root"], [missing])

        restored = tiktok_publish.load_state(self.project["project_root"])

        self.assertEqual(restored["items"][0]["status"], "missing")
        self.assertEqual(tiktok_publish.summarize(self.project["project_root"])["status"], "failed")

    def test_background_import_owns_the_video_and_keeps_its_display_name(self):
        source = self.root / "My finished video.mp4"
        source.write_bytes(b"video")
        host = SimpleNamespace(
            _project_type="publish",
            tiktok_publish_items=TikTokPublishListModel(),
            tiktokPublishChanged=_Signal(),
            refreshVideos=lambda: None,
        )
        controller = TikTokPublishController(host)
        controller.attach_project(self.project["key"], self.project["project_root"])

        with mock.patch(
            "haizflow.desktop.tiktok_publish_controller.create_video_thumbnail_path",
            return_value="",
        ):
            self.assertTrue(controller.add_videos([str(source)]))
            controller._worker.join(timeout=5)
            controller.drain_events()

        state = tiktok_publish.load_state(self.project["project_root"])
        self.assertEqual(state["items"][0]["file_name"], source.name)
        self.assertNotEqual(Path(state["items"][0]["file_path"]), source)
        self.assertTrue(Path(state["items"][0]["file_path"]).is_file())
        self.assertFalse(controller.busy)

    def test_orphan_cleanup_removes_interrupted_files_but_keeps_queue_media(self):
        media = Path(tiktok_publish.media_directory(self.project["project_root"]))
        kept = media / "kept.mp4"
        orphan = media / "abandoned.mp4.part"
        kept.write_bytes(b"kept")
        orphan.write_bytes(b"partial")
        item = tiktok_publish.new_item(str(kept), "", 0, "", "")
        tiktok_publish.append_items(self.project["project_root"], [item])

        removed = tiktok_publish.cleanup_orphaned_media(self.project["project_root"])

        self.assertEqual(removed, 1)
        self.assertTrue(kept.is_file())
        self.assertFalse(orphan.exists())

    def test_corrupt_primary_recovers_backup_without_deleting_media(self):
        project_root = self.project["project_root"]
        media = Path(tiktok_publish.media_directory(project_root))
        kept = media / "recoverable.mp4"
        kept.write_bytes(b"video")
        item = tiktok_publish.new_item(str(kept), "", 0, "first", "#one")
        tiktok_publish.append_items(project_root, [item])
        tiktok_publish.update_defaults(project_root, "second", "#two")

        Path(tiktok_publish.state_path(project_root)).write_text("{broken", encoding="utf-8")

        recovered = tiktok_publish.load_state(project_root)
        self.assertEqual(len(recovered["items"]), 1)
        self.assertEqual(recovered["items"][0]["file_path"], str(kept))
        self.assertEqual(tiktok_publish.cleanup_orphaned_media(project_root), 0)
        self.assertTrue(kept.is_file())

    def test_rendered_single_and_batch_outputs_can_be_added_to_publish_queue(self):
        output = self.root / "dubbed.mp4"
        output.write_bytes(b"rendered")
        thumbnail = self.root / "thumb.jpg"
        thumbnail.write_bytes(b"thumbnail")
        rendered = SimpleNamespace(
            video_id="rendered-video",
            project_key="batch-project",
            project_name="Finished project",
            project_type="batch",
            original_filename="source.mp4",
            status="done",
            video_width=1080,
            video_height=1920,
            files={"final_video": str(output), "thumbnail": str(thumbnail)},
        )
        second_output = self.root / "dubbed-second.mp4"
        second_output.write_bytes(b"rendered-second")
        second_rendered = SimpleNamespace(
            video_id="rendered-video-2",
            project_key="batch-project",
            project_name="Finished project",
            project_type="batch",
            original_filename="second.mp4",
            status="done",
            video_width=720,
            video_height=1280,
            files={"final_video": str(second_output), "thumbnail": str(thumbnail)},
        )
        host = SimpleNamespace(
            _project_type="publish",
            tiktok_publish_items=TikTokPublishListModel(),
            tiktok_project_sources=TikTokProjectSourceListModel(),
            tiktokPublishChanged=_Signal(),
            refreshVideos=lambda: None,
        )
        controller = TikTokPublishController(host)
        controller.attach_project(self.project["key"], self.project["project_root"])

        with mock.patch(
            "haizflow.desktop.tiktok_publish_controller.video_store.list_videos",
            return_value=[rendered, second_rendered],
        ):
            controller.refresh_project_sources()

        self.assertEqual(host.tiktok_project_sources.rowCount(), 1)
        self.assertEqual(host.tiktok_project_sources.items()[0]["video_count"], 2)
        self.assertTrue(controller.set_project_source_selected(0, True))
        self.assertEqual(controller.project_source_selected_count, 1)
        with mock.patch.object(controller, "add_videos", return_value=True) as add_videos:
            self.assertTrue(controller.add_selected_project_videos())
        add_videos.assert_called_once_with(
            [str(output), str(second_output)],
            {
                str(output): "Finished project — source.mp4",
                str(second_output): "Finished project — second.mp4",
            },
        )

    def test_folder_picker_adds_every_supported_video_in_the_folder(self):
        folder = self.root / "publish-folder"
        folder.mkdir()
        first = folder / "first.mp4"
        second = folder / "second.webm"
        ignored = folder / "notes.txt"
        first.write_bytes(b"first")
        second.write_bytes(b"second")
        ignored.write_text("not a video", encoding="utf-8")
        host = SimpleNamespace(
            _project_type="publish",
            tiktok_publish_items=TikTokPublishListModel(),
            tiktok_project_sources=TikTokProjectSourceListModel(),
            tiktokPublishChanged=_Signal(),
            refreshVideos=lambda: None,
        )
        controller = TikTokPublishController(host)
        controller.attach_project(self.project["key"], self.project["project_root"])

        with (
            mock.patch(
                "haizflow.desktop.tiktok_publish_controller.QFileDialog.getExistingDirectory",
                return_value=str(folder),
            ),
            mock.patch.object(controller, "add_videos", return_value=True) as add_videos,
        ):
            controller.browse_folder()

        add_videos.assert_called_once_with([str(first), str(second)])

    def test_prepare_login_uses_dedicated_persistent_browser_session(self):
        host = SimpleNamespace(
            _project_type="publish",
            tiktok_publish_items=TikTokPublishListModel(),
            tiktok_project_sources=TikTokProjectSourceListModel(),
            tiktokPublishChanged=_Signal(),
            refreshVideos=lambda: None,
        )
        controller = TikTokPublishController(host)

        with mock.patch(
            "haizflow.desktop.tiktok_publish_controller.open_managed_chrome_url",
            return_value=True,
        ) as opener:
            self.assertTrue(controller.prepare_login())

        opener.assert_called_once_with(
            "https://www.tiktok.com/tiktokstudio",
            os.path.abspath(tiktok_publish.TIKTOK_BROWSER_DATA_DIR),
            new_window=True,
        )
        self.assertIn("saved session", controller.status)

    def test_clear_login_closes_managed_chrome_and_removes_only_its_profile(self):
        host = SimpleNamespace(
            _project_type="publish",
            tiktok_publish_items=TikTokPublishListModel(),
            tiktok_project_sources=TikTokProjectSourceListModel(),
            tiktokPublishChanged=_Signal(),
            refreshVideos=lambda: None,
        )
        controller = TikTokPublishController(host)
        controller.attach_project(self.project["key"], self.project["project_root"])

        with (
            mock.patch(
                "haizflow.desktop.tiktok_publish_controller.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            mock.patch(
                "haizflow.desktop.tiktok_publish_controller.close_managed_chrome",
                return_value=True,
            ) as close_chrome,
            mock.patch(
                "haizflow.desktop.tiktok_publish_controller.tiktok_publish.clear_browser_session_data",
                return_value=True,
            ) as clear_session,
        ):
            self.assertTrue(controller.clear_login_session())
            controller._worker.join(timeout=5)
            controller.drain_events()

        close_chrome.assert_called_once_with(os.path.abspath(tiktok_publish.TIKTOK_BROWSER_DATA_DIR))
        clear_session.assert_called_once_with()
        self.assertFalse(controller.busy)
        self.assertIn("login removed", controller.status)

    def test_clear_browser_session_deletes_only_the_dedicated_profile(self):
        session = Path(tiktok_publish.browser_session_directory())
        session.mkdir(parents=True)
        (session / "Cookies").write_bytes(b"saved-login")

        self.assertTrue(tiktok_publish.clear_browser_session_data())
        self.assertFalse(session.exists())
        self.assertFalse(tiktok_publish.clear_browser_session_data())

    def test_failed_browser_launch_does_not_advance_post_confirmation_state(self):
        media = Path(tiktok_publish.media_directory(self.project["project_root"]))
        video = media / "ready.mp4"
        video.write_bytes(b"video")
        tiktok_publish.append_items(
            self.project["project_root"],
            [tiktok_publish.new_item(str(video), "", 0, "Caption", "#tag")],
        )
        host = SimpleNamespace(
            _project_type="publish",
            tiktok_publish_items=TikTokPublishListModel(),
            tiktok_project_sources=TikTokProjectSourceListModel(),
            tiktokPublishChanged=_Signal(),
            refreshVideos=lambda: None,
        )
        controller = TikTokPublishController(host)
        controller.attach_project(self.project["key"], self.project["project_root"])

        with (
            mock.patch(
                "haizflow.desktop.tiktok_publish_controller.QGuiApplication.clipboard",
                return_value=SimpleNamespace(setText=lambda _text: None),
            ),
            mock.patch(
                "haizflow.desktop.tiktok_publish_controller.open_managed_chrome_url",
                return_value=False,
            ),
        ):
            self.assertFalse(controller.prepare_item(0))

        item = tiktok_publish.load_state(self.project["project_root"])["items"][0]
        self.assertEqual(item["status"], "ready")
        self.assertIn("Chrome is required", controller.status)

    def test_prepare_attaches_video_and_caption_in_background(self):
        media = Path(tiktok_publish.media_directory(self.project["project_root"]))
        video = media / "ready.mp4"
        video.write_bytes(b"video")
        tiktok_publish.append_items(
            self.project["project_root"],
            [tiktok_publish.new_item(str(video), "", 0, "Caption", "#tag")],
        )
        host = SimpleNamespace(
            _project_type="publish",
            tiktok_publish_items=TikTokPublishListModel(),
            tiktok_project_sources=TikTokProjectSourceListModel(),
            tiktokPublishChanged=_Signal(),
            refreshVideos=lambda: None,
        )
        controller = TikTokPublishController(host)
        controller.attach_project(self.project["key"], self.project["project_root"])

        with (
            mock.patch(
                "haizflow.desktop.tiktok_publish_controller.QGuiApplication.clipboard",
                return_value=SimpleNamespace(setText=lambda _text: None),
            ),
            mock.patch(
                "haizflow.desktop.tiktok_publish_controller.open_managed_chrome_url",
                return_value=True,
            ),
            mock.patch(
                "haizflow.desktop.tiktok_publish_controller.tiktok_studio.prepare_upload",
                return_value=tiktok_studio.StudioPreparationResult(True, True),
            ) as prepare_upload,
        ):
            self.assertTrue(controller.prepare_item(0))
            controller._worker.join(timeout=5)
            controller.drain_events()

        prepare_upload.assert_called_once()
        item = tiktok_publish.load_state(self.project["project_root"])["items"][0]
        self.assertEqual(item["status"], "awaiting_confirmation")
        self.assertFalse(controller.busy)
        self.assertIn("ready in TikTok Studio", controller.status)


if __name__ == "__main__":
    unittest.main()

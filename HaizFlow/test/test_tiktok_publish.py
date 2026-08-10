import json
import tempfile
import unittest
from pathlib import Path

from haizflow.services import tiktok_publish


class TikTokPublishStateTests(unittest.TestCase):
    def test_post_text_normalizes_duplicate_hashtags_and_preserves_newline(self):
        text = tiktok_publish.compose_post_text(
            "  A useful caption  ",
            "#Video video, #FYP; #fyp #hướng_dẫn",
        )

        self.assertEqual(text, "A useful caption\n#Video #FYP #hướng_dẫn")
        self.assertLessEqual(
            tiktok_publish.utf16_length(text),
            tiktok_publish.MAX_POST_TEXT_UTF16,
        )

    def test_schema_one_queue_migrates_with_a_stable_request_id(self):
        with tempfile.TemporaryDirectory() as project_root:
            media = Path(project_root, "publishing", "media", "clip.mp4")
            media.parent.mkdir(parents=True)
            media.write_bytes(b"video")
            Path(tiktok_publish.state_path(project_root)).write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "default_caption": "Caption",
                        "default_hashtags": "#one",
                        "items": [
                            {
                                "id": "item-1",
                                "file_path": str(media),
                                "file_name": "clip.mp4",
                                "caption": "Caption",
                                "hashtags": "#one",
                                "status": "ready",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            migrated = tiktok_publish.load_state(project_root)
            request_id = migrated["items"][0]["request_id"]
            tiktok_publish.save_state(project_root, migrated)
            restored = tiktok_publish.load_state(project_root)

            self.assertEqual(restored["schema_version"], 2)
            self.assertEqual(restored["items"][0]["request_id"], request_id)
            self.assertTrue(request_id)
            self.assertTrue(restored["allow_comment"])
            self.assertTrue(restored["publish_now"])

    def test_cleanup_removes_only_unreferenced_project_owned_media(self):
        with tempfile.TemporaryDirectory() as project_root:
            media_dir = Path(tiktok_publish.media_directory(project_root))
            thumb_dir = Path(tiktok_publish.thumbnail_directory(project_root))
            media_dir.mkdir(parents=True)
            thumb_dir.mkdir(parents=True)
            referenced = media_dir / "keep.mp4"
            orphan = media_dir / "orphan.mp4"
            partial = thumb_dir / "interrupted.jpg.part"
            referenced.write_bytes(b"keep")
            orphan.write_bytes(b"orphan")
            partial.write_bytes(b"partial")
            state = tiktok_publish.empty_state()
            state["items"] = [
                tiktok_publish.new_item(str(referenced), "", 0, "Caption", "#tag")
            ]
            tiktok_publish.save_state(project_root, state)

            removed = tiktok_publish.cleanup_orphaned_media(project_root)

            self.assertEqual(removed, 2)
            self.assertTrue(referenced.is_file())
            self.assertFalse(orphan.exists())
            self.assertFalse(partial.exists())

    def test_publish_settings_are_project_scoped(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            tiktok_publish.save_state(first, tiktok_publish.empty_state())
            tiktok_publish.save_state(second, tiktok_publish.empty_state())
            tiktok_publish.update_publish_settings(
                first,
                selected_account_id="account-1",
                privacy_level="SELF_ONLY",
                allow_comment=False,
                publish_now=False,
            )

            first_state = tiktok_publish.load_state(first)
            second_state = tiktok_publish.load_state(second)

            self.assertEqual(first_state["selected_account_id"], "account-1")
            self.assertEqual(first_state["privacy_level"], "SELF_ONLY")
            self.assertFalse(first_state["allow_comment"])
            self.assertFalse(first_state["publish_now"])
            self.assertEqual(second_state["selected_account_id"], "")
            self.assertTrue(second_state["allow_comment"])

    def test_content_edit_rotates_idempotency_but_status_retry_does_not(self):
        with tempfile.TemporaryDirectory() as project_root:
            media = Path(project_root, "publishing", "media", "clip.mp4")
            media.parent.mkdir(parents=True)
            media.write_bytes(b"video")
            item = tiktok_publish.new_item(str(media), "", 0, "First", "#one")
            state = tiktok_publish.empty_state()
            state["items"] = [item]
            tiktok_publish.save_state(project_root, state)
            original_request_id = item["request_id"]

            status_only = tiktok_publish.update_item(project_root, item["id"], status="failed")
            edited = tiktok_publish.update_item(project_root, item["id"], caption="Second")

            self.assertEqual(status_only["request_id"], original_request_id)
            self.assertNotEqual(edited["request_id"], original_request_id)
            self.assertEqual(edited["zernio_post_id"], "")
            self.assertEqual(edited["upload_progress"], 0)


if __name__ == "__main__":
    unittest.main()

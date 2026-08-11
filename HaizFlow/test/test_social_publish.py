import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from haizflow.services import social_publish as tiktok_publish


class SocialPublishStateTests(unittest.TestCase):
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

    def test_post_text_does_not_repeat_a_hashtag_already_present_in_caption(self):
        text = tiktok_publish.compose_post_text(
            "A useful caption #Video",
            "#video #FYP",
        )

        self.assertEqual(text, "A useful caption #Video\n#FYP")

    def test_defaults_fill_empty_queue_items_without_overwriting_custom_or_active_posts(self):
        with tempfile.TemporaryDirectory() as project_root:
            media = Path(project_root, "publishing", "media", "clip.mp4")
            media.parent.mkdir(parents=True)
            media.write_bytes(b"video")
            empty = tiktok_publish.new_item(str(media), "", 0, "", "")
            custom = tiktok_publish.new_item(str(media), "", 1, "Custom", "#own")
            active = tiktok_publish.new_item(str(media), "", 2, "", "")
            active["status"] = "publishing"
            scheduled = tiktok_publish.new_item(str(media), "", 3, "Scheduled", "#later")
            scheduled["status"] = "scheduled"
            state = tiktok_publish.empty_state()
            state["items"] = [empty, custom, active, scheduled]
            tiktok_publish.save_state(project_root, state)

            updated = tiktok_publish.update_defaults(
                project_root,
                "Default caption",
                "#default",
                apply_to_ready_items=False,
            )

            self.assertEqual(updated["items"][0]["caption"], "Default caption")
            self.assertEqual(updated["items"][0]["hashtags"], "#default")
            self.assertEqual(updated["items"][1]["caption"], "Custom")
            self.assertEqual(updated["items"][1]["hashtags"], "#own")
            self.assertEqual(updated["items"][2]["caption"], "")
            self.assertEqual(updated["items"][2]["status"], "publishing")
            self.assertEqual(updated["items"][3]["caption"], "Scheduled")
            self.assertEqual(updated["items"][3]["hashtags"], "#later")
            self.assertEqual(updated["items"][3]["status"], "scheduled")

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

            self.assertEqual(restored["schema_version"], 4)
            self.assertEqual(restored["selected_platform"], "tiktok")
            self.assertEqual(restored["items"][0]["request_id"], request_id)
            self.assertTrue(request_id)
            self.assertTrue(restored["allow_comment"])
            self.assertTrue(restored["publish_now"])

    def test_legacy_tiktok_state_is_migrated_and_empty_legacy_directories_are_removed(self):
        with tempfile.TemporaryDirectory() as project_root:
            root = Path(project_root)
            (root / "exports").mkdir()
            (root / "videos").mkdir()
            legacy_path = root / tiktok_publish.LEGACY_STATE_FILE_NAME
            legacy_path.write_text(
                json.dumps({
                    "schema_version": 3,
                    "default_caption": "Legacy caption",
                    "default_hashtags": "#legacy",
                    "items": [],
                }),
                encoding="utf-8",
            )

            migrated = tiktok_publish.migrate_project_layout(project_root)

            self.assertEqual(migrated["default_caption"], "Legacy caption")
            self.assertTrue(Path(tiktok_publish.state_path(project_root)).is_file())
            self.assertFalse(legacy_path.exists())
            self.assertFalse((root / "exports").exists())
            self.assertFalse((root / "videos").exists())

    def test_layout_migration_never_removes_non_empty_legacy_directories(self):
        with tempfile.TemporaryDirectory() as project_root:
            exports = Path(project_root, "exports")
            exports.mkdir()
            user_file = exports / "keep.mp4"
            user_file.write_bytes(b"keep")

            tiktok_publish.migrate_project_layout(project_root)

            self.assertTrue(user_file.is_file())

    def test_current_layout_migration_does_not_rewrite_state_on_every_open(self):
        with tempfile.TemporaryDirectory() as project_root:
            tiktok_publish.save_state(project_root, tiktok_publish.empty_state())

            with patch.object(tiktok_publish, "save_state") as save_state:
                migrated = tiktok_publish.migrate_project_layout(project_root)

            save_state.assert_not_called()
            self.assertEqual(migrated["schema_version"], tiktok_publish.STATE_SCHEMA_VERSION)

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

    def test_platform_settings_are_persisted_per_publishing_project(self):
        with tempfile.TemporaryDirectory() as project_root:
            updated = tiktok_publish.update_publish_settings(
                project_root,
                share_to_feed=False,
                ai_generated=True,
                first_comment="  Link in bio  ",
            )

            restored = tiktok_publish.load_state(project_root)
            self.assertFalse(updated["share_to_feed"])
            self.assertTrue(restored["ai_generated"])
            self.assertEqual(restored["first_comment"], "Link in bio")

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

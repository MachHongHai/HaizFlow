import unittest
import tempfile
from queue import Empty
from pathlib import Path
from unittest.mock import MagicMock, patch

from haizflow.services import social_publish as tiktok_publish, zernio
from haizflow.desktop.social_publish_controller import (
    ZERNIO_CREDENTIAL_TARGET,
    ZERNIO_API_KEYS_URL,
    ZERNIO_SIGN_IN_URL,
    ZERNIO_SIGN_UP_URL,
    ZERNIO_POSTING_DOCS_URL,
    SocialPublishController,
)


class _Signal:
    def __init__(self):
        self.emissions = 0

    def emit(self):
        self.emissions += 1


class _Host:
    def __init__(self):
        self.socialPublishStateChanged = _Signal()
        self.zernioAccountsChanged = _Signal()
        self.zernioPostOptionsChanged = _Signal()
        self.tiktokPublishChanged = _Signal()
        self.tiktok_publish_items = _Model()
        self.tiktok_project_sources = _Model()
        self.refresh_count = 0

    def refreshVideos(self):
        self.refresh_count += 1


class _Model:
    def __init__(self):
        self.items = []

    def set_items(self, items):
        self.items = list(items)

    def update_item(self, item_id, item):
        for index, current in enumerate(self.items):
            if current.get("id") == item_id:
                self.items[index] = dict(item)
                return True
        return False

    def item_at(self, row):
        return self.items[row] if 0 <= row < len(self.items) else None

    def set_selected(self, row, selected):
        if not 0 <= row < len(self.items):
            return False
        self.items[row]["selected"] = bool(selected)
        return True


class SocialPublishControllerTests(unittest.TestCase):
    def setUp(self):
        self.host = _Host()
        self.controller = SocialPublishController(self.host)

    def test_onboarding_links_open_their_dedicated_zernio_pages(self):
        with patch(
            "haizflow.desktop.social_publish_controller.open_external_url",
            return_value=True,
        ) as opened:
            self.assertTrue(self.controller.open_zernio_sign_up())
            self.assertTrue(self.controller.open_zernio_sign_in())
            self.assertTrue(self.controller.open_zernio_api_keys())
            self.assertTrue(self.controller.open_zernio_posting_docs())

        self.assertEqual(
            [call.args[0] for call in opened.call_args_list],
            [
                ZERNIO_SIGN_UP_URL,
                ZERNIO_SIGN_IN_URL,
                ZERNIO_API_KEYS_URL,
                ZERNIO_POSTING_DOCS_URL,
            ],
        )
        self.assertEqual(self.host.tiktokPublishChanged.emissions, 4)

    def test_status_change_does_not_invalidate_account_or_option_properties(self):
        self.controller._emit_changed()
        account_emissions = self.host.zernioAccountsChanged.emissions
        option_emissions = self.host.zernioPostOptionsChanged.emissions

        self.controller._status = "Publishing"
        self.controller._emit_changed()

        self.assertEqual(self.host.socialPublishStateChanged.emissions, 2)
        self.assertEqual(self.host.zernioAccountsChanged.emissions, account_emissions)
        self.assertEqual(self.host.zernioPostOptionsChanged.emissions, option_emissions)

    def test_api_key_is_read_from_windows_credential_store_once(self):
        key = "sk_" + "a" * 64
        with patch(
            "haizflow.desktop.social_publish_controller.secure_credentials.read_secret",
            return_value=key,
        ) as read_secret:
            self.assertEqual(self.controller._api_key(), key)
            self.assertEqual(self.controller._api_key(), key)

        read_secret.assert_called_once_with(ZERNIO_CREDENTIAL_TARGET)

    def test_account_ready_requires_verified_creator_options_and_posting_capacity(self):
        self.controller._accounts = [{"id": "account-1", "platform": "tiktok"}]
        self.controller._state["selected_account_id"] = "account-1"
        self.controller._creator_info_loaded = True
        self.controller._privacy_levels = ["PUBLIC_TO_EVERYONE"]

        self.assertTrue(self.controller.account_ready)
        self.controller._can_post_more = False
        self.assertFalse(self.controller.account_ready)
        self.assertFalse(self.controller.can_post_more)

    def test_background_account_refresh_does_not_mark_the_whole_page_busy(self):
        worker = MagicMock()
        with (
            patch.object(self.controller, "_api_key", return_value="sk_" + "a" * 64),
            patch("haizflow.desktop.social_publish_controller.threading.Thread", return_value=worker),
        ):
            self.assertTrue(self.controller._start_account_worker("refresh", silent=True))

        self.assertFalse(self.controller.account_syncing)
        self.assertTrue(self.controller._background_account_refreshing)
        self.assertFalse(self.controller.busy)
        worker.start.assert_called_once_with()

    def test_connect_is_not_blocked_by_an_in_flight_background_refresh(self):
        worker = MagicMock()
        self.controller._background_account_refreshing = True
        with (
            patch.object(self.controller, "_api_key", return_value="sk_" + "a" * 64),
            patch("haizflow.desktop.social_publish_controller.threading.Thread", return_value=worker),
        ):
            self.assertTrue(self.controller.connect_platform("youtube"))

        self.assertTrue(self.controller.account_syncing)
        self.assertEqual(self.controller._account_generation, 1)
        worker.start.assert_called_once_with()

    def test_creator_options_request_does_not_block_connecting_another_platform(self):
        worker = MagicMock()
        self.controller._creator_syncing = True
        with (
            patch.object(self.controller, "_api_key", return_value="sk_" + "a" * 64),
            patch("haizflow.desktop.social_publish_controller.threading.Thread", return_value=worker),
        ):
            self.assertTrue(self.controller.connect_platform("youtube"))

        self.assertTrue(self.controller.account_syncing)
        worker.start.assert_called_once_with()

    def test_disconnect_account_runs_in_the_background(self):
        worker = MagicMock()
        self.controller._accounts = [{"_id": "account-1", "platform": "youtube"}]
        with (
            patch.object(self.controller, "_api_key", return_value="sk_" + "a" * 64),
            patch("haizflow.desktop.social_publish_controller.threading.Thread", return_value=worker) as thread,
        ):
            self.assertTrue(self.controller.disconnect_account(0))

        self.assertTrue(self.controller.account_syncing)
        self.assertFalse(self.controller.busy)
        self.assertEqual(thread.call_args.kwargs["args"][-1], "account-1")
        worker.start.assert_called_once_with()

    def test_verified_account_remains_visually_ready_during_background_refresh(self):
        self.controller._accounts = [{"id": "account-1", "platform": "tiktok"}]
        self.controller._state["selected_account_id"] = "account-1"
        self.controller._creator_info_loaded = True
        self.controller._privacy_levels = ["PUBLIC_TO_EVERYONE"]
        self.controller._background_account_refreshing = True

        self.assertTrue(self.controller.account_ready)

    def test_published_item_content_cannot_be_edited(self):
        self.host.tiktok_publish_items.items = [{
            "id": "post-1", "status": "published", "caption": "Original", "hashtags": "#tag",
        }]

        with patch.object(self.controller, "_ensure_publish_project", return_value=True):
            self.assertFalse(self.controller.update_item(0, "Changed", "#new"))

    def test_posting_capacity_is_neutral_until_creator_info_loads(self):
        self.assertTrue(self.controller.can_post_more)

    def test_non_tiktok_connection_is_ready_without_tiktok_creator_info(self):
        self.controller._project_key = "publish-project"
        self.controller._project_root = "D:/HaizFlowData/publish-project"
        self.host._project_type = "publish"
        self.controller._accounts = [{"id": "youtube-1", "platform": "youtube", "name": "Channel"}]
        with patch(
            "haizflow.desktop.social_publish_controller.tiktok_publish.update_publish_settings",
            side_effect=lambda _root, **changes: {**self.controller._state, **changes},
        ):
            self.assertTrue(self.controller.select_account(0))

        self.assertEqual(self.controller.selected_platform, "youtube")
        self.assertEqual(self.controller.privacy_levels, ["public", "unlisted", "private"])
        self.assertTrue(self.controller.account_ready)

    def test_reselecting_loaded_account_does_not_rewrite_state_or_reload_model(self):
        self.controller._project_key = "publish-project"
        self.controller._project_root = "D:/HaizFlowData/publish-project"
        self.host._project_type = "publish"
        self.controller._accounts = [{"id": "youtube-1", "platform": "youtube"}]
        self.controller._state.update({
            "selected_account_id": "youtube-1",
            "selected_platform": "youtube",
        })
        self.controller._creator_info_loaded = True

        with (
            patch(
                "haizflow.desktop.social_publish_controller.tiktok_publish.update_publish_settings"
            ) as update_settings,
            patch.object(self.controller, "_sync_model") as sync_model,
        ):
            self.assertTrue(self.controller.select_account(0))

        update_settings.assert_not_called()
        sync_model.assert_not_called()

    def test_reselecting_cached_tiktok_account_does_not_wait_for_network(self):
        self.controller._project_key = "publish-project"
        self.controller._project_root = "D:/HaizFlowData/publish-project"
        self.host._project_type = "publish"
        self.controller._accounts = [{"id": "tiktok-1", "platform": "tiktok"}]
        self.controller._state.update({
            "selected_account_id": "youtube-1",
            "selected_platform": "youtube",
            "privacy_level": "public",
        })
        self.controller._creator_cache["tiktok-1"] = (
            0.0,
            {
                "levels": ["PUBLIC_TO_EVERYONE"],
                "interactions": {"comment": True},
                "can_post_more": True,
            },
        )

        with (
            patch("haizflow.desktop.social_publish_controller.time.monotonic", return_value=1.0),
            patch(
                "haizflow.desktop.social_publish_controller.tiktok_publish.update_publish_settings",
                side_effect=lambda _root, **changes: {**self.controller._state, **changes},
            ),
            patch.object(self.controller, "_start_creator_info_worker") as creator_worker,
        ):
            self.assertTrue(self.controller.select_account(0))

        creator_worker.assert_not_called()
        self.assertEqual(self.controller.privacy_levels, ["PUBLIC_TO_EVERYONE"])
        self.assertTrue(self.controller.account_ready)

    def test_waiting_card_uses_the_current_publishing_platform(self):
        self.controller._state["selected_platform"] = "youtube"
        item = {
            "caption": "Caption",
            "hashtags": "#tag",
            "status": "ready",
            "target_platform": "tiktok",
            "zernio_post_id": "",
            "thumbnail_path": "",
        }

        self.assertEqual(self.controller._model_item(item)["target_platform"], "youtube")

    def test_selected_batch_project_adds_every_rendered_video_once(self):
        self.controller._project_sources = [{
            "selected": True,
            "output_paths": [
                {"output_path": "D:/out/one.mp4", "display_name": "Batch — one.mp4"},
                {"output_path": "D:/out/two.mp4", "display_name": "Batch — two.mp4"},
            ],
        }]

        with patch.object(self.controller, "add_videos", return_value=True) as add:
            self.assertTrue(self.controller.add_selected_project_videos())

        add.assert_called_once_with(
            ["D:/out/one.mp4", "D:/out/two.mp4"],
            {
                "D:/out/one.mp4": "Batch — one.mp4",
                "D:/out/two.mp4": "Batch — two.mp4",
            },
        )

    def test_youtube_short_rejects_horizontal_or_long_video(self):
        self.controller._state["selected_platform"] = "youtube"
        self.assertIn(
            "3 minutes",
            self.controller._platform_video_error({
                "file_path": "clip.mp4",
                "duration_seconds": 181,
                "video_width": 1080,
                "video_height": 1920,
            }),
        )
        self.assertIn(
            "vertical",
            self.controller._platform_video_error({
                "file_path": "clip.mp4",
                "duration_seconds": 60,
                "video_width": 1920,
                "video_height": 1080,
            }),
        )

    def test_meta_reels_reject_webm_and_platform_duration_limits(self):
        self.controller._state["selected_platform"] = "facebook"
        self.assertIn("MP4 or MOV", self.controller._platform_video_error({"file_path": "clip.webm"}))
        self.assertIn(
            "60 seconds",
            self.controller._platform_video_error({"file_path": "clip.mp4", "duration_seconds": 61}),
        )
        self.controller._state["selected_platform"] = "instagram"
        self.assertIn(
            "90 seconds",
            self.controller._platform_video_error({"file_path": "clip.mov", "duration_seconds": 91}),
        )

    def test_published_post_without_public_url_remains_in_status_poll(self):
        item = {
            "status": "published",
            "zernio_post_id": "post-1",
            "platform_post_url": "",
        }
        self.controller._state["items"] = [item]

        self.assertEqual(self.controller._pending_post_ids(), ["post-1"])

        item["platform_post_url"] = "https://www.tiktok.com/@creator/video/123"
        self.assertEqual(self.controller._pending_post_ids(), [])

    def test_opening_publish_project_restores_zernio_accounts_automatically(self):
        with (
            patch.object(self.controller, "_reload"),
            patch.object(self.controller, "_api_key", return_value="sk_" + "a" * 64),
            patch.object(self.controller, "reconcile_accounts", return_value=True) as refresh,
            patch(
                "haizflow.desktop.social_publish_controller.tiktok_publish.migrate_project_layout"
            ),
            patch(
                "haizflow.desktop.social_publish_controller.tiktok_publish.cleanup_orphaned_media"
            ),
        ):
            self.controller.attach_project("publish-project", "D:/HaizFlowData/publish-project")

        refresh.assert_called_once_with()

    def test_refresh_syncs_supported_accounts_across_all_zernio_profiles(self):
        client = MagicMock()
        client.list_profiles.return_value = [
            {"_id": "profile-default", "name": "Default", "isDefault": True},
            {"_id": "profile-web", "name": "Web connections"},
        ]
        client.list_accounts.return_value = [
            {
                "_id": "account-web",
                "platform": "tiktok",
                "username": "@creator",
                "profileId": {"_id": "profile-web", "name": "Web connections"},
            }
        ]

        with patch(
            "haizflow.desktop.social_publish_controller.zernio.ZernioClient",
            return_value=client,
        ):
            self.controller._account_worker("refresh", "sk_" + "a" * 64, "publish-project")

        client.list_accounts.assert_called_once_with(platforms=("tiktok", "youtube", "facebook", "instagram"))
        event = self.controller._events.get_nowait()
        self.assertEqual(event["type"], "accounts")
        self.assertEqual(event["profile_id"], "profile-default")
        self.assertEqual(event["accounts"][0]["_id"], "account-web")
        with self.assertRaises(Empty):
            self.controller._events.get_nowait()

    def test_disconnect_worker_deletes_then_returns_the_fresh_account_list(self):
        client = MagicMock()
        client.list_profiles.return_value = [{"_id": "profile-default", "name": "Default"}]
        client.list_accounts.return_value = [{"_id": "account-2", "platform": "youtube"}]

        with patch(
            "haizflow.desktop.social_publish_controller.zernio.ZernioClient",
            return_value=client,
        ):
            self.controller._account_worker(
                "disconnect",
                "sk_" + "a" * 64,
                "publish-project",
                connected_account_count=2,
                generation=1,
                silent=False,
                account_id="account-1",
            )

        client.disconnect_account.assert_called_once_with("account-1")
        client.list_accounts.assert_called_once_with(platforms=("tiktok", "youtube", "facebook", "instagram"))
        event = self.controller._events.get_nowait()
        self.assertEqual(event["type"], "accounts")
        self.assertEqual(event["message"], "Social account disconnected.")
        self.assertEqual(event["accounts"], [{"_id": "account-2", "platform": "youtube"}])

    def test_background_account_poll_detects_dashboard_disconnects(self):
        self.controller._project_key = "publish-project"
        self.controller._account_refresh_next = 0.0
        with (
            patch.object(self.controller, "_api_key", return_value="sk_" + "a" * 64),
            patch.object(self.controller, "_start_account_worker", return_value=True) as refresh,
        ):
            self.controller._poll_connected_accounts()

        refresh.assert_called_once_with("refresh", silent=True)

    def test_account_refresh_clears_a_selection_removed_on_the_web(self):
        self.controller._project_key = "publish-project"
        self.controller._project_root = "D:/HaizFlowData/publish-project"
        self.controller._accounts = [{"_id": "removed", "platform": "tiktok"}]
        self.controller._state["selected_account_id"] = "removed"
        self.controller._events.put({
            "type": "accounts",
            "project_key": "publish-project",
            "profile_id": "profile-default",
            "profile_name": "Default",
            "profiles": [{"_id": "profile-default", "name": "Default"}],
            "accounts": [],
        })

        with (
            patch(
                "haizflow.desktop.social_publish_controller.tiktok_publish.update_publish_settings",
                side_effect=lambda _root, **changes: {**self.controller._state, **changes},
            ),
            patch.object(self.controller, "_poll_connected_accounts"),
        ):
            self.controller.drain_events()

        self.assertEqual(self.controller.connected_account_count, 0)
        self.assertEqual(self.controller.selected_account_index, -1)
        self.assertFalse(self.controller.account_ready)

    def test_stale_background_refresh_cannot_restore_a_disconnected_account(self):
        self.controller._project_key = "publish-project"
        self.controller._project_root = "D:/HaizFlowData/publish-project"
        self.controller._account_generation = 2
        self.controller._background_account_refreshing = True
        self.controller._accounts = []
        self.controller._events.put({
            "type": "accounts",
            "project_key": "publish-project",
            "profile_id": "profile-default",
            "profile_name": "Default",
            "profiles": [{"_id": "profile-default", "name": "Default"}],
            "accounts": [{"_id": "disconnected", "platform": "youtube"}],
            "generation": 1,
            "silent": True,
        })

        with (
            patch.object(self.controller, "_poll_connected_accounts"),
            patch.object(self.controller, "_poll_oauth_accounts"),
        ):
            self.controller.drain_events()

        self.assertEqual(self.controller.connected_account_count, 0)
        self.assertFalse(self.controller._background_account_refreshing)

    def test_silent_refresh_ignores_volatile_api_fields_without_rebuilding_the_ui(self):
        self.controller._project_key = "publish-project"
        self.controller._project_root = "D:/HaizFlowData/publish-project"
        self.controller._accounts = [{
            "_id": "youtube-account",
            "platform": "youtube",
            "displayName": "Channel",
            "updatedAt": "old",
        }]
        self.controller._state.update({
            "selected_account_id": "youtube-account",
            "selected_platform": "youtube",
        })
        self.controller._creator_info_loaded = True
        self.controller._events.put({
            "type": "accounts",
            "project_key": "publish-project",
            "profile_id": "profile-default",
            "profile_name": "Default",
            "profiles": [{"_id": "profile-default", "name": "Default"}],
            "accounts": [{
                "_id": "youtube-account",
                "platform": "youtube",
                "displayName": "Channel",
                "updatedAt": "new",
            }],
            "generation": 0,
            "silent": True,
        })
        emissions_before = self.host.tiktokPublishChanged.emissions

        with (
            patch.object(self.controller, "_sync_model") as sync_model,
            patch.object(self.controller, "_poll_connected_accounts"),
            patch.object(self.controller, "_poll_oauth_accounts"),
        ):
            self.controller.drain_events()

        sync_model.assert_not_called()
        self.assertEqual(self.host.tiktokPublishChanged.emissions, emissions_before)

    def test_stale_creator_response_cannot_overwrite_new_platform_settings(self):
        self.controller._project_key = "publish-project"
        self.controller._state["selected_account_id"] = "youtube-account"
        self.controller._creator_generation = 2
        self.controller._privacy_levels = ["public", "private"]
        self.controller._events.put({
            "type": "creator",
            "project_key": "publish-project",
            "account_id": "old-tiktok-account",
            "generation": 1,
            "levels": ["PUBLIC_TO_EVERYONE"],
            "interactions": {"comment": True, "duet": True, "stitch": True},
            "can_post_more": True,
        })

        with (
            patch.object(self.controller, "_poll_connected_accounts"),
            patch.object(self.controller, "_poll_oauth_accounts"),
        ):
            self.controller.drain_events()

        self.assertEqual(self.controller._privacy_levels, ["public", "private"])

    def test_account_labels_include_the_zernio_profile_when_available(self):
        label = self.controller._account_label({
            "_id": "account-1",
            "displayName": "Creator",
            "username": "@creator",
            "profileId": {"_id": "profile-1", "name": "Main brand"},
        })

        self.assertEqual(label, "TikTok — Creator · Main brand")

    def test_account_event_updates_the_ui_visible_account_list(self):
        self.controller._project_key = "publish-project"
        self.controller._project_root = "D:/HaizFlowData/publish-project"
        self.controller._events.put({
            "type": "accounts",
            "project_key": "publish-project",
            "profile_id": "profile-default",
            "profile_name": "Default",
            "profiles": [{"_id": "profile-default", "name": "Default"}],
            "accounts": [{
                "_id": "account-1",
                "platform": "tiktok",
                "displayName": "Creator",
                "profileId": {"_id": "profile-default", "name": "Default"},
            }],
        })

        with (
            patch(
                "haizflow.desktop.social_publish_controller.tiktok_publish.update_publish_settings",
                return_value={"selected_account_id": "account-1"},
            ),
            patch.object(self.controller, "_start_creator_info_worker", return_value=True),
        ):
            self.controller.drain_events()

        self.assertEqual(self.controller.connected_account_count, 1)
        self.assertEqual(self.controller.profile_count, 1)
        self.assertEqual(self.controller.account_names, ["TikTok — Creator · Default"])
        self.assertGreater(self.host.tiktokPublishChanged.emissions, 0)

    def test_oauth_sync_waits_for_a_new_account_instead_of_accepting_stale_results(self):
        self.controller._project_key = "publish-project"
        self.controller._project_root = "D:/HaizFlowData/publish-project"
        self.controller._accounts = [{"_id": "existing", "platform": "tiktok"}]
        self.controller._state["selected_account_id"] = "existing"
        self.controller._start_oauth_sync()

        stale_event = {
            "type": "accounts",
            "project_key": "publish-project",
            "profile_id": "profile-default",
            "profile_name": "Default",
            "profiles": [{"_id": "profile-default", "name": "Default"}],
            "accounts": [{"_id": "existing", "platform": "tiktok"}],
        }
        self.controller._events.put(stale_event)
        with (
            patch.object(self.controller, "_start_creator_info_worker", return_value=True),
            patch.object(self.controller, "_poll_oauth_accounts"),
        ):
            self.controller.drain_events()
        self.assertTrue(self.controller.oauth_sync_pending)

        self.controller._events.put({
            **stale_event,
            "accounts": [
                {"_id": "existing", "platform": "tiktok"},
                {"_id": "new-account", "platform": "youtube"},
            ],
        })
        with (
            patch.object(self.controller, "_start_creator_info_worker", return_value=True),
            patch.object(self.controller, "_poll_oauth_accounts"),
        ):
            self.controller.drain_events()
        self.assertFalse(self.controller.oauth_sync_pending)
        self.assertEqual(self.controller.connected_account_count, 2)

    def test_pending_oauth_connection_refreshes_accounts_automatically(self):
        self.controller._project_key = "publish-project"
        self.controller._oauth_sync_pending = True
        self.controller._oauth_sync_deadline = float("inf")
        self.controller._oauth_sync_next = 0.0

        with patch.object(self.controller, "_start_account_worker", return_value=True) as refresh:
            self.controller._poll_oauth_accounts()

        refresh.assert_called_once_with("refresh", silent=True)

    def test_connection_prefers_the_existing_haizflow_profile(self):
        profile = self.controller._connection_profile([
            {"_id": "default", "name": "Default", "isDefault": True},
            {"_id": "haizflow", "name": "HaizFlow"},
        ])

        self.assertEqual(profile["_id"], "haizflow")

    def test_third_connection_is_not_blocked_when_zernio_returns_authorization_url(self):
        client = MagicMock()
        client.list_profiles.return_value = [{"_id": "haizflow", "name": "HaizFlow"}]
        client.get_connect_url.return_value = "https://zernio.com/connect/third"

        with patch(
            "haizflow.desktop.social_publish_controller.zernio.ZernioClient",
            return_value=client,
        ):
            self.controller._account_worker(
                "connect",
                "sk_" + "a" * 64,
                "publish-project",
                "instagram",
                2,
            )

        event = self.controller._events.get_nowait()
        self.assertEqual(event["type"], "oauth")
        self.assertEqual(event["platform"], "instagram")
        self.assertEqual(event["url"], "https://zernio.com/connect/third")

    def test_connection_uses_the_verified_cached_profile_without_listing_profiles(self):
        client = MagicMock()
        client.get_connect_url.return_value = "https://zernio.com/connect/youtube"

        with patch(
            "haizflow.desktop.social_publish_controller.zernio.ZernioClient",
            return_value=client,
        ):
            self.controller._account_worker(
                "connect",
                "sk_" + "a" * 64,
                "publish-project",
                "youtube",
                cached_profile_id="profile-cached",
                cached_profile_name="HaizFlow",
                cached_profiles=[{"_id": "profile-cached", "name": "HaizFlow"}],
            )

        client.list_profiles.assert_not_called()
        client.get_connect_url.assert_called_once_with("profile-cached", "youtube")
        event = self.controller._events.get_nowait()
        self.assertEqual(event["type"], "oauth")
        self.assertEqual(event["profile_id"], "profile-cached")

    def test_connection_refreshes_only_when_the_cached_profile_was_deleted(self):
        client = MagicMock()
        client.list_profiles.return_value = [{"_id": "profile-new", "name": "HaizFlow"}]

        def connect_url(profile_id, _platform):
            if profile_id == "profile-cached":
                raise zernio.ZernioError("Zernio request failed (HTTP 404): profile not found")
            return "https://zernio.com/connect/recovered"

        client.get_connect_url.side_effect = connect_url
        with patch(
            "haizflow.desktop.social_publish_controller.zernio.ZernioClient",
            return_value=client,
        ):
            self.controller._account_worker(
                "connect",
                "sk_" + "a" * 64,
                "publish-project",
                "youtube",
                cached_profile_id="profile-cached",
            )

        client.list_profiles.assert_called_once_with()
        event = self.controller._events.get_nowait()
        self.assertEqual(event["type"], "oauth")
        self.assertEqual(event["profile_id"], "profile-new")

    def test_third_connection_billing_failure_has_a_clear_message(self):
        client = MagicMock()
        client.list_profiles.return_value = [{"_id": "haizflow", "name": "HaizFlow"}]
        client.get_connect_url.return_value = ""

        with patch(
            "haizflow.desktop.social_publish_controller.zernio.ZernioClient",
            return_value=client,
        ):
            self.controller._account_worker(
                "connect",
                "sk_" + "a" * 64,
                "publish-project",
                "instagram",
                2,
            )

        event = self.controller._events.get_nowait()
        self.assertEqual(event["type"], "error")
        self.assertIn("first 2 connected accounts", event["message"])
        self.assertIn("billing", event["message"])

    def test_platform_published_status_replaces_stale_local_publishing_state(self):
        with tempfile.TemporaryDirectory() as project_root:
            media = Path(project_root, "publishing", "media", "clip.mp4")
            media.parent.mkdir(parents=True)
            media.write_bytes(b"video")
            item = tiktok_publish.new_item(str(media), "", 0, "Caption", "#tag")
            item.update({"status": "publishing", "zernio_post_id": "post-1"})
            state = tiktok_publish.empty_state()
            state["items"] = [item]
            tiktok_publish.save_state(project_root, state)
            self.controller._project_key = "publish-project"
            self.controller._project_root = project_root
            self.controller._reload()
            self.controller._post_status_refreshing = True
            self.controller._events.put({
                "type": "statuses",
                "project_key": "publish-project",
                "updates": [{
                    "item_id": item["id"],
                    "status": "published",
                    "url": "https://www.tiktok.com/@creator/video/123",
                    "error": "",
                }],
            })

            with patch(
                "haizflow.desktop.social_publish_controller.project_store.touch_project_by_key"
            ):
                self.controller.drain_events()

            restored = tiktok_publish.load_state(project_root)["items"][0]
            self.assertEqual(restored["status"], "published")
            self.assertEqual(self.controller.posted_count, 1)
            self.assertFalse(self.controller._post_status_refreshing)
            self.assertEqual(self.host.tiktok_publish_items.items[0]["status"], "published")


if __name__ == "__main__":
    unittest.main()

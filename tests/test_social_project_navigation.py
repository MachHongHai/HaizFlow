"""Publishing tasks own their project, not navigation across the whole app."""

import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from haizflow.desktop.project_import_controller import ProjectImportController
from haizflow.desktop.project_workspace_controller import ProjectWorkspaceController
from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.desktop.social_publish_controller import SocialPublishController
from haizflow.services import project_store, social_publish


class Items:
    def __init__(self):
        self.items = []

    def set_items(self, items):
        self.items = list(items)

    def item_at(self, row):
        return self.items[row] if 0 <= row < len(self.items) else None

    def update_item(self, item_id, item):
        for row, current in enumerate(self.items):
            if current["id"] == item_id:
                self.items[row] = item
                return True
        return False


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    project = project_store.create_project("Posting", str(tmp_path), "publish")
    social_publish.initialize_project(project["project_root"])
    host = SimpleNamespace(
        _project_name=project["project_name"], _project_type="publish",
        _project_directory=str(tmp_path), _selected_project_key=project["key"],
        _selected_video_id=None, _settings_owner_video_id=None, _settings_language="vi",
        _project_import=None, _media_downloader=Mock(), _refresh_batch_model=Mock(),
        _clear_logs=Mock(), refreshVideos=Mock(), tiktok_publish_items=Items(),
    )
    for name in ("socialPublishStateChanged", "zernioAccountsChanged", "zernioPostOptionsChanged",
                 "tiktokPublishChanged", "projectSetupChanged", "selectedVideoChanged", "logsChanged",
                 "projectPrepared", "batchChanged", "appAlertRequested"):
        setattr(host, name, Mock())
    publisher = SocialPublishController(host)
    publisher._project_key = project["key"]
    publisher._project_root = project["project_root"]
    publisher._api_key_cache = ""
    host._tiktok_publisher = publisher
    controller = ProjectWorkspaceController(host)
    host._open_project_summary = controller.open_project_summary
    importer = ProjectImportController(host)
    monkeypatch.setattr(importer, "_reset_new_project_setup", Mock())
    monkeypatch.setattr("haizflow.services.desktop_settings.save_settings", Mock())
    monkeypatch.setattr("haizflow.desktop.social_publish_controller.QMessageBox.information", Mock())
    yield host, publisher, project, importer
    publisher.shutdown()


@pytest.mark.parametrize("project_type", ["manual", "single", "batch", "download"])
def test_busy_social_import_does_not_block_creating_unrelated_projects(workspace, project_type, tmp_path):
    host, publisher, owner, importer = workspace
    publisher._busy = True
    assert importer.prepare_project("Independent " + project_type, str(tmp_path), project_type)
    assert host._project_type == project_type
    assert host._selected_project_key != owner["key"]
    assert publisher._project_key == owner["key"]
    assert publisher.busy and not publisher._cancel.is_set()


@pytest.mark.parametrize("project_type", ["manual", "single", "batch", "download"])
def test_busy_social_task_does_not_block_opening_unrelated_projects(workspace, project_type, tmp_path):
    host, publisher, owner, _ = workspace
    project = project_store.create_project("Open " + project_type, str(tmp_path), project_type)
    project["videos"] = []
    host.prepareChannelImport = Mock()
    publisher._busy = True
    assert HaizFlowController._select_project_summary(host, project)
    host.appAlertRequested.emit.assert_not_called()
    assert host._selected_project_key == project["key"]
    assert publisher._project_key == owner["key"]
    assert publisher.busy and publisher.has_project_work(owner["key"])


def test_other_publishing_project_still_cannot_steal_the_active_worker(workspace, tmp_path):
    host, publisher, owner, importer = workspace
    other = project_store.create_project("Other posting", str(tmp_path), "publish")
    other["videos"] = []
    publisher._busy = True
    assert not HaizFlowController._select_project_summary(host, other)
    assert not importer.prepare_project("New posting", str(tmp_path), "publish")
    assert publisher._project_key == host._selected_project_key == owner["key"]


def test_returning_to_active_owner_preserves_worker_account_and_consent(workspace, tmp_path):
    host, publisher, owner, importer = workspace
    publisher._busy = publisher._consent_confirmed = True
    publisher._account_generation = 7
    publisher._creator_generation = 9
    publisher._worker = worker = Mock()
    assert importer.prepare_project("Independent", str(tmp_path), "manual")
    owner["videos"] = []
    assert HaizFlowController._select_project_summary(host, owner)
    assert publisher._worker is worker and publisher.busy
    assert publisher._consent_confirmed
    assert publisher._account_generation == 7 and publisher._creator_generation == 9


def test_import_finishes_in_its_owner_after_navigation_and_can_be_reopened(workspace, tmp_path, monkeypatch):
    host, publisher, owner, importer = workspace
    source = tmp_path / "source.mp4"
    source.write_bytes(b"original source")
    started, release = threading.Event(), threading.Event()
    def duration(*_args, **_kwargs):
        started.set()
        assert release.wait(5)
        return 10.0
    monkeypatch.setattr("haizflow.desktop.social_publish_controller.get_video_duration", duration)
    monkeypatch.setattr("haizflow.desktop.social_publish_controller.get_video_dimensions", lambda *_a, **_k: (1080, 1920))
    monkeypatch.setattr("haizflow.desktop.social_publish_controller.create_video_thumbnail_path", Mock())
    assert publisher.add_videos([str(source)])
    worker = publisher._import_thread
    try:
        assert started.wait(2)
        assert importer.prepare_project("Manual while importing", str(tmp_path), "manual")
        independent = host._selected_project_key
        release.set()
        worker.join(5)
        assert not worker.is_alive()
        publisher.drain_events()
        assert not publisher.busy
        assert host._selected_project_key == independent
        items = social_publish.load_state(owner["project_root"])["items"]
        assert len(items) == 1 and Path(items[0]["file_path"]).read_bytes() == b"original source"
        assert not social_publish.load_state(project_store.project_root_for_key(independent))["items"]
        owner["videos"] = []
        assert HaizFlowController._select_project_summary(host, owner)
        assert publisher.count == 1 and publisher._project_key == owner["key"]
        assert not list(Path(owner["project_root"]).rglob("*.part"))
    finally:
        release.set()
        worker.join(5)


def test_publish_all_continues_oldest_first_without_redirecting_to_new_workspace(workspace, tmp_path, monkeypatch):
    host, publisher, owner, importer = workspace
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"video")
    items = [social_publish.new_item(str(media), "", order, str(order), "") for order in range(3)]
    items[0]["status"] = "uploading"
    publisher._state.update(items=items, selected_account_id="account", selected_platform="youtube", privacy_level="public")
    social_publish.save_state(owner["project_root"], publisher._state)
    publisher._sync_model()
    publisher._busy = publisher._auto_continue = publisher._consent_confirmed = True
    publisher._api_key_cache = "fake-test-key"
    # Real task start/finish events, no external upload or API request.
    sent = []
    def publish(_key, project_key, item, settings):
        sent.append((project_key, item["id"], settings["account_id"]))
        publisher._events.put(dict(type="publish_finished", project_key=project_key,
            item_id=item["id"], status="published", post_id="post-" + item["id"],
            platform="youtube", url="https://www.youtube.com/watch?v=example"))
    monkeypatch.setattr(publisher, "_publish_worker", publish)
    monkeypatch.setattr(publisher, "_platform_video_error", lambda _item: "")
    assert importer.prepare_project("Work during publishing", str(tmp_path), "manual")
    independent = host._selected_project_key
    publisher._events.put(dict(type="publish_finished", project_key=owner["key"], item_id=items[0]["id"],
        status="published", post_id="first", platform="youtube", url="https://www.youtube.com/watch?v=first"))
    for _ in range(4):
        publisher.drain_events()
        if publisher._worker:
            publisher._worker.join(2)
    assert sent == [(owner["key"], items[1]["id"], "account"), (owner["key"], items[2]["id"], "account")]
    assert not publisher.busy and not publisher._auto_continue
    assert host._selected_project_key == independent
    assert all(item["status"] == "published" for item in social_publish.load_state(owner["project_root"])["items"])
    assert not social_publish.load_state(project_store.project_root_for_key(independent))["items"]


def test_cancelled_queue_does_not_continue_when_workspace_is_hidden(workspace, monkeypatch):
    _, publisher, _, _ = workspace
    publisher._auto_continue = True
    publisher._cancel.set()
    start = Mock()
    monkeypatch.setattr(publisher, "_publish_item", start)
    assert not publisher._continue_owned_queue()
    start.assert_not_called()


def test_hidden_queue_cannot_start_without_previous_publish_all_consent(workspace, monkeypatch):
    host, publisher, _, _ = workspace
    host._project_type = "manual"
    publisher._consent_confirmed = True
    publisher._auto_continue = False
    assert not publisher._ensure_ready_to_publish({}, background=True)


def setup_queue(workspace, tmp_path, monkeypatch):
    host, publisher, owner, _ = workspace
    media = tmp_path / "queue.mp4"
    media.write_bytes(b"video")
    items = [social_publish.new_item(str(media), "", order, str(order), "") for order in range(4)]
    items[0]["status"] = "uploading"
    publisher._state.update(items=items, selected_account_id="account", selected_platform="youtube", privacy_level="public")
    social_publish.save_state(owner["project_root"], publisher._state)
    publisher._busy = publisher._consent_confirmed = True
    publisher._api_key_cache = "fake-test-key"
    publisher._sync_model()
    monkeypatch.setattr(publisher, "_platform_video_error", lambda _item: "")
    # Keep unrelated account/status requests offline.
    monkeypatch.setattr(publisher, "_poll_connected_accounts", Mock())
    monkeypatch.setattr(publisher, "_poll_post_statuses", Mock())
    sent = []
    monkeypatch.setattr(publisher, "_publish_worker", lambda key, owner, item, settings:
                        sent.append((owner, item["id"], settings["account_id"])))
    return items, sent


def finish_post(publisher, owner, item, *, status="published"):
    publisher._events.put(dict(type="publish_finished", project_key=owner["key"], item_id=item["id"],
        status=status, post_id="post-" + item["id"] if status == "published" else "",
        platform="youtube", url="https://www.youtube.com/watch?v=example" if status == "published" else ""))
    publisher.drain_events()
    if publisher._worker:
        publisher._worker.join(2)


def test_individual_posts_queue_fifo_without_duplicates_or_unrequested_posts(workspace, tmp_path, monkeypatch):
    _, publisher, owner, _ = workspace
    items, sent = setup_queue(workspace, tmp_path, monkeypatch)
    active_worker = publisher._worker = Mock()
    # Newest-first rows: explicitly request item 2 before item 1; item 3 stays unrequested.
    assert publisher.publish_item(1)
    assert publisher.publish_item(2)
    assert not publisher.publish_item(1)
    assert not publisher.publish_token(publisher.item_token(3))  # active upload
    assert publisher._worker is active_worker and not sent
    assert [item["id"] for item in publisher._pending_posts] == [items[2]["id"], items[1]["id"]]
    assert publisher._host.tiktok_publish_items.item_at(1)["status"] == "queued_local"
    assert not publisher.update_item(1, "changed", "")
    assert not publisher.remove_item(1)
    assert not publisher.select_account(0)
    assert not publisher.set_publish_settings("public", True, True, True, True)
    # Queue state is session-only, never a persistent stale upload marker.
    assert social_publish.load_state(owner["project_root"])["items"][2]["status"] == "ready"
    finish_post(publisher, owner, items[0])
    assert sent == [(owner["key"], items[2]["id"], "account")]
    finish_post(publisher, owner, items[2])
    assert [post[1] for post in sent] == [items[2]["id"], items[1]["id"]]
    finish_post(publisher, owner, items[1])
    assert not publisher.busy and not publisher._pending_posts
    assert publisher._state["items"][3]["status"] == "ready"


def test_individual_queue_retains_owner_after_navigation_and_consent_for_each_request(workspace, tmp_path, monkeypatch):
    host, publisher, owner, importer = workspace
    items, sent = setup_queue(workspace, tmp_path, monkeypatch)
    assert publisher.publish_item(1)
    assert importer.prepare_project("Manual during queued upload", str(tmp_path), "manual")
    independent = host._selected_project_key
    # A later edit/reload must not revoke consent for an already-confirmed item.
    publisher._consent_confirmed = False
    finish_post(publisher, owner, items[0])
    assert sent == [(owner["key"], items[2]["id"], "account")]
    assert host._selected_project_key == independent
    finish_post(publisher, owner, items[2])
    assert not publisher.busy


@pytest.mark.parametrize("status", ["published", "ready", "failed"])
def test_cancel_clears_pending_posts_and_late_completion_cannot_restart_them(workspace, tmp_path, monkeypatch, status):
    _, publisher, owner, _ = workspace
    items, sent = setup_queue(workspace, tmp_path, monkeypatch)
    assert publisher.publish_item(1)
    publisher.cancel()
    assert publisher._cancel.is_set() and publisher._import_cancel.is_set()
    assert not publisher._pending_posts
    assert publisher._host.tiktok_publish_items.item_at(1)["status"] == "ready"
    assert not publisher.publish_item(1)  # cannot enqueue while cancellation is pending
    finish_post(publisher, owner, items[0], status=status)
    assert not sent and not publisher.busy


def test_import_during_upload_does_not_replace_worker_cancel_or_consent(workspace, tmp_path, monkeypatch):
    _, publisher, owner, _ = workspace
    items, sent = setup_queue(workspace, tmp_path, monkeypatch)
    assert publisher.publish_item(1)
    active_worker = publisher._worker = Mock()
    source = tmp_path / "new.mp4"
    source.write_bytes(b"new source")
    monkeypatch.setattr("haizflow.desktop.social_publish_controller.get_video_duration", lambda *_a, **_k: 10.0)
    monkeypatch.setattr("haizflow.desktop.social_publish_controller.get_video_dimensions", lambda *_a, **_k: (1080, 1920))
    monkeypatch.setattr("haizflow.desktop.social_publish_controller.create_video_thumbnail_path", Mock())
    assert publisher.add_videos([str(source)])
    assert not publisher.add_videos([str(source)])  # one import worker at a time
    assert publisher._worker is active_worker and publisher.import_busy
    publisher._import_thread.join(3)
    publisher.drain_events()
    assert publisher._worker is active_worker and publisher.busy and not publisher.import_busy
    assert publisher._consent_confirmed and not publisher._cancel.is_set()
    assert len(publisher._state["items"]) == 5
    # The newly prepended row must be queueable even while the original upload runs.
    assert publisher.publish_item(0)
    assert not sent
    finish_post(publisher, owner, items[0])
    assert sent[0][1] == items[2]["id"]
    assert not list(Path(owner["project_root"]).rglob("*.part"))


def test_confirmation_and_editor_tokens_survive_import_reordering(workspace, tmp_path, monkeypatch):
    host, publisher, owner, _ = workspace
    items, _ = setup_queue(workspace, tmp_path, monkeypatch)
    token = publisher.item_token(1)
    new_item = social_publish.new_item(str(tmp_path / "queue.mp4"), "", 4, "new", "")
    social_publish.append_items(owner["project_root"], [new_item])
    publisher._reload()
    assert publisher.update_item_token(token, "correct caption", "")
    assert publisher._state["items"][2]["caption"] == "correct caption"
    publisher.set_consent_confirmed(True)
    assert publisher.publish_token(token)
    assert publisher._pending_posts[0]["id"] == items[2]["id"]
    assert not publisher.publish_token("another-project:" + items[1]["id"])
    host._project_type = "manual"
    assert not publisher.publish_token(publisher.item_token(0))


def test_explicit_queue_continues_after_failure_but_does_not_retry_failed_post(workspace, tmp_path, monkeypatch):
    _, publisher, owner, _ = workspace
    items, sent = setup_queue(workspace, tmp_path, monkeypatch)
    assert publisher.publish_item(1)
    finish_post(publisher, owner, items[0], status="failed")
    assert [post[1] for post in sent] == [items[2]["id"]]
    assert publisher._state["items"][0]["status"] == "failed"


def test_publish_all_does_not_silently_include_later_imports(workspace, tmp_path, monkeypatch):
    _, publisher, owner, _ = workspace
    items, sent = setup_queue(workspace, tmp_path, monkeypatch)
    publisher._busy = False
    publisher._state["items"][0]["status"] = "ready"
    social_publish.save_state(owner["project_root"], publisher._state)
    publisher._sync_model()
    assert publisher.publish_all()
    publisher._worker.join(2)
    extra = social_publish.new_item(str(tmp_path / "queue.mp4"), "", 4, "imported later", "")
    social_publish.append_items(owner["project_root"], [extra])
    publisher._reload()
    for item in items:
        finish_post(publisher, owner, item)
    assert [post[1] for post in sent] == [item["id"] for item in items]
    assert not publisher.busy and not publisher._auto_continue
    assert publisher._state["items"][-1]["status"] == "ready"


def test_import_completion_and_queue_wait_until_both_workers_finish(workspace, tmp_path, monkeypatch):
    _, publisher, owner, _ = workspace
    items, sent = setup_queue(workspace, tmp_path, monkeypatch)
    assert publisher.publish_item(1)
    publisher._import_busy = True
    finish_post(publisher, owner, items[0])
    assert publisher.busy and not sent
    publisher._events.put(dict(type="import_finished", project_key=owner["key"], done=0, total=0, errors=[]))
    publisher.drain_events()
    publisher._worker.join(2)
    assert [post[1] for post in sent] == [items[2]["id"]]


def test_shutdown_discards_manual_queue_without_changing_prior_results(workspace, tmp_path, monkeypatch):
    _, publisher, owner, _ = workspace
    items, sent = setup_queue(workspace, tmp_path, monkeypatch)
    assert publisher.publish_item(1)
    publisher.shutdown()
    assert not publisher._pending_posts
    finish_post(publisher, owner, items[0])
    assert not sent and not publisher.busy
    assert social_publish.load_state(owner["project_root"])["items"][2]["status"] == "ready"


def test_import_finish_preserves_publish_all_consent_when_upload_finished_first(workspace, tmp_path, monkeypatch):
    _, publisher, owner, _ = workspace
    items, sent = setup_queue(workspace, tmp_path, monkeypatch)
    publisher._auto_continue = True
    publisher._auto_post_ids = {item["id"] for item in items}
    publisher._import_busy = True
    finish_post(publisher, owner, items[0])
    assert not sent and publisher._auto_continue
    publisher._events.put(dict(type="import_finished", project_key=owner["key"], done=0, total=0, errors=[]))
    publisher.drain_events()
    publisher._worker.join(2)
    assert publisher._consent_confirmed
    assert sent == [(owner["key"], items[1]["id"], "account")]

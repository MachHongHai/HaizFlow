"""Deterministic optional-browser install and session gates; no network/browser."""
import hashlib
import json
import threading
import zipfile
from dataclasses import replace
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QObject, Signal

from haizflow.services import douyin_component as browser
from haizflow.services.model_bootstrap import ModelBootstrapCancelled, _approved_download_url
from haizflow.services.resource_packs import ResourcePackManager


@pytest.fixture
def pack(tmp_path, monkeypatch):
    engines, packages = tmp_path / "engines", tmp_path / "packages"
    packages.mkdir()
    monkeypatch.setattr("haizflow.services.resource_packs.engines_dir", lambda: engines)
    monkeypatch.setattr("haizflow.core.paths.engines_dir", lambda: engines)
    monkeypatch.setattr("haizflow.services.resource_packs.resource_packages_dir", lambda: packages)
    monkeypatch.setattr("haizflow.services.resource_packs.resource_storage_dir", lambda: tmp_path)
    definition = ResourcePackManager().definitions[browser.PACK_ID]
    archive = packages / f"{browser.PACK_ID}-{browser.REVISION}.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for name in ("chrome.exe", "chrome.dll", "resources.pak", "icudtl.dat"):
            bundle.writestr(f"chrome-win/{name}", b"fixture")
        bundle.writestr("chrome-win/interactive_ui_tests.exe", b"excluded")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    monkeypatch.setattr(browser, "SHA256", digest)
    definition = replace(definition, archive_sha256=digest, download_size=archive.stat().st_size, installed_size=28)
    monkeypatch.setattr(browser, "smoke", lambda root, cancel_event=None:
                        browser.verify_files(root, full=True, cancel_event=cancel_event))
    return ResourcePackManager([definition]), archive


def test_playwright_import_is_not_an_installed_browser(pack):
    manager, _ = pack
    with patch.object(manager, "_module_available", return_value=True):
        assert manager.status(browser.PACK_ID) == "missing"
        assert not browser.installed()


def test_install_reuses_cache_and_second_install_does_not_unpack_again(pack):
    manager, _ = pack
    with patch("haizflow.services.model_bootstrap.urllib.request.urlopen") as network:
        manager.install(browser.PACK_ID, lambda *_: None)
        assert manager.status(browser.PACK_ID) == "installed"
        assert browser.installed()
        assert not (browser.component_root() / "chrome-win/interactive_ui_tests.exe").exists()
        with patch.object(manager, "_install_engine_archive") as install:
            manager.install(browser.PACK_ID, lambda *_: None)
            install.assert_not_called()
        network.assert_not_called()


def test_corrupted_inventory_or_missing_dll_is_not_installed_and_can_reinstall(pack):
    manager, _ = pack
    manager.install(browser.PACK_ID, lambda *_: None)
    root = browser.component_root()
    (root / "chrome-win/chrome.dll").unlink()
    assert not browser.installed()
    assert manager.status(browser.PACK_ID) == "missing"
    manager.install(browser.PACK_ID, lambda *_: None)
    assert browser.installed()
    (root / "complete.json").write_text("[]", encoding="utf-8")
    assert not browser.installed()
    manager.install(browser.PACK_ID, lambda *_: None)
    assert browser.installed()


def test_explicit_verification_catches_same_size_corruption_and_repair_recovers(pack):
    manager, _ = pack
    manager.install(browser.PACK_ID, lambda *_: None)
    (browser.component_root() / "chrome-win/chrome.dll").write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        browser.verify_files(browser.component_root(), full=True)
    manager.install(browser.PACK_ID, lambda *_: None, repair=True)
    assert browser.installed()
    browser.verify_files(browser.component_root(), full=True)


def test_remove_and_reinstall_do_not_conflict_with_verified_cache(pack):
    manager, archive = pack
    manager.install(browser.PACK_ID, lambda *_: None)
    assert manager.remove(browser.PACK_ID) > 0
    assert manager.status(browser.PACK_ID) == "missing" and archive.exists()
    manager.install(browser.PACK_ID, lambda *_: None)
    assert browser.installed()


def test_paused_download_survives_inventory_and_can_be_discarded(pack):
    manager, archive = pack
    archive.unlink()
    partial = archive.with_name(archive.name + ".part")
    partial.write_bytes(b"partial")
    assert manager.status(browser.PACK_ID) == "paused"
    assert manager.discard_download(browser.PACK_ID) == 7
    assert manager.status(browser.PACK_ID) == "missing"


def test_cancelled_extract_cannot_publish_install_marker(pack):
    manager, _ = pack
    def progress(pack_id, event):
        if event.state == "installing":
            manager.cancel(pack_id)
    with pytest.raises(ModelBootstrapCancelled):
        manager.install(browser.PACK_ID, progress)
    assert not browser.installed()
    assert not list(browser.component_root().parent.glob("*.partial"))
    manager.install(browser.PACK_ID, lambda *_: None)
    assert browser.installed()


def test_inventory_checksum_tampering_and_unsafe_members_are_rejected(pack):
    manager, _ = pack
    manager.install(browser.PACK_ID, lambda *_: None)
    root = browser.component_root()
    (root / "browser-files.json").write_text('[{"file":"../elsewhere"}]', encoding="utf-8")
    assert not browser.installed()
    with pytest.raises(ValueError, match="Unsafe"):
        browser.verify_files(root)


def test_cancellation_is_checked_during_verification(pack):
    manager, _ = pack
    manager.install(browser.PACK_ID, lambda *_: None)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(ModelBootstrapCancelled):
        browser.verify_files(browser.component_root(), full=True, cancel_event=cancel)


def test_only_official_chromium_bucket_is_added_to_download_allowlist():
    assert _approved_download_url(browser.URL)
    assert not _approved_download_url("http://storage.googleapis.com/chromium-browser-snapshots/Win_x64/1/a.zip")
    assert not _approved_download_url("https://storage.googleapis.com/another-bucket/a.zip")
    assert not _approved_download_url("https://storage.googleapis.com.evil.example/chromium-browser-snapshots/Win_x64/1/a.zip")


def test_missing_pack_shows_notification_and_does_not_create_worker(pack):
    from haizflow.desktop.douyin_session_controller import DouyinSessionController
    class Host(QObject):
        appAlertRequested = Signal(str, str, str)
    host = Host()
    alerts = []
    host.appAlertRequested.connect(lambda *args: alerts.append(args))
    session = DouyinSessionController(host)
    with patch("haizflow.desktop.douyin_session_controller.threading.Thread") as thread:
        session.create()
        thread.assert_not_called()
    assert not session.ready and not session.busy
    assert session.status == browser.MISSING_MESSAGE
    assert alerts and "Gói tài nguyên" in alerts[0][1]
    assert session.request_error("https://douyin.com/video/123") == browser.MISSING_MESSAGE
    assert not session.request_error("https://youtu.be/demo")


def test_pending_browser_operation_blocks_create_without_losing_previous_session(pack):
    from haizflow.desktop.douyin_session_controller import DouyinSessionController
    host = QObject()
    host._resource_packs = Mock()
    host._resource_packs._storage_mutating.return_value = False
    host._resource_packs.browser_operation_pending.return_value = True
    session = DouyinSessionController(host)
    session._ready = True
    with patch("haizflow.desktop.douyin_session_controller.threading.Thread") as thread:
        session.create()
        thread.assert_not_called()
    assert session.ready and not session.busy


def test_removed_pack_clears_ready_flag():
    from haizflow.desktop.douyin_session_controller import DouyinSessionController
    session = DouyinSessionController()
    session._ready = True
    session._set_status(browser.MISSING_MESSAGE)
    assert not session.ready


def test_browser_progress_reserves_unpack_and_validation_stages():
    from haizflow.desktop.resource_progress import InstallProgress, localized_progress
    from haizflow.services.model_bootstrap import ModelProgress
    tracker = InstallProgress(((browser.PACK_ID, 100),))
    downloaded = tracker.update(browser.PACK_ID, ModelProgress("ready", "", "", 100, 100, "transfer"))
    unpacked = tracker.update(browser.PACK_ID, ModelProgress("installing", "", "", 100, 100, "installing"))
    assert downloaded == 70 and unpacked == 95
    assert "Chromium" in localized_progress({"unit": browser.PACK_ID, "state": "downloading"}, "vi")

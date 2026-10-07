"""Owned browser, manual verification and SDK lifecycle without real network."""
import asyncio
import os
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from haizflow.services.douyin_browser import (
    DouyinBrowserSession, _component_environment, create_anonymous_state,
)
from haizflow.services.douyin_classification import DouyinError, Outcome
from haizflow.services.douyin_signing import DETAIL_PATH
from haizflow.services.douyin_transport import BrowserProfile
from haizflow.services.video_download import DownloadCancelled
from haizflow.vendor.douyin_browser_sdk import FINGERPRINT_READ


def guest(*, cookies=None, challenge=False):
    cookies = cookies if cookies is not None else [
        {"name": "UIFID_TEMP", "value": "guest-only", "domain": ".douyin.com", "path": "/"}]
    frame = SimpleNamespace(url="https://www.douyin.com/")
    page = SimpleNamespace(
        goto=AsyncMock(), reload=AsyncMock(), add_init_script=AsyncMock(),
        locator=Mock(return_value=SimpleNamespace(inner_text=AsyncMock(return_value="抖音"))),
        evaluate=AsyncMock(), main_frame=frame, frames=[frame])
    if challenge:
        element = SimpleNamespace(bounding_box=AsyncMock(return_value={"width": 300, "height": 200}))
        page.frames.append(SimpleNamespace(url="https://verify.example/captcha/",
                                           frame_element=AsyncMock(return_value=element)))
    fingerprint = {"userAgent": BrowserProfile(version="146.0.7680.177").ua, "platform": "Win32",
                   "width": 1920, "height": 1080, "language": "zh-CN", "cores": 8, "memory": 8}
    async def evaluate(script, args=None):
        if script == FINGERPRINT_READ:
            return fingerprint
        # Simulate the site SDK's exact signed URL, including encoded token.
        return args["url"] + "&a_bogus=fixture&uifid=guest-only&timestamp=1&x-secsdk-web-signature=sig&msToken=token%2B"
    page.evaluate.side_effect = evaluate
    context = SimpleNamespace(pages=[page], cookies=AsyncMock(return_value=cookies),
                              add_cookies=AsyncMock(), close=AsyncMock())
    driver = SimpleNamespace(launch_persistent_context_async=AsyncMock(return_value=context))
    return driver, context, page


@pytest.fixture(autouse=True)
def component_in_test_directory(tmp_path):
    with patch("haizflow.services.douyin_browser.component_directory", return_value=tmp_path):
        yield


def test_owned_profile_sdk_and_browser_are_reused_without_personal_profile():
    driver, context, page = guest()
    with patch("haizflow.services.douyin_browser._driver", return_value=driver):
        state = create_anonymous_state()
        backend = state["backend"]
        try:
            signed, _ = backend.sign(DETAIL_PATH, {"aweme_id": "42"}, state["cookies"])
            assert signed.url.endswith("&msToken=token%2B") and signed.mode == "browser-sdk"
            assert signed.headers["uifid"] == "guest-only"
            options = driver.launch_persistent_context_async.call_args.kwargs
            assert options["headless"] is False and options["chromium_sandbox"] is True
            assert options["stealth_args"] is False and options["browser_version"] == "146.0.7680.177.5"
            assert not any("no-sandbox" in arg or "disable-web-security" in arg for arg in options["args"])
            profile = Path(options["user_data_dir"])
            assert profile.name.startswith("guest-") and profile.is_dir()
            driver.launch_persistent_context_async.assert_awaited_once()
            page.goto.assert_awaited_once()
            context.close.assert_not_awaited()
        finally:
            backend.close()
    context.close.assert_awaited_once()
    assert not profile.exists() and not backend._thread.is_alive()


def test_captcha_waits_for_human_and_does_not_close_immediately():
    driver, context, page = guest(challenge=True)
    statuses = []
    def progress(value):
        statuses.append(value)
        context.close.assert_not_awaited()
        page.evaluate.assert_not_awaited()  # no signature attempts while challenged
        page.frames = [page.main_frame]  # simulate human completing verification
    with patch("haizflow.services.douyin_browser._driver", return_value=driver):
        state = create_anonymous_state(status_callback=progress)
        state["backend"].close()
    assert statuses == ["Complete verification in the Douyin window.", "Checking the Douyin session"]


def test_human_wait_is_bounded_and_timeout_closes_owned_context():
    driver, context, _ = guest(challenge=True)
    with patch("haizflow.services.douyin_browser._driver", return_value=driver), \
         patch("haizflow.services.douyin_browser.HUMAN_WAIT_SECONDS", 0), \
         pytest.raises(RuntimeError, match="timed out"):
        create_anonymous_state()
    context.close.assert_awaited_once()


def test_cancel_during_human_wait_closes_and_restores_environment():
    driver, context, _ = guest(challenge=True)
    cancel = threading.Event()
    with patch("haizflow.services.douyin_browser._driver", return_value=driver), \
         patch.dict(os.environ, {"CLOAKBROWSER_LICENSE_KEY": "ambient-not-used"}):
        with pytest.raises(DownloadCancelled):
            create_anonymous_state(cancel, status_callback=lambda value: cancel.set())
        assert os.environ["CLOAKBROWSER_LICENSE_KEY"] == "ambient-not-used"
    context.close.assert_awaited_once()


def test_cancel_navigation_closes_partial_context():
    driver, context, page = guest()
    cancel = threading.Event()
    async def navigating(*args, **kwargs):
        cancel.set()
        await asyncio.sleep(60)
    page.goto.side_effect = navigating
    with patch("haizflow.services.douyin_browser._driver", return_value=driver), \
         pytest.raises(DownloadCancelled):
        create_anonymous_state(cancel)
    context.close.assert_awaited_once()


def test_authenticated_context_is_rejected_not_imported():
    driver, context, _ = guest(cookies=[{"name": "sessionid", "value": "not-used"}])
    with patch("haizflow.services.douyin_browser._driver", return_value=driver), \
         pytest.raises(RuntimeError, match="anonymous"):
        create_anonymous_state()
    context.close.assert_awaited_once()


def test_idle_close_reopens_same_owned_profile_and_fingerprint_seed():
    driver, context, page = guest()
    with patch("haizflow.services.douyin_browser._driver", return_value=driver):
        state = create_anonymous_state()
        backend = state["backend"]
        try:
            asyncio.run_coroutine_threadsafe(backend._close_context(), backend._loop).result(2)
            backend.sign(DETAIL_PATH, {"aweme_id": "42"}, state["cookies"])
            calls = driver.launch_persistent_context_async.call_args_list
            assert len(calls) == 2
            assert calls[0].kwargs["user_data_dir"] == calls[1].kwargs["user_data_dir"]
            assert calls[0].kwargs["args"] == calls[1].kwargs["args"]
            context.add_cookies.assert_awaited_once_with(state["cookies"])
            assert page.goto.await_count == 2
        finally:
            backend.close()


@pytest.mark.parametrize("corrupt", ["https://evil.example/", "https://www.douyin.com/other?", ""])
def test_unusable_sdk_url_never_leaves_browser(corrupt):
    driver, context, page = guest()
    original = page.evaluate.side_effect
    async def evaluate(script, args=None):
        return await original(script, args) if script == FINGERPRINT_READ else corrupt
    page.evaluate.side_effect = evaluate
    with patch("haizflow.services.douyin_browser._driver", return_value=driver), \
         patch("haizflow.services.douyin_browser.SDK_WAIT_SECONDS", 0), pytest.raises(DouyinError) as error:
        create_anonymous_state()
    assert error.value.outcome == Outcome.SIGNATURE
    context.close.assert_awaited_once()


def test_component_environment_is_scoped_and_never_disables_verification():
    with patch.dict(os.environ, {"CLOAKBROWSER_LICENSE_KEY": "not-used", "CLOAKBROWSER_SKIP_CHECKSUM": "true"}):
        with _component_environment():
            assert os.environ["CLOAKBROWSER_LICENSE_KEY"] == ""
            assert os.environ["CLOAKBROWSER_SKIP_CHECKSUM"] == ""
            assert os.environ["CLOAKBROWSER_AUTO_UPDATE"] == "false"
        assert os.environ["CLOAKBROWSER_LICENSE_KEY"] == "not-used"
        assert os.environ["CLOAKBROWSER_SKIP_CHECKSUM"] == "true"


def test_closed_backend_cannot_restart_a_browser():
    backend = DouyinBrowserSession()
    backend.close()
    with pytest.raises(RuntimeError, match="closed"):
        backend.open()


def test_hidden_verification_iframe_is_not_a_visible_captcha():
    driver, _, page = guest(challenge=True)
    page.frames[-1].frame_element.return_value.bounding_box.return_value = None
    with patch("haizflow.services.douyin_browser._driver", return_value=driver):
        state = create_anonymous_state()
        state["backend"].close()


def test_sdk_sign_can_wait_for_manual_verification_after_session_creation():
    driver, context, page = guest()
    statuses = []
    def progress(value):
        statuses.append(value)
        if value == "Complete verification in the Douyin window.":
            context.close.assert_not_awaited()
            page.frames = [page.main_frame]
    with patch("haizflow.services.douyin_browser._driver", return_value=driver):
        state = create_anonymous_state(status_callback=progress)
        element = SimpleNamespace(bounding_box=AsyncMock(return_value={"width": 300, "height": 200}))
        page.frames.append(SimpleNamespace(url="https://verify.example/captcha/",
                                           frame_element=AsyncMock(return_value=element)))
        try:
            state["backend"].sign(DETAIL_PATH, {"aweme_id": "42"}, state["cookies"])
        finally:
            state["backend"].close()
    assert statuses == ["Complete verification in the Douyin window.",
                        "Checking the Douyin session", "Douyin session ready"]


def test_shutdown_interrupts_active_human_wait_before_closing_browser():
    driver, context, _ = guest(challenge=True)
    waiting = threading.Event()
    results = []
    backend = DouyinBrowserSession()
    def run():
        try:
            backend.open(status_callback=lambda value: waiting.set())
        except DownloadCancelled:
            results.append("cancelled")
    with patch("haizflow.services.douyin_browser._driver", return_value=driver):
        worker = threading.Thread(target=run)
        worker.start()
        try:
            assert waiting.wait(2)
        finally:
            backend.close()
            worker.join(2)
    assert results == ["cancelled"] and not worker.is_alive() and not backend._thread.is_alive()
    context.close.assert_awaited_once()

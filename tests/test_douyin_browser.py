"""Owned browser, manual verification and SDK lifecycle without real network."""
import asyncio
import os
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from haizflow.services.douyin_browser import (
    DouyinBrowserSession, create_anonymous_state,
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
    body = SimpleNamespace(inner_text=AsyncMock(return_value="抖音"))
    absent = SimpleNamespace(count=AsyncMock(return_value=0))
    page = SimpleNamespace(
        goto=AsyncMock(), reload=AsyncMock(), add_init_script=AsyncMock(),
        locator=Mock(side_effect=lambda selector: body if selector == "body" else absent),
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
    context = SimpleNamespace(pages=[page], cookies=AsyncMock(return_value=cookies), clear_cookies=AsyncMock(),
                              add_cookies=AsyncMock(), close=AsyncMock())
    driver = SimpleNamespace(launch_persistent_context_async=AsyncMock(return_value=context), stop=AsyncMock())
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
            assert Path(options["executable_path"]).name == "chrome.exe"
            assert "1714059" in Path(options["executable_path"]).parts
            assert options["timezone_id"] == "Asia/Shanghai"
            assert not any("fingerprint" in arg for arg in options["args"])
            assert not any("no-sandbox" in arg or "disable-web-security" in arg for arg in options["args"])
            profile = Path(options["user_data_dir"])
            assert profile.name.startswith("guest-") and profile.is_dir()
            driver.launch_persistent_context_async.assert_awaited_once()
            page.goto.assert_awaited_once()
            context.close.assert_not_awaited()
        finally:
            backend.close()
    context.close.assert_awaited_once()
    driver.stop.assert_awaited_once()
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


def test_idle_close_reopens_same_owned_profile_and_browser_options():
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


def test_standard_backend_does_not_import_cloak_or_change_security_environment():
    import inspect
    from haizflow.services import douyin_browser
    source = inspect.getsource(douyin_browser)
    assert "cloakbrowser" not in source.lower()
    assert "CLOAKBROWSER_" not in source
    assert "--no-sandbox" not in source and "--disable-web-security" not in source


def test_failed_browser_launch_stops_playwright_and_removes_temporary_profile():
    driver, context, _ = guest()
    driver.launch_persistent_context_async.side_effect = RuntimeError("launch failed")
    with patch("haizflow.services.douyin_browser._driver", return_value=driver), pytest.raises(RuntimeError, match="launch failed"):
        create_anonymous_state()
    context.close.assert_not_awaited()
    driver.stop.assert_awaited_once()


def login_prompt(*, text="登录后免费畅享高清视频", visible=True, close_count=1):
    close = SimpleNamespace(count=AsyncMock(return_value=close_count), is_visible=AsyncMock(return_value=True), click=AsyncMock())
    header = SimpleNamespace(locator=Mock(return_value=close))
    title = SimpleNamespace(count=AsyncMock(return_value=1), is_visible=AsyncMock(return_value=True),
                            inner_text=AsyncMock(return_value=text), locator=Mock(return_value=header))
    panel = SimpleNamespace(count=AsyncMock(return_value=1), is_visible=AsyncMock(return_value=visible),
                            locator=Mock(return_value=title), wait_for=AsyncMock())
    return panel, close


@pytest.mark.parametrize("text,visible,close_count,expected", [
    ("登录后免费畅享高清视频", True, 1, True),
    ("登录后免费畅享高清视频", False, 1, None),
    ("登录后观看此视频", True, 1, None),
    ("安全验证", True, 1, None),
    ("登录后免费畅享高清视频", True, 0, False),
    ("登录后免费畅享高清视频", True, 2, False),
])
def test_only_known_visible_dismissible_login_invitation_is_closed(text, visible, close_count, expected):
    backend = DouyinBrowserSession()
    panel, close = login_prompt(text=text, visible=visible, close_count=close_count)
    backend._page = SimpleNamespace(locator=Mock(return_value=panel))
    try:
        assert asyncio.run_coroutine_threadsafe(backend._dismiss_optional_login(), backend._loop).result(2) is expected
        if expected is True:
            close.click.assert_awaited_once_with(timeout=1500)
            panel.wait_for.assert_awaited_once_with(state="hidden", timeout=750)
        else:
            close.click.assert_not_awaited()
    finally:
        backend.close()


def test_login_invitation_click_failure_is_soft_and_never_forced():
    backend = DouyinBrowserSession()
    panel, close = login_prompt()
    close.click.side_effect = TimeoutError("opaque browser diagnostic")
    backend._page = SimpleNamespace(locator=Mock(return_value=panel))
    try:
        assert asyncio.run_coroutine_threadsafe(backend._dismiss_optional_login(), backend._loop).result(2) is False
        assert "force" not in close.click.call_args.kwargs
    finally:
        backend.close()


def test_captcha_has_priority_over_login_prompt_dismissal():
    driver, context, page = guest(challenge=True)
    panel, close = login_prompt()
    body = page.locator("body")
    page.locator = Mock(side_effect=lambda selector: body if selector == "body" else panel)
    with patch("haizflow.services.douyin_browser._driver", return_value=driver), \
         patch("haizflow.services.douyin_browser.HUMAN_WAIT_SECONDS", 0), pytest.raises(RuntimeError, match="timed out"):
        create_anonymous_state()
    close.click.assert_not_awaited()
    context.close.assert_awaited_once()


def test_recurring_invitation_has_two_attempt_cap_without_unbounded_retries():
    driver, _, page = guest()
    panel, close = login_prompt()
    body = page.locator("body")
    page.locator = Mock(side_effect=lambda selector: body if selector == "body" else panel)
    with patch("haizflow.services.douyin_browser._driver", return_value=driver), \
         patch.object(DouyinBrowserSession, "_capture", AsyncMock(side_effect=DouyinError(Outcome.SIGNATURE))), \
         patch("haizflow.services.douyin_browser.SDK_WAIT_SECONDS", 0.8), pytest.raises(DouyinError):
        create_anonymous_state()
    assert close.click.await_count == 4  # Two per readiness attempt; one bounded startup retry.


def test_loading_document_timeout_is_unknown_not_absence_of_captcha():
    playwright = pytest.importorskip("playwright.async_api")
    backend = DouyinBrowserSession()
    body = SimpleNamespace(inner_text=AsyncMock(side_effect=playwright.TimeoutError("body is not attached")))
    backend._page = SimpleNamespace(locator=Mock(return_value=body))
    try:
        assert asyncio.run_coroutine_threadsafe(backend._challenge(), backend._loop).result(2) is None
    finally:
        backend.close()


def test_readiness_waits_for_document_before_dismissing_or_signing():
    driver, _, _ = guest()
    with patch("haizflow.services.douyin_browser._driver", return_value=driver), \
         patch.object(DouyinBrowserSession, "_challenge", AsyncMock(side_effect=[None, False])) as challenge, \
         patch.object(DouyinBrowserSession, "_dismiss_optional_login", AsyncMock(return_value=None)) as dismiss:
        state = create_anonymous_state()
        state["backend"].close()
    assert challenge.await_count == 2
    dismiss.assert_awaited_once()


def test_loading_document_wait_has_a_deadline_and_cleans_up_browser():
    driver, context, page = guest()
    with patch("haizflow.services.douyin_browser._driver", return_value=driver), \
         patch.object(DouyinBrowserSession, "_challenge", AsyncMock(return_value=None)), \
         patch("haizflow.services.douyin_browser.SDK_WAIT_SECONDS", 0), pytest.raises(DouyinError) as failure:
        create_anonymous_state()
    assert failure.value.outcome == Outcome.NETWORK
    page.evaluate.assert_not_awaited()
    context.close.assert_awaited_once()


def test_loading_document_wait_remains_cancellable_without_clicking():
    driver, _, _ = guest()
    cancel = threading.Event()
    async def loading(self):
        cancel.set()
        return None
    with patch("haizflow.services.douyin_browser._driver", return_value=driver), \
         patch.object(DouyinBrowserSession, "_challenge", loading), \
         patch.object(DouyinBrowserSession, "_dismiss_optional_login", AsyncMock()) as dismiss, pytest.raises(DownloadCancelled):
        create_anonymous_state(cancel)
    dismiss.assert_not_awaited()


def test_document_reload_after_human_verification_keeps_human_deadline():
    driver, _, _ = guest()
    statuses = []
    with patch("haizflow.services.douyin_browser._driver", return_value=driver), \
         patch.object(DouyinBrowserSession, "_challenge", AsyncMock(side_effect=[True, None, False])), \
         patch("haizflow.services.douyin_browser.SDK_WAIT_SECONDS", 0), \
         patch("haizflow.services.douyin_browser.HUMAN_WAIT_SECONDS", 5):
        state = create_anonymous_state(status_callback=statuses.append)
        state["backend"].close()
    assert statuses == ["Complete verification in the Douyin window.", "Checking the Douyin session"]


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
                        "Checking the Douyin session"]


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


def test_transient_signing_failure_preserves_context_for_same_click_retry():
    driver, context, page = guest()
    with patch("haizflow.services.douyin_browser._driver", return_value=driver):
        state = create_anonymous_state()
        backend = state["backend"]
        try:
            with patch.object(backend, "_capture", AsyncMock(side_effect=ValueError("execution context changed"))):
                with pytest.raises(DouyinError) as failure:
                    backend.sign(DETAIL_PATH, {"aweme_id": "42"}, state["cookies"])
                assert failure.value.outcome == Outcome.NETWORK
            context.close.assert_not_awaited()
            backend.sign(DETAIL_PATH, {"aweme_id": "42"}, state["cookies"], refresh=True)
            driver.launch_persistent_context_async.assert_awaited_once()
            page.reload.assert_awaited_once()
        finally:
            backend.close()


def test_signature_timeout_does_not_destroy_reusable_browser():
    driver, context, _ = guest()
    with patch("haizflow.services.douyin_browser._driver", return_value=driver):
        state = create_anonymous_state()
        backend = state["backend"]
        try:
            with patch.object(backend, "_capture", AsyncMock(side_effect=DouyinError(Outcome.SIGNATURE))), \
                 patch("haizflow.services.douyin_browser.SDK_WAIT_SECONDS", 0), pytest.raises(DouyinError):
                backend.sign(DETAIL_PATH, {"aweme_id": "42"}, state["cookies"])
            context.close.assert_not_awaited()
            backend.sign(DETAIL_PATH, {"aweme_id": "42"}, state["cookies"], refresh=True)
            driver.launch_persistent_context_async.assert_awaited_once()
        finally:
            backend.close()


def test_old_native_export_cannot_overwrite_live_browser_rotation():
    driver, context, page = guest()
    with patch("haizflow.services.douyin_browser._driver", return_value=driver):
        state = create_anonymous_state()
        backend = state["backend"]
        try:
            context.cookies.return_value = [{**state["cookies"][0], "value": "live-rotation"}]
            _, fresh = backend.sign(DETAIL_PATH, {"aweme_id": "42"}, state["cookies"])
            context.add_cookies.assert_not_awaited()
            page.reload.assert_awaited_once()
            assert fresh["cookies"][0]["value"] == "live-rotation"
        finally:
            backend.close()


def test_native_rotation_is_merged_only_if_browser_has_not_changed_it():
    driver, context, page = guest()
    with patch("haizflow.services.douyin_browser._driver", return_value=driver):
        state = create_anonymous_state()
        backend = state["backend"]
        try:
            native = [{**state["cookies"][0], "value": "native-rotation"}]
            backend.sign(DETAIL_PATH, {"aweme_id": "42"}, native)
            context.add_cookies.assert_awaited_once_with(native)
            page.reload.assert_awaited_once()
        finally:
            backend.close()


def test_idle_reopen_restores_latest_browser_cookies_not_old_native_jar():
    driver, context, _ = guest()
    with patch("haizflow.services.douyin_browser._driver", return_value=driver):
        state = create_anonymous_state()
        backend = state["backend"]
        try:
            latest = [{**state["cookies"][0], "value": "late-browser-rotation"}]
            context.cookies.return_value = latest
            asyncio.run_coroutine_threadsafe(backend._close_context(), backend._loop).result(2)
            backend.sign(DETAIL_PATH, {"aweme_id": "42"}, state["cookies"])
            context.add_cookies.assert_awaited_once_with(latest)
        finally:
            backend.close()


def test_plain_sdk_sign_does_not_publish_ready_status():
    driver, _, _ = guest()
    statuses = []
    with patch("haizflow.services.douyin_browser._driver", return_value=driver):
        state = create_anonymous_state(status_callback=statuses.append)
        try:
            state["backend"].sign(DETAIL_PATH, {"aweme_id": "42"}, state["cookies"])
            assert "Douyin session ready" not in statuses
        finally:
            state["backend"].close()


@pytest.mark.parametrize("outcome", [Outcome.SIGNATURE, Outcome.NETWORK])
def test_first_creation_recovers_before_returning_without_second_user_click(outcome):
    driver, context, page = guest()
    original = DouyinBrowserSession._ready
    calls = 0
    async def initial_error(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise DouyinError(outcome)
        return await original(self, *args, **kwargs)
    with patch("haizflow.services.douyin_browser._driver", return_value=driver), \
         patch.object(DouyinBrowserSession, "_ready", initial_error):
        state = create_anonymous_state()
        try:
            assert calls == 2
            page.reload.assert_awaited_once()
            driver.launch_persistent_context_async.assert_awaited_once()
            context.close.assert_not_awaited()
        finally:
            state["backend"].close()


def test_park_closes_window_and_driver_but_keeps_owned_profile_for_explicit_refresh():
    driver, context, page = guest()
    with patch("haizflow.services.douyin_browser._driver", return_value=driver):
        state = create_anonymous_state()
        backend = state["backend"]
        profile = backend._profile_dir.name
        try:
            backend.park()
            context.close.assert_awaited_once()
            driver.stop.assert_awaited_once()
            assert backend._context is None and backend._driver_instance is None
            assert backend._idle is None and not backend._closed
            assert Path(profile).is_dir()
            updated = [{**state["cookies"][0], "value": "native-new-visitor"}]
            backend.sign(DETAIL_PATH, {"aweme_id": "0"}, updated, refresh=True)
            context.add_cookies.assert_awaited_once_with(updated)
            context.clear_cookies.assert_awaited_once()
            assert backend._profile_dir.name == profile
            assert driver.launch_persistent_context_async.await_count == 2
            page.reload.assert_awaited_once()
        finally:
            backend.close()

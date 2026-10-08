"""Explicit owned Douyin guest browser. No personal profile or CAPTCHA solving.

The browser SDK signs requests locally; native curl transport sends them.
The unmodified Chromium component is isolated from users' installed browsers.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import re
import sys
import tempfile
import threading
import time
from contextlib import suppress
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlsplit

from haizflow.services.douyin_classification import DouyinError, Outcome
from haizflow.services.douyin_signing import DETAIL_PATH, POSTS_PATH, SignedRequest
from haizflow.services.douyin_transport import BrowserProfile
from haizflow.vendor.douyin_browser_sdk import CAPTURE_INIT_SCRIPT, FINGERPRINT_READ, SIGN_SCRIPT

CHROMIUM_REVISION = "1714059"
PLAYWRIGHT_VERSION = "1.63.0"
IDLE_SECONDS = 90
HUMAN_WAIT_SECONDS = 300
SDK_WAIT_SECONDS = 25
AUTH_COOKIES = {"sessionid", "sessionid_ss", "sid_guard", "sid_tt"}
logger = logging.getLogger(__name__)
OPTIONAL_LOGIN_TITLE = "登录后免费畅享高清视频"
OPTIONAL_LOGIN_CLOSE = 'div:has(> svg[viewBox="0 0 37 36"] > path[d^="M12.7929 22.2426"])'


def component_directory():
    if getattr(sys, "frozen", False):
        from haizflow.config import RUNTIME_DATA_DIR
        return Path(RUNTIME_DATA_DIR) / "components" / "douyin-chromium"
    return Path(__file__).resolve().parents[3] / "runtime" / "douyin-chromium"


def browser_executable() -> Path:
    # Use only the owned component. No discovery of Chrome/Edge or personal profiles.
    from haizflow.services.douyin_component import component_root
    return component_root() / "chrome-win/chrome.exe"


class _ChromiumDriver:
    def __init__(self):
        self._playwright = None

    async def launch_persistent_context_async(self, **options):
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        return await self._playwright.chromium.launch_persistent_context(**options)

    async def stop(self):
        if self._playwright:
            playwright, self._playwright = self._playwright, None
            await playwright.stop()


def _driver(cancel_event=None, status_callback=None):
    try:
        from importlib.metadata import version
        import playwright.async_api  # noqa: F401
    except ImportError:
        raise RuntimeError("The optional Douyin browser component is not installed.") from None
    if version("playwright") != PLAYWRIGHT_VERSION:
        raise RuntimeError("The Douyin browser component version is not supported.")
    from haizflow.services.douyin_component import MISSING_MESSAGE, installed
    if not installed():
        raise RuntimeError(MISSING_MESSAGE)
    return _ChromiumDriver()


class DouyinBrowserSession:
    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._operations = asyncio.Lock()
        self._thread = threading.Thread(target=self._run, name="douyin-sdk", daemon=True)
        self._context = self._page = self._profile_dir = self._idle = None
        self._driver_instance = None
        self._state = None
        self._parked_for_native = False
        self._status_callback = None
        self._closed = False
        self._pending = set()
        self._pending_lock = threading.Lock()
        self._thread.start()

    def _run(self):
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()
            if pending:
                self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            self._loop.close()

    def _submit(self, coroutine, cancel_event=None, timeout=45):
        from haizflow.services.douyin_adapter import _check_cancel
        from haizflow.services.video_download import DownloadCancelled
        with self._pending_lock:
            if self._closed:
                coroutine.close()
                raise RuntimeError("The Douyin browser session is closed. Create a new session.")
            future = asyncio.run_coroutine_threadsafe(self._operate(coroutine), self._loop)
            self._pending.add(future)
        deadline = time.monotonic() + timeout
        try:
            while True:
                _check_cancel(cancel_event)
                if time.monotonic() >= deadline:
                    raise RuntimeError("Creating the Douyin session timed out. Try again later.")
                try:
                    return future.result(timeout=0.1)
                except concurrent.futures.TimeoutError:
                    if future.done():
                        return future.result()
        except BaseException as exc:
            future.cancel()
            # A rejected signature/loading page is recoverable in this profile.
            # Do not close Chromium on every bounded retry. Cancellation/fatal
            # errors still release the owned process and driver promptly.
            if not self._closed and not isinstance(exc, DouyinError):
                with suppress(Exception):
                    asyncio.run_coroutine_threadsafe(self._close_context(), self._loop).result(timeout=7)
            if isinstance(exc, concurrent.futures.CancelledError):
                raise DownloadCancelled("Video download cancelled.") from None
            if isinstance(exc, (DouyinError, RuntimeError, DownloadCancelled, KeyboardInterrupt)):
                raise
            logger.info("douyin browser request_error=%s classification=network_transient", type(exc).__name__)
            raise DouyinError(Outcome.NETWORK) from None
        finally:
            with self._pending_lock:
                self._pending.discard(future)

    async def _operate(self, coroutine):
        started = False
        try:
            async with self._operations:
                started = True
                return await coroutine
        finally:
            if not started:
                coroutine.close()

    async def _close_context(self):
        async with self._operations:
            await self._dispose_context()

    async def _dispose_context(self):
        if self._idle:
            self._idle.cancel()
            self._idle = None
        context, self._context, self._page = self._context, None, None
        if context:
            # Preserve late guest-cookie rotations before idle disposal, too.
            if self._state:
                with suppress(Exception):
                    async with asyncio.timeout(1):
                        cookies = await context.cookies(["https://www.douyin.com/"])
                        if not any(c["name"] in AUTH_COOKIES for c in cookies):
                            self._state = {**self._state, "cookies": cookies}
            with suppress(Exception):
                async with asyncio.timeout(5):
                    await context.close()
        driver, self._driver_instance = self._driver_instance, None
        if driver:
            with suppress(Exception):
                async with asyncio.timeout(5):
                    await driver.stop()

    def _arm_idle(self):
        if self._idle:
            self._idle.cancel()
        if not self._closed and self._context:
            self._idle = self._loop.call_later(
                IDLE_SECONDS, lambda: self._loop.create_task(self._close_context()))

    async def _launch(self, cookies=(), cancel_event=None):
        if self._context:
            return
        if self._profile_dir is None:
            directory = component_directory() / "profiles"
            directory.mkdir(parents=True, exist_ok=True)
            self._profile_dir = tempfile.TemporaryDirectory(prefix="guest-", dir=directory)
        self._driver_instance = await asyncio.to_thread(_driver, cancel_event, self._status_callback)
        self._context = await self._driver_instance.launch_persistent_context_async(
            executable_path=str(browser_executable()), user_data_dir=self._profile_dir.name,
            headless=False, timeout=15000, locale="zh-CN", timezone_id="Asia/Shanghai",
            chromium_sandbox=True, no_viewport=True,
            args=["--no-first-run", "--no-default-browser-check", "--disable-background-networking"])
        if cookies:
            if self._parked_for_native:
                # Explicit refresh adopts the current verified native jar,
                # including deletions, in this owned profile only.
                await self._context.clear_cookies(domain=re.compile(r"(^|\.)douyin\.com$"))
            await self._context.add_cookies(cookies)
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        await self._page.add_init_script(CAPTURE_INIT_SCRIPT)
        await self._page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=20000)

    async def _challenge(self) -> bool | None:
        try:
            body = (await self._page.locator("body").inner_text(timeout=1500))[:4096].lower()
        except Exception as exc:
            from playwright.async_api import TimeoutError as BrowserTimeoutError
            if isinstance(exc, BrowserTimeoutError):
                # A redirect/loading document is not evidence of no CAPTCHA.
                # The caller waits without signing or dismissing anything.
                return None
            raise
        for frame in self._page.frames:
            if frame == self._page.main_frame:
                continue
            if "captcha" in frame.url.lower() or "verifycenter" in frame.url.lower():
                element = await frame.frame_element()
                bounds = await element.bounding_box()
                # A hidden security SDK iframe is not an active human challenge.
                if bounds and bounds["width"] > 20 and bounds["height"] > 20:
                    return True
        return any(marker in body for marker in (
            "请完成验证", "安全验证", "拖动滑块", "验证后继续", "complete verification", "verify you are human"))

    async def _dismiss_optional_login(self) -> bool | None:
        """Click the site's own X on its known dismissible invitation only.

        Unknown/mandatory login, CAPTCHA and hidden/ambiguous controls stay intact.
        No DOM removal, Escape-key fallback, forced click or authentication occurs.
        None means no invitation; bool means one bounded dismissal was attempted.
        """
        try:
            panel = self._page.locator("#douyin_login_comp_flat_panel")
            if await panel.count() != 1 or not await panel.is_visible():
                return None
            title = panel.locator("#douyin_login_comp_flat_panel_title")
            if (await title.count() != 1 or not await title.is_visible()
                    or (await title.inner_text(timeout=750)).strip() != OPTIONAL_LOGIN_TITLE):
                return None
            # The observed header contains the title and exactly one X icon.
            # Match its shape, not obfuscated class names or a page-wide close button.
            close = title.locator("..").locator(OPTIONAL_LOGIN_CLOSE)
            if await close.count() != 1 or not await close.is_visible():
                return False
            await close.click(timeout=1500)  # Normal hit testing: never force through an overlay.
            await panel.wait_for(state="hidden", timeout=750)
            logger.info("douyin browser optional_login_prompt=closed")
            return True
        except Exception as exc:
            # A changing page must not crash UI or expose browser request/session data.
            logger.info("douyin browser optional_login_prompt=not_closed error_type=%s", type(exc).__name__)
            return False

    async def _snapshot(self):
        cookies = await self._context.cookies(["https://www.douyin.com/"])
        if any(cookie["name"] in AUTH_COOKIES for cookie in cookies):
            raise RuntimeError("The Douyin browser session must remain anonymous.")
        fingerprint = await self._page.evaluate(FINGERPRINT_READ)
        BrowserProfile.from_browser(fingerprint)
        return {"cookies": cookies, "fingerprint": fingerprint}

    async def _capture(self, path, params):
        from haizflow.services.douyin_adapter import _base_params
        if path not in {DETAIL_PATH, POSTS_PATH}:
            raise ValueError("Unsupported Douyin signing endpoint.")
        state = await self._snapshot()
        profile = BrowserProfile.from_browser(state["fingerprint"])
        values = {**_base_params(profile), **{str(k): str(v) for k, v in params.items()}}
        raw = "https://www.douyin.com" + path + "?" + urlencode(values, quote_via=quote, safe="*-._")
        match = {k: v for k, v in values.items() if k in {"aweme_id", "sec_user_id", "max_cursor"}}
        signed = await self._page.evaluate(SIGN_SCRIPT, {"url": raw, "match": match})
        if not isinstance(signed, str) or len(signed) > 32768:
            raise DouyinError(Outcome.SIGNATURE)
        parsed = urlsplit(signed)
        query = parse_qs(parsed.query)
        if (parsed.scheme != "https" or parsed.netloc != "www.douyin.com" or parsed.path != path
                or any(query.get(k) != [v] for k, v in match.items())
                or any(len(query.get(k, [])) != 1 or not query[k][0] for k in (
                    "a_bogus", "uifid", "timestamp", "x-secsdk-web-signature"))):
            raise DouyinError(Outcome.SIGNATURE)
        headers = {"uifid": query["uifid"][0], "x-secsdk-web-expire": query["timestamp"][0],
                   "x-secsdk-web-signature": query["x-secsdk-web-signature"][0]}
        self._state = await self._snapshot()
        # Preserve EXACT SDK bytes/order. Never append msToken after signing.
        return SignedRequest(signed, headers, "browser-sdk"), self._state

    async def _ready(self, path, params, cancel_event=None, status_callback=None, human=False):
        from haizflow.services.douyin_adapter import _check_cancel
        deadline = time.monotonic() + SDK_WAIT_SECONDS
        human_deadline = time.monotonic() + HUMAN_WAIT_SECONDS
        delay, waiting, errors, prompt_attempts = 0.25, False, 0, 0
        while True:
            _check_cancel(cancel_event)
            challenge = await self._challenge()
            if challenge is None:
                # Human verification may navigate/reload the document. Preserve
                # its human deadline until the page can be examined again.
                if time.monotonic() >= (human_deadline if waiting else deadline):
                    if waiting:
                        raise RuntimeError("Creating the Douyin session timed out. Try again later.")
                    logger.info("douyin browser readiness=page_loading_timeout")
                    raise DouyinError(Outcome.NETWORK)
                await asyncio.sleep(delay)
                delay = min(2.5, delay * 1.6)
                continue
            if challenge:
                if not human:
                    raise DouyinError(Outcome.CHALLENGE)
                if not waiting and status_callback:
                    status_callback("Complete verification in the Douyin window.")
                waiting = True
                if time.monotonic() >= human_deadline:
                    raise RuntimeError("Creating the Douyin session timed out. Try again later.")
                await asyncio.sleep(0.5)
                continue
            if waiting:
                waiting = False
                deadline = time.monotonic() + SDK_WAIT_SECONDS
                if status_callback:
                    status_callback("Checking the Douyin session")
            if prompt_attempts < 2:
                prompt_result = await self._dismiss_optional_login()
                if prompt_result is not None:
                    prompt_attempts += 1
                _check_cancel(cancel_event)
            try:
                return await self._capture(path, params)
            except DouyinError as exc:
                if exc.outcome != Outcome.SIGNATURE:
                    raise
                errors = 0
            except Exception as exc:
                if isinstance(exc, RuntimeError):
                    raise
                errors += 1
                if errors >= 3:
                    logger.info("douyin browser sdk_error=%s classification=network_transient", type(exc).__name__)
                    raise DouyinError(Outcome.NETWORK) from None
            if time.monotonic() >= deadline:
                raise DouyinError(Outcome.SIGNATURE)
            await asyncio.sleep(delay)
            delay = min(2.5, delay * 1.6)

    async def _bootstrap(self, cancel_event, status_callback):
        # Initial SDK startup needs the same bounded recovery as later requests.
        # Keep the one owned profile/context; never require a second UI click.
        for attempt in range(1, 3):
            try:
                if not self._context:
                    await self._launch(cancel_event=cancel_event)
                elif attempt > 1:
                    await self._page.reload(wait_until="domcontentloaded", timeout=20000)
                _, state = await self._ready(DETAIL_PATH, {"aweme_id": "0"}, cancel_event, status_callback, human=True)
                self._arm_idle()
                return state
            except DouyinError as exc:
                outcome = exc.outcome
                if outcome not in {Outcome.SIGNATURE, Outcome.NETWORK, Outcome.RISK}:
                    raise
            except Exception as exc:
                # Navigation/document replacement errors are transient; missing
                # components, unsupported profiles and anonymous-only errors are not.
                if not type(exc).__module__.startswith("playwright."):
                    raise
                outcome = Outcome.NETWORK
            logger.info("douyin browser bootstrap_attempt=%d classification=%s retry=%s", attempt, outcome.value, attempt < 2)
            if attempt == 2:
                raise DouyinError(outcome)
            if status_callback:
                status_callback("Checking the Douyin session")
            if self._page is None or (hasattr(self._page, "is_closed") and self._page.is_closed()):
                await self._dispose_context()

    def park(self):
        """Close the owned window/driver after native verification, retain profile.

        Only the explicit create/refresh action may use this backend again.
        """
        self._submit(self._dispose_context(), timeout=15)
        self._parked_for_native = True
        logger.info("douyin browser closed_after_native_verification=True")

    def open(self, cancel_event=None, status_callback=None):
        self._status_callback = status_callback
        return self._submit(self._bootstrap(cancel_event, status_callback), cancel_event, HUMAN_WAIT_SECONDS + 45)

    async def _sign(self, path, params, cookies, cancel_event, refresh):
        if self._idle:
            self._idle.cancel()
        try:
            if not self._context:
                # Restore the latest browser snapshot, not a possibly older
                # native jar. Reopening after idle keeps the same profile.
                await self._launch(cookies if self._parked_for_native else (self._state or {}).get("cookies", cookies), cancel_event)
                self._parked_for_native = False
            elif cookies:
                refresh = await self._sync_native_cookies(cookies) or refresh
            if refresh:
                if self._status_callback:
                    self._status_callback("Checking the Douyin session")
                await self._page.reload(wait_until="domcontentloaded", timeout=20000)
            # SDK availability is not proof that the metadata endpoint accepted
            # the request. Only the adapter may publish successful readiness.
            return await self._ready(path, params, cancel_event, self._status_callback, human=True)
        finally:
            self._arm_idle()

    async def _sync_native_cookies(self, cookies):
        """Merge actual native rotations, never replay an unchanged old export."""
        def key(cookie):
            return cookie["name"], cookie.get("domain", ""), cookie.get("path", "/")

        baseline = {key(c): c["value"] for c in (self._state or {}).get("cookies", [])}
        current = {key(c): c["value"] for c in await self._context.cookies(["https://www.douyin.com/"])}
        changed = [c for c in cookies if c["name"] not in AUTH_COOKIES
                   and c["value"] != baseline.get(key(c))
                   and current.get(key(c)) == baseline.get(key(c))]
        if changed:
            await self._context.add_cookies(changed)
        # Visitor identity is cached by the SDK at document load. A late browser
        # rotation or a genuine native update requires one reload, not a new profile.
        names = {"UIFID", "UIFID_TEMP", "uifid", "s_v_web_id"}
        return (any(key_[0] in names and value != baseline.get(key_) for key_, value in current.items())
                or any(c["name"] in names for c in changed))

    def sign(self, path, params, cookies, cancel_event=None, *, refresh=False):
        return self._submit(self._sign(path, params, cookies, cancel_event, refresh),
                            cancel_event, HUMAN_WAIT_SECONDS + 45)

    def close(self):
        with self._pending_lock:
            if self._closed:
                return
            self._closed = True
            for future in self._pending:
                future.cancel()
        with suppress(Exception):
            asyncio.run_coroutine_threadsafe(self._close_context(), self._loop).result(timeout=7)
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2)
        if self._profile_dir and not self._thread.is_alive():
            with suppress(OSError):
                self._profile_dir.cleanup()


def create_anonymous_state(cancel_event=None, status_callback=None):
    backend = DouyinBrowserSession()
    try:
        return {**backend.open(cancel_event, status_callback), "backend": backend}
    except BaseException:
        backend.close()
        raise

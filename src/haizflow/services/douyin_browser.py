"""Explicit owned Douyin guest browser. No personal profile or CAPTCHA solving.

The browser SDK signs requests locally; native curl transport sends them.
The optional Cloak binary is separately licensed and never bundled here.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import os
import secrets
import sys
import tempfile
import threading
import time
from contextlib import contextmanager, suppress
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlsplit

from haizflow.services.douyin_classification import DouyinError, Outcome
from haizflow.services.douyin_signing import DETAIL_PATH, POSTS_PATH, SignedRequest
from haizflow.services.douyin_transport import BrowserProfile
from haizflow.vendor.douyin_browser_sdk import CAPTURE_INIT_SCRIPT, FINGERPRINT_READ, SIGN_SCRIPT

CLOAK_VERSION = "146.0.7680.177.5"
IDLE_SECONDS = 90
HUMAN_WAIT_SECONDS = 300
SDK_WAIT_SECONDS = 25
AUTH_COOKIES = {"sessionid", "sessionid_ss", "sid_guard", "sid_tt"}


def component_directory():
    if getattr(sys, "frozen", False):
        from haizflow.config import RUNTIME_DATA_DIR
        return Path(RUNTIME_DATA_DIR) / "components" / "douyin-cloak"
    return Path(__file__).resolve().parents[3] / "runtime" / "douyin-cloak"


@contextmanager
def _component_environment():
    # Do not consume a personal Cloak license/profile or ambient binary override.
    values = {"CLOAKBROWSER_CACHE_DIR": str(component_directory()),
              "CLOAKBROWSER_VERSION": CLOAK_VERSION, "CLOAKBROWSER_AUTO_UPDATE": "false",
              "CLOAKBROWSER_LICENSE_KEY": "", "CLOAKBROWSER_BINARY_PATH": None,
              "CLOAKBROWSER_DOWNLOAD_URL": None, "CLOAKBROWSER_SKIP_CHECKSUM": ""}
    previous = {key: os.environ.get(key) for key in values}
    for key, value in values.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _driver():
    try:
        import cloakbrowser
        from cloakbrowser.config import get_binary_path
    except ImportError:
        raise RuntimeError("The optional Douyin browser component is not installed.") from None
    if cloakbrowser.__version__ != "0.5.10":
        raise RuntimeError("The Douyin browser component version is not supported.")
    # No automatic binary download inside a request or UI worker.
    if not get_binary_path(CLOAK_VERSION).is_file():
        raise RuntimeError("The optional Douyin browser component is not installed.")
    return cloakbrowser


class DouyinBrowserSession:
    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._operations = asyncio.Lock()
        self._thread = threading.Thread(target=self._run, name="douyin-sdk", daemon=True)
        self._context = self._page = self._profile_dir = self._idle = None
        self._state = None
        self._status_callback = None
        self._closed = False
        self._pending = set()
        self._pending_lock = threading.Lock()
        self._seed = secrets.randbelow(2**31 - 1) + 1
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
            if not self._closed:
                with suppress(Exception):
                    asyncio.run_coroutine_threadsafe(self._close_context(), self._loop).result(timeout=7)
            if isinstance(exc, concurrent.futures.CancelledError):
                raise DownloadCancelled("Video download cancelled.") from None
            if isinstance(exc, (DouyinError, RuntimeError, DownloadCancelled, KeyboardInterrupt)):
                raise
            raise RuntimeError("The Douyin browser session could not complete the request.") from None
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
            with suppress(Exception):
                async with asyncio.timeout(5):
                    await context.close()

    def _arm_idle(self):
        if self._idle:
            self._idle.cancel()
        if not self._closed and self._context:
            self._idle = self._loop.call_later(
                IDLE_SECONDS, lambda: self._loop.create_task(self._close_context()))

    async def _launch(self, cookies=()):
        if self._context:
            return
        if self._profile_dir is None:
            directory = component_directory() / "profiles"
            directory.mkdir(parents=True, exist_ok=True)
            self._profile_dir = tempfile.TemporaryDirectory(prefix="guest-", dir=directory)
        with _component_environment():
            self._context = await _driver().launch_persistent_context_async(
                user_data_dir=self._profile_dir.name, headless=False, timeout=15000,
                locale="zh-CN", timezone="Asia/Shanghai", geoip=False, humanize=False,
                stealth_args=False, chromium_sandbox=True, browser_version=CLOAK_VERSION,
                args=[f"--fingerprint={self._seed}", "--fingerprint-platform=windows",
                      "--no-first-run", "--no-default-browser-check", "--disable-background-networking"])
        if cookies:
            await self._context.add_cookies(cookies)
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        await self._page.add_init_script(CAPTURE_INIT_SCRIPT)
        await self._page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=20000)

    async def _challenge(self):
        body = (await self._page.locator("body").inner_text(timeout=1500))[:4096].lower()
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
        delay, waiting, errors = 0.25, False, 0
        while True:
            _check_cancel(cancel_event)
            if await self._challenge():
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
            try:
                return await self._capture(path, params)
            except DouyinError:
                errors = 0
            except Exception as exc:
                if isinstance(exc, RuntimeError):
                    raise
                errors += 1
                if errors >= 3:
                    raise RuntimeError("The Douyin browser session could not complete the request.") from None
            if time.monotonic() >= deadline:
                raise DouyinError(Outcome.SIGNATURE)
            await asyncio.sleep(delay)
            delay = min(2.5, delay * 1.6)

    async def _bootstrap(self, cancel_event, status_callback):
        await self._launch()
        _, state = await self._ready(DETAIL_PATH, {"aweme_id": "0"}, cancel_event, status_callback, human=True)
        self._arm_idle()
        return state

    def open(self, cancel_event=None, status_callback=None):
        self._status_callback = status_callback
        return self._submit(self._bootstrap(cancel_event, status_callback), cancel_event, HUMAN_WAIT_SECONDS + 45)

    async def _sign(self, path, params, cookies, cancel_event, refresh):
        if self._idle:
            self._idle.cancel()
        try:
            if not self._context:
                await self._launch(cookies)
            elif cookies:
                # SDK caches visitor identity at page load; reload only if it changed.
                names = {"UIFID", "UIFID_TEMP", "uifid", "s_v_web_id"}
                before = {c["name"]: c["value"] for c in (self._state or {}).get("cookies", []) if c["name"] in names}
                after = {c["name"]: c["value"] for c in cookies if c["name"] in names}
                await self._context.add_cookies(cookies)
                if refresh or before != after:
                    await self._page.reload(wait_until="domcontentloaded", timeout=20000)
            result = await self._ready(path, params, cancel_event, self._status_callback, human=True)
            if self._status_callback:
                self._status_callback("Douyin session ready")
            return result
        finally:
            self._arm_idle()

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

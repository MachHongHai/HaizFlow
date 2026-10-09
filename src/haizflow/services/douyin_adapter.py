"""One small local Douyin session, shared by video inspection and channel scans.

Architecture inspired by Evil0ctal/Douyin_TikTok_Download_API at
4f0bed8483c35a980315d9c7b3a1d4a1119ad2b2. No RPC, database, pool or service.
"""
from __future__ import annotations

import http.cookiejar
import json
import logging
import re
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from haizflow.services.douyin_classification import DouyinError, Outcome, Verdict, classify
from haizflow.services.douyin_signing import DETAIL_PATH, POSTS_PATH, DouyinSigner
from haizflow.services.douyin_transport import BrowserProfile, DouyinTransport, validate_douyin_address

logger = logging.getLogger(__name__)


class ProfileCandidates(list):
    """Usable pages with an explicit incomplete-scan notice, never false EOF."""

    warning = ""


def _check_cancel(cancel_event):
    if cancel_event and cancel_event.is_set():
        from haizflow.services.video_download import DownloadCancelled
        raise DownloadCancelled("Video download cancelled.")


@contextmanager
def _session_guard(lock, cancel_event):
    while not lock.acquire(timeout=0.1):
        _check_cancel(cancel_event)
    try:
        _check_cancel(cancel_event)
        yield
    finally:
        lock.release()


class DouyinSession:
    def __init__(self, transport_factory=DouyinTransport, profile=None, *, browser_state=None):
        self.profile = BrowserProfile.from_browser(browser_state["fingerprint"]) if browser_state else profile or BrowserProfile()
        self.transport_factory = transport_factory
        self.transport = transport_factory(self.profile)
        self.generation = 1
        self.ready = False
        self.lock = threading.RLock()
        self.cookie_file_identity = None
        self.browser = None
        self.native_verified = False
        if browser_state:
            try:
                self.transport.import_cookies(browser_state["cookies"])
                if not any(self.transport.cookies.get(n) for n in ("UIFID_TEMP", "UIFID", "uifid")):
                    raise DouyinError(Outcome.SIGNATURE)
            except BaseException:
                self.transport.close()
                raise

    def warmup(self, cancel_event=None, *, refresh=False):
        if self.ready and not refresh:
            return
        response = self.transport.get("https://www.douyin.com/", cancel_event=cancel_event)
        # An HTML app shell is normal here; do not interpret it as detail JSON.
        if response.status >= 500:
            raise DouyinError(Outcome.NETWORK)
        if response.status == 429:
            raise DouyinError(Outcome.RATE_LIMIT)
        if response.status >= 400:
            raise DouyinError(Outcome.RISK)
        self.ready = True
        if refresh:
            self.generation += 1

    def use_browser_state(self, state):
        profile = BrowserProfile.from_browser(state["fingerprint"])
        replacement = self.transport_factory(profile)
        try:
            replacement.import_cookies(state["cookies"])
            if not any(replacement.cookies.get(n) for n in ("UIFID_TEMP", "UIFID", "uifid")):
                raise DouyinError(Outcome.SIGNATURE)
        except Exception:
            replacement.close()
            raise
        old = self.transport
        self.profile = profile
        self.transport = replacement
        self.ready = True
        self.generation += 1
        old.close()

    def browser_cookies(self):
        return [{"name": c.name, "value": c.value, "domain": c.domain, "path": c.path,
                 "secure": c.secure, "httpOnly": c.has_nonstandard_attr("HttpOnly"),
                 **({"expires": c.expires} if c.expires else {})} for c in self.transport.cookie_jar
                if not c.is_expired() and (c.domain.lstrip(".") == "douyin.com" or c.domain.endswith(".douyin.com"))]

    def close_browser(self):
        browser, self.browser = self.browser, None
        if browser:
            browser.close()


def _base_params(profile):
    return {
        "device_platform": "webapp", "aid": "6383", "channel": "channel_pc_web",
        "pc_client_type": "1", "version_code": "290100", "version_name": "29.1.0",
        "cookie_enabled": "true", "screen_width": str(profile.width), "screen_height": str(profile.height),
        "browser_language": profile.language, "browser_platform": profile.platform,
        "browser_name": "Chrome", "browser_version": profile.version, "browser_online": "true",
        "engine_name": "Blink", "engine_version": profile.version, "os_name": "Windows", "os_version": "10",
        "cpu_core_num": str(profile.cores), "device_memory": str(profile.memory), "platform": "PC",
        "downlink": "10", "effective_type": "4g", "round_trip_time": "0", "update_version_code": "170400",
    }


class DouyinAdapter:
    def __init__(self, session=None, signer=None):
        self.session = session or DouyinSession()
        self.signer = signer or DouyinSigner()
        self._status_callback = None
        self._profile_pages = {}
        self._posts_cooldown_until = 0.0

    def _request_succeeded(self):
        self.session.ready = True
        if self._status_callback:
            try:
                self._status_callback("Douyin request succeeded")
            except RuntimeError:
                # A UI owner may have been destroyed during shutdown.
                pass

    def resolve(self, url, cancel_event=None):
        validate_douyin_address(url)
        if (urlsplit(url).hostname or "").lower() != "v.douyin.com":
            return url
        response = self.session.transport.get(url, cancel_event=cancel_event)
        if response.status >= 400:
            raise DouyinError(Outcome.UNAVAILABLE if response.status in {404, 410} else Outcome.RISK)
        return validate_douyin_address(response.url)

    def _api(self, path, params, cancel_event=None, *, session_probe=False, continuation=False):
        last = Verdict(Outcome.NETWORK, True)
        signing_failed = False
        for attempt in range(1, 4):
            _check_cancel(cancel_event)
            response = None
            mode = "not_signed"
            try:
                if self.session.browser and not self.session.native_verified:
                    refresh = attempt == 2 and (last.outcome in ({Outcome.SIGNATURE} if continuation else
                                                               {Outcome.RISK, Outcome.SIGNATURE})
                                               or (last.outcome == Outcome.NETWORK and signing_failed))
                    signed, state = self.session.browser.sign(
                        path, params, self.session.browser_cookies(), cancel_event, refresh=refresh)
                    if refresh:
                        self.session.generation += 1
                    if BrowserProfile.from_browser(state["fingerprint"]) != self.session.profile:
                        self.session.use_browser_state(state)
                    else:
                        self.session.transport.import_cookies(state["cookies"], replace=True)
                else:
                    self.session.warmup(cancel_event, refresh=(attempt == 2 and last.outcome in (
                        {Outcome.SIGNATURE} if continuation else {Outcome.RISK, Outcome.SIGNATURE})))
                    signed = self.signer.sign(path, {**_base_params(self.session.profile), **params},
                                              self.session.transport.cookies, self.session.profile)
                mode = signed.mode
                response = self.session.transport.get(signed.url, signed.headers, cancel_event)
                last = classify(response, list_endpoint=path == POSTS_PATH)
                # Probe only: Douyin's structured "unknown aweme" response to
                # ID 0 verifies endpoint/identity handling without reading a
                # random user's video. HTTP 200/empty HTML is NOT enough.
                if session_probe and path == DETAIL_PATH and params == {"aweme_id": "0"} and response.status == 200:
                    try:
                        payload = json.loads(response.body)
                    except (ValueError, RecursionError):
                        payload = None
                    if (last.outcome == Outcome.METADATA and isinstance(payload, dict)
                            and type(payload.get("status_code")) is int
                            and payload["status_code"] == 5 and "aweme_detail" in payload
                            and payload["aweme_detail"] is None):
                        last = Verdict(Outcome.SUCCESS, payload=payload)
            except DouyinError as exc:
                last = Verdict(exc.outcome, exc.outcome in {Outcome.NETWORK, Outcome.RISK, Outcome.RATE_LIMIT,
                                                           Outcome.SIGNATURE})
            except OSError:
                last = Verdict(Outcome.NETWORK, True)
            except ValueError:
                last = Verdict(Outcome.UPSTREAM)
            except Exception as exc:
                # curl_cffi does not inherit OSError. Keep programming errors visible.
                if not type(exc).__module__.startswith("curl_cffi"):
                    raise
                last = Verdict(Outcome.NETWORK, True)
            retry = last.retryable and attempt < 3
            signing_failed = mode == "not_signed"
            logger.info("douyin attempt=%d endpoint=%s generation=%d transport=%s signer=%s "
                        "classification=%s http=%d bytes=%d retry=%s", attempt, path,
                        self.session.generation, self.session.profile.transport_mode, mode,
                        last.outcome.value, response.status if response else 0,
                        len(response.body) if response else 0, retry)
            if last.outcome == Outcome.SUCCESS:
                if path == POSTS_PATH and not session_probe:
                    self._request_succeeded()
                return last.payload
            if not retry:
                break
            from haizflow.services.video_download import _wait_for_retry
            delay = 0.6 * attempt
            if continuation and last.outcome in {Outcome.RISK, Outcome.RATE_LIMIT}:
                delay = 6.0 * attempt
            if last.outcome == Outcome.RATE_LIMIT:
                value = str(response.headers.get("retry-after", "")) if response else ""
                delay = max(delay, min(8.0, max(1.0, float(value))) if value.isdigit() else 2.0)
            _wait_for_retry(cancel_event, delay)
        invalid_session = last.outcome in {Outcome.SIGNATURE, Outcome.CHALLENGE} or (
            last.outcome == Outcome.RISK and not continuation)
        if self.session.browser and invalid_session:
            self.session.ready = False
            if self._status_callback:
                try:
                    self._status_callback("Douyin session needs refresh")
                except RuntimeError:
                    pass
        # A continuation throttle is not evidence that the working guest jar
        # expired. Do not instruct the user to create another browser session.
        raise DouyinError(Outcome.RATE_LIMIT if continuation and last.outcome == Outcome.RISK else last.outcome)

    def inspect(self, url, cancel_event=None):
        from haizflow.services.douyin_video import share_page_detail, video_id_from_url

        with _session_guard(self.session.lock, cancel_event):
            video_id = video_id_from_url(self.resolve(url, cancel_event))
            try:
                detail = self._api(DETAIL_PATH, {"aweme_id": video_id}, cancel_event)["aweme_detail"]
            except DouyinError as exc:
                if exc.outcome not in {Outcome.RISK, Outcome.SIGNATURE, Outcome.UPSTREAM}:
                    raise
                # One controlled first-party fallback; exactly the same UA, jar and TLS.
                response = self.session.transport.get(
                    f"https://www.iesdouyin.com/share/video/{video_id}/", cancel_event=cancel_event)
                detail = share_page_detail(response.body.decode("utf-8", "replace"), video_id)
                fallback = Verdict(Outcome.SUCCESS) if response.status == 200 and detail else classify(response)
                logger.info("douyin attempt=4 endpoint=/share/video/ generation=%d transport=%s signer=none "
                            "classification=%s http=%d bytes=%d retry=False",
                            self.session.generation, self.session.profile.transport_mode,
                            fallback.outcome.value, response.status, len(response.body))
                if response.status != 200 or not detail:
                    if fallback.outcome in {Outcome.UNAVAILABLE, Outcome.CHALLENGE}:
                        raise DouyinError(fallback.outcome) from None
                    raise exc from None
            if str(detail.get("aweme_id")) != video_id:
                raise DouyinError(Outcome.METADATA)
            if detail.get("images") or not isinstance(detail.get("video"), dict):
                raise DouyinError(Outcome.UNAVAILABLE)
            self._request_succeeded()
            return detail

    def profile_posts(self, url, *, limit=20, cancel_event=None, progress_callback=None):
        from haizflow.services.douyin_channel_worker import _candidate

        with _session_guard(self.session.lock, cancel_event):
            resolved = self.resolve(url, cancel_event)
            match = re.fullmatch(r"/user/([A-Za-z0-9_-]+)/?", urlsplit(resolved).path)
            if not match:
                raise ValueError("Paste a link to a Douyin profile.")
            candidates, seen, cursor, channel_name = [], set(), "0", ""
            # Count raw posts, including photos, so a profile full of photos cannot
            # trigger an unbounded scan. The UI's 'all' scope has a desktop cap.
            scanned = 0
            budget = min(max(int(limit or 1000), 1), 1000)
            cache_key = (match[1], self.session.generation)
            cached = self._profile_pages.get(cache_key)
            if budget > 20 and cached and cached["scanned"] <= budget and time.monotonic() - cached["updated"] < 300:
                candidates = list(cached["candidates"])
                seen = {row["remote_video_id"] for row in candidates}
                cursor, scanned, channel_name = cached["cursor"], cached["scanned"], cached["name"]
                if cached["complete"]:
                    return channel_name, candidates
            while scanned < budget:
                if scanned or self._posts_cooldown_until > time.monotonic():
                    # Popular scans read multiple pages. A burst of continuation
                    # requests can be throttled even with a valid guest identity.
                    from haizflow.services.video_download import _wait_for_retry
                    if progress_callback:
                        progress_callback(min(95, round(scanned * 95 / budget)), "Đang chờ Douyin cho phép quét tiếp…")
                    _wait_for_retry(cancel_event, max(3.0 if scanned else 0,
                                                     self._posts_cooldown_until - time.monotonic()))
                try:
                    page = self._api(POSTS_PATH, {
                        "sec_user_id": match[1], "max_cursor": cursor, "count": str(min(20, budget - scanned)),
                        "publish_video_strategy_type": "2", "from_user_page": "1", "locate_query": "false",
                        "need_time_list": "1", "show_live_replay_strategy": "1", "time_list_query": "0",
                        "pc_libra_divert": "Windows", "whale_cut_token": "",
                    }, cancel_event, continuation=bool(scanned))
                except DouyinError as exc:
                    if exc.outcome not in {Outcome.RATE_LIMIT, Outcome.RISK, Outcome.NETWORK} or not candidates:
                        raise
                    self._posts_cooldown_until = time.monotonic() + 30
                    partial = ProfileCandidates(candidates)
                    partial.warning = (f"Đã quét {scanned}/{budget} bài đăng. Douyin tạm giới hạn quét tiếp; "
                                       "danh sách được xếp theo dữ liệu đã quét. Chờ một lúc rồi Quét lại để tiếp tục.")
                    return channel_name, partial
                for item in page["aweme_list"]:
                    if scanned >= budget:
                        break
                    _check_cancel(cancel_event)
                    scanned += 1
                    if not isinstance(item, dict):
                        continue
                    candidate = _candidate(item)
                    if candidate and candidate["remote_video_id"] not in seen:
                        seen.add(candidate["remote_video_id"])
                        candidates.append(candidate)
                        channel_name = channel_name or candidate["uploader"]
                if progress_callback:
                    progress_callback(min(95, round(scanned * 95 / budget)),
                                      f"Reading video details {scanned}/{budget}")
                complete = not page["has_more"]
                next_cursor = str(page["max_cursor"])
                if not complete and (next_cursor == cursor or not page["aweme_list"]):
                    raise DouyinError(Outcome.METADATA)
                self._profile_pages[cache_key] = {
                    "updated": time.monotonic(), "candidates": list(candidates), "cursor": next_cursor,
                    "scanned": scanned, "name": channel_name, "complete": complete,
                }
                while len(self._profile_pages) > 4:
                    del self._profile_pages[next(iter(self._profile_pages))]
                if complete:
                    break
                cursor = next_cursor
            if not candidates:
                raise RuntimeError("The Douyin profile returned no public videos.")
            return channel_name, candidates

    def create_browser_session(self, cancel_event=None, status_callback=None):
        # Called ONLY by the explicit UI action. Never on an ordinary request.
        from haizflow.services.douyin_browser import create_anonymous_state

        with _session_guard(self.session.lock, cancel_event):
            if status_callback is not None:
                self._status_callback = status_callback
            browser = self.session.browser
            if browser:
                # Refresh the same owned profile rather than discarding a
                # usable guest identity on every click. Failure/cancellation
                # retains the native jar and this reopenable backend.
                _, state = browser.sign(DETAIL_PATH, {"aweme_id": "0"},
                                        self.session.browser_cookies(), cancel_event, refresh=True)
            else:
                state = create_anonymous_state(cancel_event, status_callback=status_callback)
            try:
                _check_cancel(cancel_event)
                # Verify on a candidate transport. A failed/cancelled refresh
                # must not overwrite the last usable native session.
                candidate = DouyinSession(self.session.transport_factory, browser_state=state)
                candidate.browser = browser or state.get("backend")
                candidate.ready = True
                # A created guest jar must work with native signing before we
                # close the visible browser. Normal requests never reopen it.
                candidate.native_verified = True
                candidate.generation = self.session.generation + 1
                try:
                    if status_callback:
                        status_callback("Checking the Douyin session")
                    DouyinAdapter(candidate)._api(DETAIL_PATH, {"aweme_id": "0"}, cancel_event, session_probe=True)
                    _check_cancel(cancel_event)
                    if candidate.browser:
                        candidate.browser.park()
                    _check_cancel(cancel_event)
                except BaseException:
                    candidate.transport.close()
                    raise
                old = self.session.transport
                self.session.transport = candidate.transport
                self.session.profile = candidate.profile
                self.session.browser = candidate.browser
                self.session.ready = True
                self.session.native_verified = True
                self.session.generation = candidate.generation
                old.close()
            except BaseException:
                if not browser and state.get("backend"):
                    state["backend"].close()
                raise
            # Keep the last file revision remembered, so unchanged per-request
            # auth options cannot immediately overwrite this explicit new session.

    def log_media_refresh(self, attempt, *, http_status=0, outcome=Outcome.MEDIA_EXPIRED):
        # No CDN URL or signed query enters diagnostics. The next extraction
        # performs a new inspect with this same session, not the old cached URL.
        logger.info("douyin attempt=%d endpoint=media generation=%d transport=%s signer=none "
                    "classification=%s http=%d bytes=0 retry=True", attempt,
                    self.session.generation, self.session.profile.transport_mode,
                    outcome.value, http_status)


_adapter = None
_adapter_lock = threading.Lock()


def get_douyin_adapter(auth=None):
    global _adapter
    # Browser-profile settings may be used by other platforms. Douyin ignores
    # them completely, including after the explicit guest action has succeeded.
    # It never invokes yt-dlp's broad personal-profile cookie reader.
    if auth and auth.get("cookie_file"):
        # Explicit user-selected Netscape file, Douyin domains only. No automatic search.
        path = Path(auth["cookie_file"]).resolve(strict=True)
        stat = path.stat()
        identity = (str(path), stat.st_mtime_ns, stat.st_size)
        adapter = get_douyin_adapter()
        with adapter.session.lock:
            if adapter.session.cookie_file_identity == identity:
                return adapter
            jar = http.cookiejar.MozillaCookieJar(str(path))
            jar.load(ignore_discard=True, ignore_expires=False)
            cookies = [{"name": c.name, "value": c.value, "domain": c.domain, "path": c.path,
                        "secure": c.secure, "expires": c.expires,
                        "httpOnly": c.has_nonstandard_attr("HttpOnly")} for c in jar
                       if c.name not in {"sessionid", "sessionid_ss", "sid_guard", "sid_tt"}]
            # Never blend unrelated cookie identities, nor overwrite refreshed
            # cookies from the same file on every inspect/download call.
            profile = BrowserProfile()
            replacement = adapter.session.transport_factory(profile)
            try:
                replacement.import_cookies(cookies)
            except Exception:
                replacement.close()
                raise
            old = adapter.session.transport
            adapter.session.transport = replacement
            adapter.session.profile = profile
            adapter.session.ready = False
            adapter.session.native_verified = False
            adapter.session.generation += 1
            adapter.session.cookie_file_identity = identity
            adapter.session.close_browser()
            old.close()
        return adapter
    with _adapter_lock:
        if _adapter is None:
            _adapter = DouyinAdapter()
        return _adapter


def close_douyin_browser():
    # Shutdown must not instantiate a Douyin subsystem that was never used.
    if _adapter is not None:
        _adapter.session.close_browser()

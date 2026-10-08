"""Lazy browser-compatible transport. Cookies never leave this local session."""
from __future__ import annotations

import http.cookiejar
import re
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit


def validate_douyin_address(url: str) -> str:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        valid = (parsed.scheme in {"http", "https"} and not parsed.username and not parsed.password
                 and parsed.port in {None, 80, 443}
                 and any(host == d or host.endswith("." + d) for d in ("douyin.com", "iesdouyin.com")))
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Use a valid douyin.com URL.")
    return url


@dataclass(frozen=True)
class BrowserProfile:
    major: int = 136
    version: str = "136.0.0.0"
    platform: str = "Win32"
    width: int = 1920
    height: int = 1080
    language: str = "zh-CN"
    cores: int = 8
    memory: int = 8
    user_agent: str = ""

    @property
    def ua(self) -> str:
        return self.user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{self.version} Safari/537.36")

    @property
    def transport_mode(self) -> str:
        # Explicit, tested Chrome-family mapping for the shipped Chromium 157.
        # curl_cffi 0.16.3's newest TLS/H2 template is Chrome 150. Keep the
        # actual browser UA/cookies/fingerprint unchanged; do not rotate UAs
        # or silently select arbitrary profiles for unknown browser versions.
        if self.major == 157:
            return "chrome150"
        return f"chrome{self.major}"

    @classmethod
    def from_browser(cls, values: dict) -> BrowserProfile:
        ua = str(values.get("userAgent") or "")
        match = re.search(r"(?:Headless)?Chrome/(\d+\.\d+\.\d+\.\d+)", ua)
        if not match or values.get("platform") != "Win32":
            raise ValueError("The Douyin browser profile is not supported by the native transport.")
        return cls(major=int(match[1].split(".")[0]), version=match[1], user_agent=ua,
                   width=int(values["width"]), height=int(values["height"]),
                   language=str(values["language"]), cores=int(values.get("cores") or 8),
                   memory=int(values.get("memory") or 8))


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes
    url: str
    headers: dict


class DouyinTransport:
    def __init__(self, profile: BrowserProfile):
        from curl_cffi import requests
        from curl_cffi.requests.impersonate import BrowserType

        if profile.transport_mode not in {v.value for v in BrowserType}:
            raise ValueError("The Douyin browser version needs a matching curl_cffi transport profile.")
        self.profile = profile
        self._client = requests.Session(impersonate=profile.transport_mode, default_headers=False)

    @property
    def cookie_jar(self):
        return self._client.cookies.jar

    @property
    def cookies(self) -> dict[str, str]:
        return {c.name: c.value for c in self._client.cookies.jar
                if any(c.domain.lstrip(".") == d or c.domain.endswith("." + d)
                       for d in ("douyin.com", "iesdouyin.com")) and not c.is_expired()}

    def import_cookies(self, cookies, *, replace=False) -> None:
        if replace:
            # A browser snapshot is authoritative, including cookie deletions.
            # Do not retain old visitors/tokens that are absent from that jar.
            for cookie in list(self.cookie_jar):
                domain = cookie.domain.lstrip(".").lower()
                if domain == "douyin.com" or domain.endswith(".douyin.com"):
                    self.cookie_jar.clear(cookie.domain, cookie.path, cookie.name)
        for cookie in cookies:
            domain = str(cookie.get("domain") or "").lstrip(".").lower()
            if not any(domain == d or domain.endswith("." + d) for d in ("douyin.com", "iesdouyin.com")):
                continue
            expiry = float(cookie.get("expires") or 0)
            if expiry > 0 and expiry <= time.time():
                continue
            raw_domain = str(cookie["domain"]).lower()
            # Retain browser scope, TLS-only flag and lifetime rather than
            # converting secure visitor cookies into unrestricted session cookies.
            self.cookie_jar.set_cookie(http.cookiejar.Cookie(
                version=0, name=str(cookie["name"]), value=str(cookie["value"]),
                port=None, port_specified=False, domain=raw_domain,
                domain_specified=raw_domain.startswith("."), domain_initial_dot=raw_domain.startswith("."),
                path=str(cookie.get("path") or "/"), path_specified=True,
                secure=bool(cookie.get("secure")), expires=int(expiry) if expiry > 0 else None,
                discard=expiry <= 0, comment=None, comment_url=None,
                rest={"HttpOnly": None} if cookie.get("httpOnly") else {}, rfc2109=False))

    def get(self, url: str, headers: dict | None = None, cancel_event=None) -> Response:
        # Validate EACH redirect before sending cookies/headers, not after following it.
        from haizflow.services.video_download import DownloadCancelled

        request_headers = {
            "User-Agent": self.profile.ua, "Accept-Language": self.profile.language + ",zh;q=0.9",
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
            "Referer": "https://www.douyin.com/", "sec-ch-ua-platform": '"Windows"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua": f'"Chromium";v="{self.profile.major}", "Google Chrome";v="{self.profile.major}"',
        }
        request_headers.update(headers or {})
        for _ in range(6):
            validate_douyin_address(url)
            if cancel_event and cancel_event.is_set():
                raise DownloadCancelled("Video download cancelled.")
            response = self._client.get(url, headers=request_headers, timeout=(5, 15),
                                        allow_redirects=False, verify=True)
            if cancel_event and cancel_event.is_set():
                raise DownloadCancelled("Video download cancelled.")
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    break
                url = validate_douyin_address(urljoin(url, location))
                # API signing headers are path-bound. Do not propagate them to a redirect.
                for name in ("uifid", "x-secsdk-web-signature", "x-secsdk-web-expire"):
                    request_headers.pop(name, None)
                continue
            if len(response.content) > 8 * 1024 * 1024:
                raise ValueError("Douyin metadata exceeded the safe size limit.")
            return Response(response.status_code, response.content, url, dict(response.headers))
        raise ValueError("Douyin returned an invalid or excessive redirect chain.")

    def close(self) -> None:
        self._client.close()

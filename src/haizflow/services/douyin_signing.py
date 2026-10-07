"""Small native signing boundary; no UI, transport or generated visitor tokens.

Web signature protocol adapted from Evil0ctal/Douyin_TikTok_Download_API,
commit 4f0bed8483c35a980315d9c7b3a1d4a1119ad2b2 (Apache-2.0).
Copyright 2021-2026 Evil0ctal and contributors.
Modified by HaizFlow 2026-10-08: synchronous session/profile interface, GET-only
endpoint allowlist, no invented msToken, no server dependencies.
See licenses/DOUYIN-CHANNEL-IMPORT-NOTICE.md and licenses/Apache-2.0.txt.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from urllib.parse import quote, urlencode

from haizflow.vendor.douyin_abogus import ABogus, browser_info_from_screen

DETAIL_PATH = "/aweme/v1/web/aweme/detail/"
POSTS_PATH = "/aweme/v1/web/aweme/post/"
WEB_SALT = "A96D855A08C0A9707F8BEF0D9A527E4E"
VISITOR_NAMES = ("uifid", "uifid_temp", "uifidtemp", "UIFID", "UIFID_TEMP", "UIFIDTEMP")


@dataclass(frozen=True)
class SignedRequest:
    url: str
    headers: dict[str, str]
    mode: str


class DouyinSigner:
    def sign(self, path: str, params: dict, cookies: dict, profile) -> SignedRequest:
        if path not in {DETAIL_PATH, POSTS_PATH}:
            raise ValueError("Unsupported Douyin signing endpoint.")
        values = {str(k): str(v) for k, v in params.items()}
        # msToken is session state, not a randomly generated request parameter.
        if cookies.get("msToken"):
            values["msToken"] = cookies["msToken"]
        query = urlencode(values, quote_via=quote, safe="*-._")
        bogus = ABogus(profile.ua, browser_info=browser_info_from_screen(
            profile.width, profile.height, profile.platform)).get_value(query)
        pairs = [*values.items(), ("a_bogus", bogus)]
        visitor = next((cookies[n] for n in VISITOR_NAMES if cookies.get(n)), "")
        headers = {}
        mode = "a_bogus"
        if visitor:
            fp = cookies.get("s_v_web_id")
            if fp:
                pairs.extend([("verifyFp", fp), ("fp", fp)])
            stamp = str(int(time.time()))
            pairs.extend([("uifid", visitor), ("timestamp", stamp)])
            covered = urlencode(pairs, quote_via=quote, safe="*-._")
            signature = hashlib.md5(f"{visitor}_{stamp}_{WEB_SALT}_{covered}".encode(),
                                    usedforsecurity=False).hexdigest()
            pairs.append(("x-secsdk-web-signature", signature))
            headers = {"uifid": visitor, "x-secsdk-web-signature": signature,
                       "x-secsdk-web-expire": stamp}
            mode = "a_bogus+websign"
        return SignedRequest("https://www.douyin.com" + path + "?" + urlencode(
            pairs, quote_via=quote, safe="*-._"), headers, mode)

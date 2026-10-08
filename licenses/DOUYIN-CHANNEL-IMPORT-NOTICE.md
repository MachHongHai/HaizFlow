# Douyin Request Signing Notice

HaizFlow adapts the native a_bogus/SM3 implementation and web-signature protocol
from `Evil0ctal/Douyin_TikTok_Download_API` at the verified revision
`4f0bed8483c35a980315d9c7b3a1d4a1119ad2b2`:

https://github.com/Evil0ctal/Douyin_TikTok_Download_API/tree/4f0bed8483c35a980315d9c7b3a1d4a1119ad2b2/src/dtk/signing/native

Upstream notice retained:

> Douyin_TikTok_Download_API
> Copyright 2021-2026 Evil0ctal and contributors
>
> Licensed under the Apache License, Version 2.0. The full text is in the
> LICENSE file next to this one.
>
> https://github.com/Evil0ctal/Douyin_TikTok_Download_API

The full Apache-2.0 text is supplied as `licenses/Apache-2.0.txt` in HaizFlow.
Files changed by HaizFlow on 2026-10-08:

- `src/haizflow/vendor/douyin_abogus.py`: local SM3 import and attribution header;
  native algorithm and diagnostic decoder retained.
- `src/haizflow/vendor/douyin_sm3.py`: attribution header; native algorithm retained.
- `src/haizflow/services/douyin_signing.py`: smaller GET-only signing boundary,
  explicit session/profile arguments and endpoint allowlist. No generated visitor tokens.
- `src/haizflow/vendor/douyin_browser_sdk.py`: SDK capture adapted from
  `docker/browser_rpc/backends/cloak.py` at the same revision. Restricted to
  HaizFlow's owned Douyin context and the requested endpoint/video/profile;
  preserves the exact signed URL and aborts signing probes before sending them.

The small local adapter/session/transport/classifier is HaizFlow code inspired
by the reference architecture. No upstream server, database, scheduler, proxy
pool or public API client is used. Optional browser-assisted signing uses an
isolated browser context with its own temporary profile, only after the
user explicitly creates a Douyin session. It does not solve CAPTCHA, read
personal browser profiles, disable TLS checks or disable Chromium's sandbox.

The active browser uses Playwright 1.63.0 with unmodified Chromium snapshot
1714059 (157.0.8092.0), installed separately through Resource Packs by direct
download from Google's official upstream bucket. The app installer and Core
update do not contain Chromium. Browser creation is explicit and does not
automatically download a missing resource pack. The Chromium base BSD text and
Playwright NOTICE are retained separately, with versions and hashes in
`licenses/BROWSER-BINARY-LICENSES.json`. See `docs/douyin-distribution.md`
for the delivery boundary and exact-binary notice limitations.

The legacy, unused `douyin_xbogus.py` remains separately attributed to
`jiji262/douyin-downloader` / Evil0ctal under Apache-2.0. The current Douyin
adapter does not import it. The historical requested revision `8384ade7` could
not be verified in that repository; HaizFlow makes no provenance claim for it.

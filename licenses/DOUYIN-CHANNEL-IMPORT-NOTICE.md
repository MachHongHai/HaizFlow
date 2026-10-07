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
isolated CloakBrowser context with its own temporary profile, only after the
user explicitly creates a Douyin session. It does not solve CAPTCHA, read
personal browser profiles, disable TLS checks or disable Chromium's sandbox.

The legacy, unused `douyin_xbogus.py` remains separately attributed to
`jiji262/douyin-downloader` / Evil0ctal under Apache-2.0. The current Douyin
adapter does not import it. The historical requested revision `8384ade7` could
not be verified in that repository; HaizFlow makes no provenance claim for it.

Optional development guest-browser support uses Playwright 1.58.0 (Apache-2.0)
and the CloakBrowser 0.5.10 wrapper (MIT, Copyright 2026 CloakHQ), pinned to the
Windows Chromium binary 146.0.7680.177.5. The wrapper source is referenced at
`CloakHQ/cloakbrowser` commit `f04c23da285b3b3d3cf10c8f9d282e7adc1d52ce`.
The binary has a separate proprietary license; wrapper MIT and Chromium's
BSD-style terms do NOT grant permission to redistribute the patched binary.

Upstream wrapper license: https://github.com/CloakHQ/cloakbrowser/blob/v0.5.10/LICENSE

The unmodified wrapper MIT text is retained as `licenses/CloakBrowser-MIT.txt`.

Binary terms: https://github.com/CloakHQ/cloakbrowser/blob/v0.5.10/BINARY-LICENSE.md

No Cloak binary is bundled or published by this change. Internal development
testing uses the official download with upstream manifest/signature verification.
Public HaizFlow browser-component delivery requires a separate licensing review
and any necessary OEM/SaaS agreement. Do not package `runtime/douyin-cloak`.
Dependency listing does not by itself resolve customer-facing browser-control
rights. The source-only distribution decision and next steps are documented in
`docs/douyin-distribution.md`.

# Douyin browser delivery

Reviewed on 2026-10-08. This records the delivery design and license evidence, not a legal opinion.

HaizFlow uses **Playwright 1.63.0** and an unmodified, unbranded Chromium Windows x64 snapshot **1714059 / 157.0.8092.0**. CloakBrowser is not imported, installed or included in the release. Its unused wrapper/binary license files have been removed.

## Optional resource pack

The installer and Core update do not contain Chromium. The user installs **Trình duyệt Douyin (Chromium)** in Resource Packs; the app downloads it directly over TLS from Google's official Chromium snapshot bucket. HaizFlow does not mirror or publish that browser archive on GitHub.

- Archive: https://storage.googleapis.com/chromium-browser-snapshots/Win_x64/1714059/chrome-win.zip
- SHA-256: `bcd33aa9cd52ae75da0f84cbc5915c7583f0f791e5abe711ab1ca2ef37b00b19`
- Source revision: `86d7d234e3e67c9888a06fa2e2957d3c7604e839`
- Upstream license: https://chromium.googlesource.com/chromium/src/+/86d7d234e3e67c9888a06fa2e2957d3c7604e839/LICENSE
- Upstream component sources and terms: https://chromium.googlesource.com/chromium/src/+/86d7d234e3e67c9888a06fa2e2957d3c7604e839/third_party/

The retained Chromium BSD-3-Clause text is the upstream **base license**, not a complete license inventory for all Chromium components. This snapshot's built-in credits page is a placeholder; it must not be represented as a complete notice set. Redistribution of the browser by HaizFlow is not part of this release design. Any future bundled/mirrored browser requires a separate exact-binary notice review.

Resource Pack installation verifies the pinned archive and extracted files, tests an owned blank headless window, and only then promotes the installation. Pause/resume, cancellation, removal and repair use the existing local package manager. Session creation never installs a missing browser implicitly.

## Bundled Playwright driver

Playwright's Apache-2.0 license and NOTICE are retained. Its wheel includes the Node driver and component notices; the release keeps those original driver license/notice files along with the generated locked-dependency inventory. This does not grant permission for unrelated browser binaries.

## Adapted Douyin source

The a_bogus/SM3 signing and SDK capture adapted from the pinned Evil0ctal revision remain Apache-2.0 source. Their attribution and modification notice are retained in [DOUYIN-CHANNEL-IMPORT-NOTICE.md](../licenses/DOUYIN-CHANNEL-IMPORT-NOTICE.md). A historical upstream file name containing `cloak.py` identifies provenance; it does not introduce CloakBrowser code or proprietary browser patches.

No server, database, remote download API or browser identity pool is included. Create/Refresh session uses an owned anonymous profile. Users complete any verification themselves; HaizFlow does not solve CAPTCHA, read personal browser profiles, disable TLS validation or disable the Chromium sandbox. The browser closes after native-session verification, while the anonymous session is reused for video, channel and audio.

Cookie state, browser profiles, development caches and browser binaries are excluded from source/release artifacts. Publisher and user obligations for video rights and other bundled components remain independent.

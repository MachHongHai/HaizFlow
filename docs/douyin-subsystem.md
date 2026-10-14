# Douyin desktop subsystem — implementation record

Status: source changes only, 2026-10-08. No build, commit, push or release.

## Previous flow and observed causes

The generic HFlow downloader used yt-dlp, with a custom Douyin extractor and
several request identities/fallbacks. Protected metadata requests were not tied
to a stable browser visitor identity. Empty metadata could become a terminal
“no playable video” error, rather than a classified session/risk response.

An isolated native probe received only `__ac_nonce` from the root page. The
protected detail endpoint returned HTTP 403, a 46-byte response and missing
UIFID/signature rejection. The first-party share-page fallback returned a
verification page. A stock Chromium guest window showed a slider inside a
cross-origin frame; the previous guest bootstrap treated that as terminal and
closed it. These observations support a session/signing problem, not an invalid
`jingxuan?modal_id` URL. They do not establish that all failures have one cause.

TikTok channel enumeration also masked extractor failures with `ignoreerrors`
and could report an empty channel when yt-dlp returned unusable entries. Its
narrow fix preserves yt-dlp and reports/retries that failure rather than
silently returning zero videos.

## Reference architecture and intentional exclusions

Reference: Evil0ctal/Douyin_TikTok_Download_API at
`4f0bed8483c35a980315d9c7b3a1d4a1119ad2b2`:

- [Cloak backend and SDK readiness/capture](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/4f0bed8483c35a980315d9c7b3a1d4a1119ad2b2/docker/browser_rpc/backends/cloak.py)
- [Protected endpoints](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/4f0bed8483c35a980315d9c7b3a1d4a1119ad2b2/src/dtk/signing/protection.py)
- [Native signing](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/tree/4f0bed8483c35a980315d9c7b3a1d4a1119ad2b2/src/dtk/signing/native)

Adapted principles: coherent identity, session-bound web signing, actual SDK
readiness with backoff, protected endpoint classification, bounded retry, and
separation of signing from transport. Native a_bogus/SM3 and the small browser
capture shim contain attributed adaptations, not just architectural inspiration.

Not copied: PostgreSQL, Redis, FastAPI, RPC/MCP server, identity/proxy pools,
distributed workers, schedulers, archive database, web console, Docker services
or calls to the reference project's public API. Other sources remain on yt-dlp;
the later scoped Facebook collection reader and source checks are documented
in [Download source checks](download-source-checks.md).

## Current request/session model

`URL -> normalize/ID -> DouyinAdapter -> one local guest session -> signer ->
coherent native transport -> classified metadata -> existing HFlow pipeline`

The adapter reuses one cookie jar, UA, browser version, geometry and transport.
Inspect and subsequent download share that session. A re-entrant lock freezes
identity while extraction transfers formats, headers and scoped cookies to
yt-dlp. Redirects are validated before sending requests; unrelated domains,
credentials, unsupported ports and malformed URLs are rejected.

An explicit guest-cookie file is filtered to Douyin domains and imported once
per file revision, not on every request. Login/session authentication cookies
are excluded. Personal browser-profile extraction is never invoked for Douyin,
including by yt-dlp construction. Other platforms retain their existing auth.

## Signing and transport

Native is the default: a_bogus uses the stable UA/geometry. The protected detail
and posts endpoints use the session UIFID and web signature when available.
Only real session msToken is included; no visitor token is fabricated. Signing
has a GET-only endpoint allowlist, separate from UI and HTTP transport.

After the explicit **Tạo phiên Douyin** action, an owned standard Chromium window
creates an anonymous identity. SDK request capture is installed before page
scripts, only in that owned context. A probe traverses the site's SDK wrappers
but is aborted below them before the matching request reaches the network.
The exact signed URL is returned; HFlow does not re-encode, reorder or append
msToken after signing. Native transport sends it with the required signing
headers and the same scoped cookies.

Current normal download requests use native signing after browser-assisted
creation verifies the native transport. The visible browser and driver close
immediately after successful verification. SDK capture is used by explicit
creation/refresh, not by every inspection or media refresh. Normal requests
never reopen the browser automatically; rejected/expired guest state requires
the explicit session action. See the latest follow-up in
[Chromium test notes](douyin-chromium-test.md).

Playwright 1.63.0 controls unmodified Chromium snapshot 1714059 (157.0.8092.0),
installed separately in Resource Packs by direct official upstream download.
Create Session is blocked with a notification when the pack is missing; no
implicit install takes place. Video, channel and audio share the same pack.
CloakBrowser and its unused license documents have been removed. Native
curl_cffi 0.16.3 uses its newest Chrome-family TLS/H2 template, Chrome 150,
for the reviewed Chromium 157 profile. This is an explicitly tested family
compatibility mapping, not a claim of an exact Chrome 157 TLS fingerprint.
Actual browser UA, cookies and fingerprint values stay coherent and are not
rotated between requests. Other unsupported versions fail clearly. TLS validation
and Chromium sandbox remain enabled. No Googlebot/Mobile Safari/random-UA
retry ladder remains. No broad personal profile or unrelated cookie read.

## Browser lifecycle and human verification

The browser is lazy: nothing opens at application startup. One temporary
HFlow-owned profile is reused for that browser identity; no fingerprint seed
or spoofing flag is configured. The latest browser snapshot is restored before
navigation when reopening an idle context, not a stale native export.
Visitor changes trigger a page reload so SDK cached identity is not stale.

A visible CAPTCHA leaves the window open for the user to complete manually,
with a five-minute bound and cancellation. The same behavior applies if the
SDK encounters verification after initial creation. Hidden verification frames
are not mistaken for a visible CAPTCHA. No challenge solving, security patching,
credential collection or personal-browser injection is implemented.

Readiness probes back off from 0.25 s to at most 2.5 s, with a 25 s SDK budget.
Initial creation retries a transient startup failure once in the same context,
instead of requiring a second click. Verified native sessions close the window
and driver before creation returns; normal requests do not use the idle-reopen
path. The 90 s idle bound below remains for unfinished/legacy SDK operations.
Repeated transient SDK errors are classified for bounded same-profile retry,
not immediately presented as a terminal "create session" failure. Chromium
closes after 90 s idle; a later request can reopen the same owned profile,
not a new identity on every request.
Refresh reuses that owned identity instead of discarding it before success.
A failed/cancelled refresh preserves the previous native jar/backend; an actual
successful metadata request clears stale UI refresh errors. Initial signing
probe readiness alone cannot mark creation as ready. A candidate native
transport must receive a structured response from the protected detail endpoint
before its identity is committed. The probe uses ID 0 and accepts only a
validated successful response or the observed structured unknown-ID response
(HTTP 200, integer status_code 5, aweme_detail null, no challenge). This special
business response is never accepted as a normal video inspection. New failed
contexts and app shutdown clean up owned resources. Browser tasks run on a
dedicated event loop, outside the Qt UI thread.

## Classification and retry

Outcomes: success; private/removed/unavailable; risk control; signature/session
rejection; rate limit; transient network; upstream format change; unusable
metadata; expired media; verification required.

HTTP 200 is not automatically success. Empty/tiny envelopes are retryable risk
responses; malformed shapes are upstream/metadata errors. Successful titles
are not scanned for words such as “captcha”. Private/removed, unsupported
content and malformed URLs are not retried.

At most three protected API attempts: initial stable request; one controlled
session/SDK refresh when risk/signature rejection justifies it; a final bounded
attempt. Backoff and numeric Retry-After are capped. One first-party share-page
fallback uses the same identity; no download website or external API is used.
Human verification is not an automatic retry/challenge solver.

## Media refresh and integration

An expired/403 CDN URL or unavailable requested format causes fresh metadata
extraction, not infinite reuse of the inspected URL. Scoped cookies and browser
profile are transferred to the existing yt-dlp media download. Workspace,
progress, cancellation, FFmpeg validation, project import and cleanup remain
the existing HFlow implementations. Channel scans have a bounded raw-post
budget, including photo posts, even if an upstream page exceeds requested size.

Continuation throttles retain the exact cursor and verified session. After the
ordinary three-attempt request retry, a scan can wait 30 seconds and then 60
seconds to resume automatically. This recovery budget is shared across the
whole scan, not reset for every page; waits are cancellation-aware. CAPTCHA
and terminal failures never enter this recovery path. The scan status reports
the scanned count and waiting period without pretending that work is complete.

If recovery is exhausted, available candidates are returned as an explicitly
incomplete scan, not a successful 100% scan or a failed download. Users can
download the available rows or rescan. Popular ordering is applied to all
collected rows before selecting the requested count, but cannot promise the
most-viewed videos from unread pages. The cursor cache remains local to the
same session for five minutes; saved project results and the incomplete notice
survive restart, but the API cursor does not. A new session/restart must rescan.

2026-10-13 anonymous live checks: native signing, browser SDK signing and
in-page SDK fetch all returned `{"status_code":0}` without a list for a
nonzero cursor. First pages contained 20/22 rows, including pinned posts.
Repeated 30/60-second waits did not recover this channel. This exact bare
continuation envelope now receives at most three same-cursor attempts with
short one/two-second waits, then is reported as incomplete pagination,
not mislabeled as a temporary HTTP rate limit or end-of-channel. A transient
envelope can recover without replacing the anonymous identity; a persistent
one never enters the long 30/60-second recovery loop. Genuine
HTTP 429/network failures retain bounded recovery. A channel returning only
zero/missing play counts is not advertised as successfully ranked by views.
Anonymous-only access remains the user-selected boundary; no login, personal
profile extraction or challenge solver is added. More than the readable first
page and accurate view ranking cannot be guaranteed when Douyin withholds them.

## Diagnostics

Adapter logs include attempt, endpoint path, session generation, transport mode,
signer mode, semantic classification, HTTP status, body size and retry decision.
Media refresh logs use a constant `media` endpoint label. Cookies, tokens,
fingerprint seed, signed query, sensitive headers, page contents and CDN URLs
are not logged by these diagnostic paths. Browser exception text is sanitized
before reaching UI.

## Tests and measured evidence

Deterministic tests cover URL forms/redirects, stable session reuse, signing
context and fixed web-signature fixture, matching transport, cookie domain/
secure/expiry preservation, empty HTTP 200, signature rejection, rate limits,
malformed metadata, terminal private responses, bounded retry, stale-media
refresh and successful retry, cancellation and unaffected generic routing.

Guest-browser mocks cover human CAPTCHA completion/timeout, later CAPTCHA,
cancelled navigation, anonymous-only state, idle close/reopen with stable
profile/seed, invalid SDK URLs, cleanup and environment restoration. A Node
test executes the actual capture shim with a fake SDK/network and verifies
exact signed bytes, target filtering, fetch/XHR capture and no probe network
request. It skips only when that optional development test runtime is absent.
UI tests check no browser on component load, duplicate-create guard and status/
cancel bindings. All network tests are mocked; live Douyin is not a required
test-suite dependency.

Live evidence on this development machine: the supplied modal URL and its
`/video/` form both returned the matching video metadata, HTTP 200, in one
Cloak-assisted session using native Chrome 146 transport. The author's posts
endpoint also returned public video data after one bounded SDK refresh.
The existing `inspect_video_url -> download_video` pipeline then downloaded the
181-second sample (88,926,883 bytes) and passed the existing FFmpeg audio/video
track validation. This does not prove that every video/channel works or that
all project processing stages were exercised live. No benchmark success
percentage is claimed.

Tests executed: the previous full `scripts/test.ps1 -SkipCompile` run passed the Python
correctness lint, 1,653 tests (one skip), 243 subtests and complete QML lint.
The run includes shutdown interrupting an active human verification wait.
Four existing Qt deprecation/optional TorchCodec decoder warnings remain; no
test failed. Focused browser/SDK tests also passed. The isolated source
application `hflow_desktop.py --ui-smoke-test` exited successfully; dependency
lock manifest verification, targeted source compile/lint and `git diff --check`
passed. These source checks are not a frozen-installer acceptance test.

## Download UI and audio follow-up

Video, channel and audio actions use the same adapter and owned guest session.
The shared Qt controller exposes readiness: subsequent tabs show a refresh
action rather than suggesting another session must be created. An idle browser
reopen still keeps the same owned profile and fingerprint seed; a site-requested
human verification remains possible. Switching tabs alone never recreates it.

New link inspection clears completed download errors without hiding active
work. Successful channel tasks are no longer classified as failures. Channel
results are matched to their actual source, including queued inspection, so
changing URL/platform cannot expose the previous source as a new success.
Progress is shown once on the channel page, with queue cancellation/progress
still available when navigating to video or audio.

Both URL audio and local extraction stage their output privately, then choose
a non-overwriting final filename. Cancelled/failed conversion cleans staging
files; late cancellation after the committed move cannot report a false failure.
Audio progress separates download from AAC conversion, and FFmpeg conversion
has a timeout and cancellation checks before committing output. Douyin expired
audio URLs refresh metadata through the same adapter as video URLs.

TikTok probing found a concrete Python-API integration error: yt-dlp requires
an `ImpersonateTarget`, not the CLI string `"chrome"`. A string caused an
assertion before the retry could request metadata. This is fixed for shared
video/audio options. TikTok channel JSON requests now use browser transport
from the first attempt, with bounded retry for empty/invalid JSON. Private
accounts remain terminal. No TikTok signing/browser replacement was added.
Live `@tiktok` inspection returned two public videos (68 and 65 seconds);
audio download of the first succeeded and FFmpeg confirmed an audio stream.
This small live sample is not an all-channel reliability benchmark.

Additional deterministic tests cover the real yt-dlp target constructor,
empty-JSON retry, shared video/channel/audio identity, queue feedback, private
audio staging, non-overwrite and cancellation before committing converted audio.
The video/audio pages were rendered at 1120 and 640 pixels in an isolated Qt
environment and the source application's UI smoke test exited successfully.
After the final queued-source guard, 85 focused tests and QML lint were rerun
successfully. Live network checks are intentionally not mandatory in the suite.

## Remaining limitations and relative reliability

Newest-count follow-up (2026-10-14): source had forced `count=20` on every
profile request, including requests for 50/100 newest videos. Read-only probes
against the same profile obtained 40 rows with `count=40`, and 41 rows with
`count=50` or `100` (platform-selected/pinned rows can differ). The next page
was still withheld, including an SDK-signed request using the same count.
The adapter now requests up to 40 posts per page and keeps that count stable
for the entire cursor chain. A cached 20-post cursor is not reused when the
page size changes. Deterministic 50/100 multi-page tests pass; those tests are
not evidence that the current anonymous live session can retrieve 50/100.

Historical source comparison found a separate counting regression: newest
scans used the requested video count as a raw-post budget. Photos, invalid
posts and repeated pinned posts therefore reduced the usable video count.
Newest scans now count unique usable videos, with a separate hard safety cap
of 1,000 raw posts. Popular scans still respect their selected raw-post scope.
The adapter retains whole received pages and their exact next cursor, so
increasing 50 to 100 can reuse buffered rows without skipping the tail of a
page. Newest ordering and final requested-count trimming remain in the channel
service. Cursor caches cannot cross page-size, counting-mode or session changes.

Additional read-only probes on 2026-10-14 tested the former query recipe,
`cut_version=1`, disabled time-list queries, profile Referer and same-origin
fetch headers. First pages returned 40 rows, but each continuation still
returned the bare 17-byte envelope. Clock skew was about one second, not a
large timezone/clock error. These probes do not establish why the same channel
previously allowed 50/100 anonymous results. Live 100-video recovery remains
unverified; passing fixture tests must not be presented as that evidence.

## Audio link inspection

The Downloads audio page inspects metadata before enabling its download action,
matching the video page's title, author, duration and thumbnail presentation.
Typing, pasting or checking a link never queues media. Downloading requires the
same inspected URL; editing the URL invalidates its preview. Local-file audio
extraction is unchanged. Audio preview checkpoints are separate from video
previews and contain metadata only, never signed media URLs or authentication.
Project switching invalidates late inspection callbacks, and shutdown drains
both coordinators. The actual audio download still refreshes metadata instead
of relying on a persisted CDN URL.

Channel scans retain every usable result up to the requested download count,
even when a later page requires verification, rejects the session, changes
format or repeats its cursor. These cases return an incomplete-scan notice;
they do not trigger challenge solving or treat the received rows as full EOF.
A legitimate empty profile is a zero-result scan, with a 0/requested notice.
Shortfalls after filters/scan scope are also reported explicitly.

The desktop persists both partial rows and their notice. A failed/cancelled
rescan of the same source/ranking/content filter retains a detached copy of
the earlier list and labels it as previous results. Another channel or changed
filters never inherits those rows. Deterministic checks cover 0, 1, 22, 50 and
100 results, project reopening, terminal continuation errors and invalid cursors.

Expected reliability is better than the earlier contradictory-UA/no-visitor
approach: identity is coherent, protected signing is explicit, session/risk
errors are recoverable when justified, and human verification no longer closes
the window immediately. Evidence is still limited to this machine and a small
live metadata sample. Network/IP/region restrictions, CAPTCHA, private content
and future Douyin SDK/API changes remain outside HFlow's guarantees.

Native cold sessions can still be rejected without browser-created visitor
state. Explicit cookie files cannot prove the original browser fingerprint.
The native HTTP request has bounded timeout cancellation, not immediate socket
interruption. Chromium is optional and cannot be assumed available in existing
installed releases. Windows x64 is the verified development target.

## License and release boundary

Apache attribution/modified-file headers and retained upstream notice are in
`licenses/DOUYIN-CHANNEL-IMPORT-NOTICE.md`, `NOTICE` and third-party inventories.
No CloakBrowser package or browser patches are used. Its unused license files
have been removed; artifact guards still reject legacy development caches.
Chromium is downloaded directly from Google's official upstream when the user
installs the optional Resource Pack. No browser binary is committed, mirrored
or included in the installer/Core update. Playwright and its original driver
license/notice files are included. The Chromium BSD reference is not the full
third-party binary closure. See [Douyin distribution decision](douyin-distribution.md).

The final combined download/source follow-up passed 1,704 tests, 243 subtests,
Python correctness lint and all QML lint. The same four pre-existing warnings
and one optional skip remain. Detailed source probes and limitations are in
`download-source-checks.md`.

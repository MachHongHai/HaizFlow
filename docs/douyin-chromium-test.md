# Douyin: standard Chromium compatibility test

Local source checks on Windows, 2026-10-08. No installer, commit, push or public
release is produced by these checks. No personal profile, login, credential or
cookie file is used. Results are samples, not a measured platform success rate.

## Backend

- Playwright 1.58.0, loaded only by the explicit Douyin session action.
- Unmodified Chromium 146.0.7680.0, official Windows x64 snapshot 1582218.
- Stable application-owned temporary profile; the same browser session and
  domain-scoped cookie jar are reused for inspection, channel and media requests.
- Native curl_cffi `chrome146` transport remains consistent with the browser's
  actual profile. No fake browser family, patched fingerprint, sandbox/TLS
  override or ambient browser-profile discovery is introduced.
- Idle/shutdown closes both Chromium context and its Playwright driver. This
  experiment does not distribute the binary; see `douyin-distribution.md`.

## Live results before the popup adjustment

The public video `7692729822069443859` was inspected through both the
`jingxuan?modal_id=` and `/video/` forms. A complete 60.488-second video
(6,544,810 bytes) and a 60.489-second AAC/M4A file (1,486,874 bytes) downloaded
through the existing HaizFlow pipeline. FFprobe verified the media.

The video's public author profile returned three candidates. One 66.571-second
channel video (9,136,067 bytes, HEVC picture and AAC audio) downloaded through
the existing channel pipeline. A video → channel → video sequence retained
the same owned browser/profile. A pre-cancelled inspection was rejected.

Some signing attempts needed the existing bounded session refresh. This remains
observable; a successful media sample is not proof that Chromium will never
need refresh or user verification.

## Optional login invitation

The observed invitation has the title `登录后免费畅享高清视频`, the semantic
panel ID `douyin_login_comp_flat_panel`, and a normal X control in its header.
HaizFlow now clicks only that known visible invitation's unambiguous X through
normal hit testing. It does not remove/hide DOM, force a click, press Escape on
an unknown overlay, fill a login form, or solve verification. At most two
dismissal attempts are allowed per signing-readiness operation.

CAPTCHA is checked before dismissal. A different/mandatory login heading, hidden
control, changed icon or ambiguous controls are left alone. Changing upstream
markup fails conservatively rather than clicking a different button. Diagnostics
record the action and exception type only, never cookies or signed queries.

## Loading-document failure found during repeated trials

An initial three-session trial downloaded one video but failed to create the
other two sessions. A separate diagnostic retry established a concrete cause:
`Locator.inner_text: Timeout 1500ms exceeded` while reading the page body, before
signing or a metadata request. Closing the invitation alone is therefore not a
complete explanation of the intermittent failures.

A transient missing body now means unknown readiness, not "no CAPTCHA" or an
immediate failed session. HaizFlow waits within its existing bounded SDK deadline,
honours cancellation and does not sign or dismiss anything until the document
can be examined. A sustained loading timeout is reported as a transient failure.
Reloads during manual verification retain the human-wait deadline rather than
accidentally using the already elapsed SDK-startup deadline.

## Repeated live check after the adjustments

Three fresh owned sessions each encountered the known invitation, closed it
through the normal X control once, and completed a real download:

| Trial | Result | Elapsed, including creation/check/download |
| --- | --- | --- |
| 1 | 60.488-second video, 6,544,810 bytes | 22.14 seconds |
| 2 | AAC/M4A audio, 1,486,874 bytes, FFprobe verified | 52.44 seconds |
| 3 | 60.488-second video, 6,544,810 bytes | 51.86 seconds |

There were no close-control failures in these three trials. Each inspection
and download retained its original browser-session object. Trials 2 and 3
needed one existing bounded SDK/session refresh before inspection succeeded;
do not represent the results as instant signing or universal Douyin reliability.
The live test results are local development artifacts, not repository assets.

## Deterministic coverage

Tests cover known/mandatory/hidden/ambiguous invitations, normal-click failure,
CAPTCHA priority, the two-attempt cap, loading-document detection, deferred
signing, bounded loading timeout, cancellation, persistent profile reuse,
failed-launch cleanup, verification-page reload and Playwright shutdown. See `tests/test_douyin_browser.py`.
The surrounding native adapter, transport, download and session UI tests remain
deterministic; live checks are not mandatory CI tests.

## Session-readiness follow-up

The reported ready-label/first-preview failure exposed separate lifecycle
weaknesses: an SDK probe could publish readiness before an API response,
transient SDK exceptions were terminal, and every failed submission disposed
the browser context. Native cookies were also replayed over live browser state.

The source now verifies a candidate native transport against the protected
detail endpoint before committing creation/refresh. ID 0 produces the observed
structured unknown-video response (status_code 5, aweme_detail null); this is
accepted only in the dedicated session probe, never as normal video metadata.
An empty/blocked/challenge/malformed response cannot complete creation.
This proves basic endpoint/session handling, not access to every channel.

Transient signing/loading errors use the existing bounded adapter retries and
one same-profile document refresh. Recoverable errors do not dispose Chromium.
Only real metadata success publishes normal request readiness; exhausted
signature/risk rejection disables requests until an explicit session refresh.
Cookie synchronization merges genuine native changes only if the browser has
not independently rotated that cookie. An unchanged old export cannot overwrite
live values. Browser snapshots also remove obsolete native Douyin cookies.
Idle disposal saves the latest guest cookies and reopening restores that snapshot
into the same owned profile. Failed candidate verification retains the previous
native transport and closes newly created resources.

After these changes the channel supplied in the screenshots returned 10 videos
on each of two preview calls without another user click. A longer sequence
also returned 10 videos after an explicit same-backend refresh, inspected a
video, downloaded AAC/M4A audio (1,486,874 bytes, 60.489 seconds), and returned
two channel videos after an idle-context close/reopen with the same profile.
This sequence took 208.51 seconds: several operations needed a bounded SDK
refresh, so it is not a claim of instant or universal reliability. A separate
shorter two-preview check passed in 12.61 seconds.

The full source gate passed 1,772 tests, 243 subtests, Python correctness lint
and all QML lint (one optional skip and four existing warnings). Additional
deterministic cases cover first-preview retry, non-destructive signature timeout,
cookie rotations, idle restoration, API verification failure, challenge refusal,
ready-label invalidation, and active-backend/package exclusion of CloakBrowser.
The isolated source UI smoke test also passed. No build, commit, push or publish
was performed for this follow-up.

## Native requests and immediate window closure

A later user test still reported a first-creation failure and a new visible
browser on preview. The initial `_bootstrap` had no same-profile startup retry,
unlike `_api`; and the default browser-SDK signing path reopened an idle context.
Keeping a profile stable was therefore not sufficient to meet the desired UI
behavior.

Initial creation now has one bounded same-context startup recovery for transient
SDK/navigation failures. Missing components, anonymous-only rejection and human
verification timeout are not retried blindly. CAPTCHA remains user-driven.

The candidate transport is now verified using native a_bogus/web signing rather
than another browser-SDK request. Only after this succeeds does `park()` close
the Chromium context and Playwright driver, retaining the owned profile for an
explicit refresh. Normal video/channel/audio metadata requests use the verified
native jar, UA and transport; they cannot reopen Chromium, including on retry.
A terminal session/challenge rejection instead requires explicit refresh.
An explicit refresh can reopen that same profile, synchronize the current native
cookie jar, reverify, and close again. Cancellation/failure still cannot commit
an unverified candidate or silently replace the previous native transport.

Three fresh owned profiles each completed creation without a second user click,
auto-closed their context/driver, then inspected a video and read three posts
from the supplied channel without reopening the browser. The first trial also
downloaded AAC/M4A (1,486,874 bytes, 60.489 seconds), explicitly refreshed the
same profile and inspected again with no open Chromium context afterwards.
Trial times were 22.28 seconds (including download and explicit refresh), 7.61
and 7.77 seconds. This is a small local compatibility sample, not a platform
benchmark or a guarantee for all IPs/videos. The older timings above describe
the superseded resident-SDK request path.

The redundant background-work badge was removed from the Downloads page;
queue progress/cancellation and project-deletion guards remain intact. These
changes remain source-only.

Verification for this follow-up: full source gate 1,778 passed, one optional
skip, 243 subtests, four existing warnings, Python correctness lint and all QML
lint; post-adjustment focused download/browser/UI suite 236 passed and 10
subtests; isolated source application smoke test passed. No build or public
release was produced.

## Optional Resource Pack acceptance (2026-10-08)

The current release path uses Playwright 1.63.0 and Chromium snapshot 1714059
(157.0.8092.0), downloaded directly from the official upstream through Resource
Packs. The historical browser/version experiments above are superseded.
Archive size: 361,641,954 bytes; installed browser files: 484,202,247 bytes
(excluding upstream test/setup executables). No Chromium binary is embedded
in the installer or mirrored in release assets.

The actual ResourcePackManager installed the pinned archive in isolated storage,
verified extracted file hashes and passed the owned blank-window browser smoke
test. No test override selected a development executable or changed transport.
Three subsequent fresh session trials passed creation, immediate automatic
browser closure, video metadata and three channel posts without an implicit
browser reopen. Trial 1 also downloaded 1,486,874 bytes of AAC/M4A audio
(60.489 seconds), refreshed the same profile explicitly and inspected again.
Times: 22.37 seconds (including audio and refresh), 7.95 and 7.40 seconds.
These are small local samples, not a reliability benchmark or platform guarantee.

Deterministic tests cover missing-pack notification/no worker, no false install
from a Playwright import, verified archive reuse, repeated-install avoidance,
missing/corrupt file recovery, explicit repair, removal/reinstall, partial-download
discard, cancelled extraction/verification, unsafe inventories, queued-operation
gates, language-independent request gating and staged progress. The current
browser delivery/notice boundary is recorded in douyin-distribution.md.

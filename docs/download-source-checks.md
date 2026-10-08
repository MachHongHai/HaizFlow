# Download source checks

Checked from the source application on Windows, 2026-10-08. Public links only;
no personal browser profile, login or cookie file was used in these probes.
Network probes are not mandatory tests and are not a success-rate benchmark.

## Source inventory

Vimeo, Dailymotion (including dai.ly), VK and Twitch are removed from video,
audio and channel URL acceptance and from the download selector/logo map.
Old schema values remain readable for compatibility; they do not enable a
removed source. X accepts both x.com and twitter.com video links.

| Source | Individual video | Audio | Channel/profile |
| --- | --- | --- | --- |
| YouTube | Live metadata, 19-second public sample | Live AAC download, FFmpeg verified | Live scan returned a candidate |
| TikTok | Live metadata; existing user tests successful | Live download verified in previous follow-up | Live @tiktok scan returned candidates |
| Douyin | Live metadata and 181-second video download verified in previous follow-up | Deterministic routing/expired-media tests; no new live audio probe | Shared-session public posts scan verified in previous follow-up |
| Facebook | Live 40-second NASA video and 8-second video from supplied profile downloaded; FFmpeg video/audio verified | Both samples downloaded as AAC; FFmpeg verified | NASA and supplied profile scanned successfully |
| Bilibili | Live metadata for public video | Deterministic shared audio route; no long live download | Live scan succeeded after video-tab/browser-transport fix |
| Instagram | Live silent video downloaded and FFmpeg verified | Sample exposes no audio; do not claim audio availability | Temporarily disabled by the owner's decision; individual-video downloads remain enabled |
| X | Live 3-second video downloaded; FFmpeg video/audio verified | Deterministic shared audio route; no new live audio probe | Public rendered profile reader verified for supplied `cb_doge`; two candidates and an 11-second silent download verified |
| Reddit | Temporarily disabled in the app | Temporarily disabled in the app | Hidden from selector; readers/schema retained for compatibility and future work |
| Streamable | Live metadata, 12-second public sample | Live AAC download; FFmpeg verified | Not offered as a channel source |

Video-only media can be saved on the **Downloads / Video** page. Audio-bearing
formats are preferred when available. Project source imports keep their strict
picture-and-audio validation: this change must not reintroduce video-only
TikTok/Douyin formats into the dubbing pipeline. Audio download still requires
an actual audio track; it does not invent sound for a silent source. Channel
downloads saved on the Downloads page now share the video-only policy; project
channel imports retain the default requirement for picture and audio.

## Facebook repair and limits

The old profile URL normalizer discarded `id` from `profile.php?id=...`; this
turned a valid profile into a different URL. It also delegated a page to a
video-specific extractor. The new reader preserves identity, requests the
video tab, and reads typed Video nodes only from its `all_videos` connection.
It excludes unrelated recommendations/comments, duplicates, photos and live
streams. Each candidate is hydrated through the existing yt-dlp video path;
failed metadata is not reported as a ready download.

The supplied profile `61573653953774` returned public candidates, including
video `1654788776061864` (8 seconds). That video and its audio were downloaded
and validated locally. This is evidence for this profile, not every Facebook
page. Only the video collection in the initial page response is supported;
no private GraphQL pagination or full-page archive guarantee is added.
Login-gated pages can require cookies explicitly supplied by the user. No
automatic login/CAPTCHA bypass is implemented. Page reads are capped at 4 MiB,
have bounded socket timeout, and check cancellation between reads.

Bilibili uses its video tab and browser-compatible transport from the first
collection request. Collection extraction no longer uses `ignoreerrors=True`
to turn a server block/extractor failure into a misleading empty channel.
Instagram, X and Reddit now have scoped first-party collection readers instead
of delegating unsupported profile URLs to individual-video extractors. Live
channel downloads for Instagram have **not** been verified end to end. Instagram
channels and Reddit are temporarily disabled; X's supplied public profile is now verified below.
They must not be advertised as universally working based on mock tests.

## Instagram, X and Reddit follow-up

The new `social_channel` reader reuses yt-dlp's cookie jar and Chrome-compatible
transport. It does not start browsers, log in, solve verification or silently
read a personal profile. The coordinator accepts explicit cookie-file/browser
authentication parameters, but the channel UI currently has no cookie selector;
adding an opt-in selector is pending the user's choice. Responses are bounded to 4 MiB with 20-second socket
timeout, cancellation checks, and no blind retries on rejected requests.

- Instagram reads the first-party web profile response, filters owner video
  posts, and uses the feed continuation only if the profile reports more posts.
  The same downloader/session is used throughout. Photos and private profiles
  are excluded; pagination is capped at ten pages with duplicate/cursor guards.
- X first reads the public rendered profile timeline in HTML, requires both a
  rendered video and media belonging to that very owner's post, and excludes
  unrelated footer links, photos and quoted-only media. No JavaScript is
  evaluated. The public embed remains one fallback only if the rendered
  timeline is absent; a 429 does not trigger repeated requests. It does not
  promise older pages, full account history or protected-profile access.
- Reddit reads `/r/<name>/new.json` or `/user/<name>/submitted.json`, follows
  bounded `after` cursors and filters native video posts. Photos, deleted posts
  and external link posts are not imported as native Reddit videos. This reader
  is retained but unreachable through new app requests while Reddit is disabled.

Candidates remain subject to individual yt-dlp metadata validation. A failed
hydration is excluded, and an entirely failed scan reports the underlying error
instead of reporting videos as ready. Hydration is serial for these three
sources to avoid bursts of simultaneous account requests.

HTTP 429, access/login rejection, unavailable profiles, empty bodies, HTML
instead of JSON, changed payloads and network failures have separate messages.
No response body, cookie, authentication header or session token is logged.

Live public probes on this machine: Instagram returned 401; the X embed endpoint
returned 429; Reddit's `www` host could not resolve. An alternative Reddit host
returned an HTML shell rather than listing JSON. These are evidence of access/
network limits, not successful channel downloads. No DNS/security changes or
verification bypass were attempted. Exact user profile links are still needed
for targeted live verification of other profiles.

User-supplied profile follow-up:

- `https://x.com/cb_doge`: the rendered public profile returns 200 while the
  embed endpoint returns 429. The scoped reader returned posts
  `2107884615138767108` (17 seconds) and `2107852643205058819` (11 seconds).
  The latter downloaded as 10,053,047 bytes; FFmpeg confirmed video with no
  audio. This exposed and fixed the strict-audio policy leaking into save-only
  channel downloads. Project source imports are deliberately still strict.
- `https://www.instagram.com/zendadbreezy/reels/`: the public page returns 200
  with owner metadata but no usable video listing. Both profile and username
  feed return 401 with `require_login: true`, even after an anonymous public
  page warm-up in the same Chrome-compatible session. The current first-party
  Reels query also returns that requirement. No anonymous endpoint success is
  claimed, and no login/verification bypass was attempted. User consent to an
  explicit cookie-file workflow or temporary channel disablement is pending.
- Reddit is hidden from the channel selector and rejected before network work
  in video/audio/channel URL validation. Historical sessions and schema values
  are not deleted.

Protocol references (independent parsers; no source copied):
[Instaloader profile reader](https://github.com/instaloader/instaloader/blob/master/instaloader/structures.py),
[X public timeline protocol](https://github.com/go-birdsite/twitter/blob/main/twitter.go),
[Reddit listing documentation](https://www.reddit.com/dev/api/).

## Douyin request gate

Video inspection, URL import, channel inspection and remote audio actions are
disabled until the shared Douyin session is ready, and during session creation/
refresh. Enter/Return and direct controller calls obey the same guard. Other
platforms and local audio extraction do not require a Douyin session. Cancelling
or failing a refresh retains the previous ready session; cancelling initial
creation does not enable inspection. No browser is started by the check button.

## Checks

Deterministic tests cover every remaining video/audio route, removed hosts,
Twitter alias, Facebook profile/video identity, collection-only parsing,
non-success/error propagation, read limits, cancellation, hydration,
Bilibili transport/tab selection and download-only silent-video policy.
See `tests/test_social_download_sources.py` plus the shared download suites.
The new `tests/test_social_channel_readers.py` covers profile/feed parsing,
photo/retweet/deleted exclusions, shared cookie jar/transport, bounded pagination,
cursor repeats, error classifications, redirects, network errors, cancellation
and size limits. `tests/test_douyin_session_ui.py` exercises the reactive QML
request gate and direct controller calls without starting a browser.

No installer was built or published. Runtime media, guest profiles, cookies,
browser binaries and probe scripts stay outside Git. See
[Douyin distribution decision](douyin-distribution.md) for the separate browser
licensing boundary; passing download tests does not grant distribution rights.

Final verification: `scripts/test.ps1 -SkipCompile` passed Python correctness
lint, 1,739 tests, 243 subtests and all QML lint (one skip, four existing Qt/
optional TorchCodec warnings). Isolated `haizflow_desktop.py --ui-smoke-test`
exited successfully. Dependency lock manifest verification also passed.
Strict notice generation copied the complete retained browser license texts,
notice and version/hash manifest into its isolated compliance output. This was
not a binary build, OEM approval or public release.

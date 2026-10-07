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
| Instagram | Live silent video downloaded and FFmpeg verified | Sample exposes no audio; do not claim audio availability | Current upstream profile extractor fails; explicit unavailable message |
| X | Live 3-second video downloaded; FFmpeg video/audio verified | Deterministic shared audio route; no new live audio probe | No profile collection extractor; explicit unsupported message |
| Reddit | Live probe failed at DNS resolution on this machine | Deterministic shared route only | No collection extractor; explicit unsupported message |
| Streamable | Live metadata, 12-second public sample | Live AAC download; FFmpeg verified | Not offered as a channel source |

Video-only media can be saved on the **Downloads / Video** page. Audio-bearing
formats are preferred when available. Project source imports keep their strict
picture-and-audio validation: this change must not reintroduce video-only
TikTok/Douyin formats into the dubbing pipeline. Audio download still requires
an actual audio track; it does not invent sound for a silent source.

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
Instagram profile, X profile and Reddit collection support remains incomplete;
their selectors are retained, but they now report that limitation explicitly.
Further platform-specific collection work is needed before advertising all
channel sources as working.

## Checks

Deterministic tests cover every remaining video/audio route, removed hosts,
Twitter alias, Facebook profile/video identity, collection-only parsing,
non-success/error propagation, read limits, cancellation, hydration,
Bilibili transport/tab selection and download-only silent-video policy.
See `tests/test_social_download_sources.py` plus the shared download suites.

No installer was built or published. Runtime media, guest profiles, cookies,
browser binaries and probe scripts stay outside Git. See
[Douyin distribution decision](douyin-distribution.md) for the separate browser
licensing boundary; passing download tests does not grant distribution rights.

Final verification: `scripts/test.ps1 -SkipCompile` passed Python correctness
lint, 1,704 tests, 243 subtests and all QML lint (one skip, four existing Qt/
optional TorchCodec warnings). Isolated `haizflow_desktop.py --ui-smoke-test`
exited successfully. Dependency lock manifest verification also passed.

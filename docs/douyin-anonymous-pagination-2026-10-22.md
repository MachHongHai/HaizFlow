# Anonymous Douyin channel pagination investigation

Local Windows checks on 2026-10-22, using the existing unmodified Chromium
157.0.8092.0 resource pack and Playwright 1.63.0. No CloakBrowser, login,
personal browser profile, proxy service, media download or project mutation.
Every owned diagnostic browser/context/driver was closed after its bounded test.

## Reproduced behavior

The latest application log shows a successful first `/aweme/v1/web/aweme/post/`
response followed by three HTTP 200 responses of only 17 bytes, classified as
`continuation_withheld`. The body is exactly `{"status_code":0}`: neither
`aweme_list`, `has_more` nor a next cursor is present. This is not a valid final
page and must not be represented as a complete scan.

Read-only trials used the channel already recorded in download project `c`.
The exact saved URL was used; visually transcribing its case-sensitive ID is
unsafe because uppercase I and lowercase l are easily confused.

| Request | First response | Continuation |
| --- | --- | --- |
| Existing native request, count 40 | 43 items; has_more 1 | Empty 17-byte envelope |
| Same cursor with cut_version 1 | Not restarted | Same empty envelope |
| Same cursor with profile Referer and cut_version 1 | Not restarted | Same empty envelope |
| Fresh guest, count 18 and cut_version 1 | 21 items; has_more 1 | Same empty envelope |
| Fresh guest, count 100 and cut_version 1 | 44 items; has_more 1 | Same empty envelope |
| Douyin's own page in owned Chromium, normal scroll | 21 items, count 18 | Site-generated second request also empty |

Successful first-page responses included
`not_login_module.guide_login_tip_exist: true`, with a prompt to sign in to see
more recent works. This signal alone is not enough to reject a valid first page;
it is supporting evidence alongside the actual withheld continuation.

The site's own requests also included webid, cut_version and media capability
parameters absent from some native requests. Those requests still failed on
continuation, so simply adding these fields, keeping Chromium resident or
switching from native signatures to the site's SDK is not a demonstrated fix.
The normal Chromium test did not modify the page's signatures, fingerprint or
network requests and did not solve a verification challenge.

## Conclusions and boundaries

- There is no fixed 43-video limit in the application loop. The returned first
  page, rather than the requested overall scan count, determines this result.
- Increasing the requested first-page size to 100 did not yield 100 videos.
  Do not raise body-size limits or change production page sizes based on that
  unproven workaround.
- These trials locate the current refusal upstream of HaizFlow, including on
  the website's own anonymous requests. They do not prove a permanent universal
  anonymous limit, nor that every account/IP/time window behaves identically.
- Existing partial-result notices, real server cursors, bounded retries,
  cancellation, same-identity caching and immediate browser closure are retained.
- No production code is changed by this investigation. No success claim of
  50/100-video anonymous pagination is justified by the observed results.
- An optional signed-in, application-owned Chromium profile would require a
  separate user decision: the current requirement is anonymous-only. It should
  not be silently enabled, and no personal Chrome/Edge cookies should be read.

Reference research (not a local acceptance result):

- <https://github.com/jiji262/douyin-downloader/blob/main/core/api_client.py>
- <https://github.com/eric1981/douyin-monitor>

The latter project also documents that unsigned-in web sessions expose only a
limited public subset and uses an explicitly signed-in owned browser session.
Neither repository constitutes evidence that HaizFlow can reliably obtain a
complete channel anonymously.

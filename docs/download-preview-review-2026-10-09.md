# Download checkpoints and long-video preview follow-up

## Evidence and changes

- Douyin logs show successful first-page HTTP 200 responses of about 2.24 MB,
  followed by 17-byte continuation responses classified as risk control.
  This is not proof that the anonymous session expired. Popular scans now
  pace pagination, retain successfully read pages, report the incomplete scope,
  and resume the cursor on a subsequent scan using the same session. A local
  five-minute, four-profile cache is bounded to the existing 1000-post cap.
  Refreshing the identity invalidates reuse. No Chromium auto-launch was added.
- The post query includes the browser-profile platform field and the empty
  optional cut token, following the endpoint parameter contract in
  [Evil0ctal's Douyin parameters](https://github.com/Evil0ctal/Douyin_TikTok_Download_API/blob/main/src/dtk/platforms/douyin/params.py).
  No server, pool, external download service, or additional signing algorithm
  was added. Existing Apache-2.0 attribution remains in place.
- Channel sessions already persisted candidates and selections, but the QML
  form reset on reopening and hid those results. Download projects now save
  the tab, forms, public preview metadata and selected audio file atomically in
  `downloads/workspace.json`. Changes are debounced and flushed on navigation
  and shutdown. Old channel session files hydrate the form automatically.
  Inspection generations prevent late results from leaking into another project.
  Workers are not falsely restored as running after an application restart.
  Cookies, authentication settings, signed media URLs and transient errors are
  not part of the new workspace checkpoint.
- `testre` has 295 subtitle and voice clips. Sampling the first 20 generated
  clips with the same silence trimming/fit policy found audible durations
  shorter than their ASR slots by a median 1.301 s (maximum 2.515 s). The live
  caption renderer had stopped consuming the published `voiceTimings` map.
  Karaoke now uses matching narration timing while retaining subtitle visibility
  and editable timeline bounds. Old audio with different text is not used to
  time newly edited text. This remains duration-based karaoke, not phoneme alignment.
- OCR post-processing still needs a treated video proxy. Its patch feather
  mask is constant; the editor now computes it once rather than performing
  RGB per-pixel expressions on every frame. Production export remains unchanged.
  A warm 20-second `testre` excerpt measured 2.002 s before versus 1.363 s with
  the static mask in one local run. This is not a full-video or cross-hardware
  benchmark. Trying ultrafast encoding did not help and increased size, so the
  existing encoder preset was retained.
- Gemini 3.8 is unavailable in the shared model selector. Stored model IDs
  remain compatible; existing project settings are not silently rewritten.

## Verification and limitations

Focused deterministic tests: 96 passed, including workspace migration,
cross-project isolation, cancellation, throttled pagination/resume, narration
clock/visibility, real FFmpeg mask repetition and existing download queues.
The repository verification gate subsequently passed: 1915 tests, 251 subtests,
one skip, Python compilation/correctness lint and QML lint. Four existing
warnings include the local pyannote/TorchCodec decoding environment warning;
the gate is not a real-model hardware benchmark. An additional QML checkpoint
test was run separately (four checkpoint tests passed) and confirms that restored
channel results remain visible across project switching.

Douyin can still enforce upstream rate limits. Partial scans explicitly report
the scanned scope; the list is not presented as a complete top-view ranking.
The new pagination behavior has not yet been verified against the user's live
anonymous session. No CAPTCHA bypass or personal-profile cookie access is used.
Long OCR proxy creation is faster in the excerpt test, but is not instantaneous.
Full 16 GB CPU inference and subjective headphone sound quality still require
real-user/model testing. No build, commit, push, or publication was performed.

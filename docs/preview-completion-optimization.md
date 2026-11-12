# Faster preview preparation after OCR and voice publication

## Scope

Reduce preparation latency after a completed Manual tool. This does not change
OCR/TTS inference, export encoding, subtitle clocks, speech trimming or tempo
fitting. No project data or existing project cache was cleared for testing.

### Visual preview

`EditorPreviewController._render_current` opens a thread-local probe batch.
Source dimensions/duration and successful output validation are reused only
inside that one render transaction. Cache identity includes device/file ID,
size, nanosecond modification/creation times and probe timeout. Filesystems
without file IDs use the resolved path. Atomic publication can reuse a probe
for the same unchanged file after rename; replacement or content changes must
probe again. Failures/zero durations are not cached. Export outside this scope
retains the previous probe behavior.

All mask chunk keys, completion markers, source/OCR validation and sequential
encoding remain unchanged. A long first preview still needs to render its
uncached treated pictures; this is not an incremental first-frame pipeline.

### Voice preview

The existing audio worker prepares at most eight compatible speech clips per
FFmpeg invocation. Trimming, target duration, atempo chain, stereo and 48 kHz
settings are identical to the individual decoder. Each output is validated
before atomic PCM publication. Groups are consumed before preparing the next
group, so the memory-cache limit cannot evict all early clips before use.

Only cold/missing clips enter the batch. Unusual media/FFmpeg errors retain
the previous individual decoding path. Cancellation is not treated as a codec
fallback: it kills the active process and does not publish partial PCM.
Temporary Windows mappings are closed on aborted publication.

The path-keyed PCM cache from before immutable TTS cache identities can still
be read, with the same path/size/mtime/slot/fitting validation. Existing files
are not renamed or rewritten just to adopt the new in-memory key.

## Local verification

- Real `tttk` source and OCR geometry (88.511 s), rendered into isolated
  temporary directories, not into the user's project. Four ABBA runs:
  baseline 6.808 / 6.837 s; optimized 6.352 / 5.832 s. Median 6.823 → 6.092 s
  (about 11% in this run). FFprobe calls 42 → 19. All four final video SHA-256
  values are identical. Timings depend on other machine activity.
- Existing 34 published speech clips, using their real slot/fitting settings:
  individual cold preparation 5.445 s → batched 3.641 s (about 33%). FFmpeg
  processes 34 → 5. PCM is byte-identical for every clip. Warm lookup ~2.7 ms.
  This measures preview PCM preparation, not model generation time.
- Real-media regression cases include 16/22.05/24/44.1/48 kHz, mono/stereo,
  short speech and multiple atempo stages. Tests cover cache compatibility,
  cancellation during publication, failed-batch fallback, persistent reuse,
  bounded groups, probe mutation/rename, nested scopes and thread isolation.
- Related Python/Qt model suite: **232 passed**. Artifact:
  `build/preview-completion-optimized-20261108.xml`.
- Entire Qt Quick suite: **159 passed**, zero failures/errors. Artifact:
  `build/qml-preview-completion-20261108.xml`.
- Ruff F, compileall and `git diff --check` pass. No new dependencies, build,
  push, model/API calls, or release publication.

Local reproduction scripts (ignored diagnostic artifacts):
`build/benchmark-preview-completion.py`,
`build/diagnose-preview-completion.py --decode`.

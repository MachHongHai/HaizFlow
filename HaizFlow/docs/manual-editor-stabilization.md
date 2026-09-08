# Manual editor engineering status

[Documentation](README.md) · [Architecture](architecture.md#7-manual-editor-and-artifact-graph) · [Tiếng Việt](manual-editor-stabilization.vi.md)

This note separates implemented editor behavior from remaining acceptance work. It is a maintenance record, not a user guide or a claim that every media/device combination has been certified.

## Implemented

- `ManualSubtitleModel` provides stable segment identity, revision-aware saves, session draft retention, atomic working documents, and serialized immutable publication.
- `SubtitleTextEditor` provides a full-height wrapped editor, 500 ms autosave, immediate focus-loss commit, save status, retry, and Windows IME commit before focus actions.
- `SubtitleOverlayRenderer` uses the export ASS writer and font path to create normal/karaoke transparent sprites; selection bounds derive from rendered alpha rather than QML text metrics.
- Manual result video does not intentionally burn translated captions into the base proxy; the subtitle overlay is a separate layer.
- Preview transport, fullscreen, and timeline share scrub state with consolidated seeks and source-generation rejection.
- Result audio is owned by one preview audio controller/output. Source, separated background, speech clips, and music share one clock; level changes do not rerender video.
- Text edits invalidate speech only for the changed segment. Timing edits reposition cached clips without invoking TTS.
- OmniVoice can retain a warm worker for bounded idle time. Edge TTS uses a serialized per-video path and content-addressed sentence clips.
- Edit history is separate from navigation history and records supported text, timing, media, voice, audio, visual, project, publishing, and application-setting changes in their owning context.
- Voice manifests activate only if their subtitle document signature is still current when generation completes.
- Preview artifacts are published atomically and stale callbacks are rejected by generation/revision.

## Verified by automated coverage

- Long Vietnamese/Unicode drafts survive save, reload, and stale revision callbacks without trimming.
- A dismissed subtitle editor commits the full draft once.
- Subtitle alpha bounds use renderer output and do not reuse a previous phrase on a cache miss.
- Repeated seek operations reuse and release one audio output in the test abstraction.
- Manual inspectors instantiate with the real controller under an isolated Qt runtime.
- Voice cache tests distinguish text invalidation from timing/style changes.
- Python compilation, correctness lint, unit/integration tests, and QML lint are part of `scripts/test.ps1`.

The current test count is intentionally not embedded here; the gate output from the reviewed commit is authoritative.

## Remaining acceptance work

- Pixel-level karaoke comparison between idle preview, selected preview, and a final exported frame on representative real media.
- Windows hardware-audio stress testing across repeated source swaps, 100+ seeks, device changes, suspend/resume, and workspace shutdown.
- Long-duration decode/memory validation. The PCM cache is bounded, but a single very long track still needs a measured windowed/memory-mapped strategy.
- Crash-interruption tests for pending subtitle publication and voice refresh at every atomic boundary.
- Real-provider Edge TTS outage/rate-limit recovery and retry UI across multiple locale voices.
- Ownership tests proving every Manual worker and media connection is released after rapid project switching.
- Cache quota acceptance with active/pinned artifact protection under low-disk conditions.

## Regression invariants

1. Seeking never starts OCR, translation, TTS, separation, or final render.
2. Selecting a different voice changes requested voice state only; it does not replace the active preview audio until the user generates or activates a complete matching voice artifact.
3. A stale voice, subtitle, preview, or media callback cannot activate over a newer revision.
4. Subtitle size and position do not change text, timing, or TTS identity.
5. Timing changes do not call a TTS provider.
6. Image mode changes do not call recognition or translation.
7. Audio levels do not call a model or rebuild the visual proxy.
8. Export consumes the current valid optional layers and does not silently run missing tools.
9. Leaving the workspace stops one audio owner and releases player connections without affecting unrelated project workers.

Any change that violates an invariant requires an architecture decision and new acceptance criteria, not a local UI workaround.

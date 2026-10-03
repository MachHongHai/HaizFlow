# Runtime, media quality and editor review — 3 October 2026

Scope: storage, Auto performance, speaker selection, social publishing,
Gemini diagnostics, hnk3 audio, hnk4 alignment, hnk5 OCR, export notifications,
Vietnamese input, pointer focus, preview scrubbing, trim/cache reuse and long
Manual projects. No installer build, commit or push is authorized.

## Evidence collected

- `full`: the worker completed rendering successfully at 12:10:06 UTC on
  2 October. The reported unresponsive state therefore requires investigation
  of result ingestion, timeline construction and preview loading as well as
  worker execution. There are 204 voice segments.
- `hnk4`: retained recognition artifacts place “Please, just give me
  something to eat.” at 21.647–28.609 seconds. The user confirmed that multiple
  artifacts are expected from repeated tests and that the editable timeline
  was shortened manually. Multiple artifacts are not evidence of a cache fault.
  A separate decode of the source audio places the spoken sentence at
  21.28–23.58 seconds. Timing verification runs only on new recognition output;
  existing editor adjustments and retained artifacts are not rewritten.
- `hnk5`: OCR selected a 59.58% × 13.05% region with an estimated line height
  of 4.27%. Static mixed-case board labels were merged into the all-caps
  subtitle band. Re-evaluating the same 36 sampled frames after filtering
  produces a 55.83% × 6.33% region at x=21.25%, y=67.72%. The actual two-line
  subtitle remains covered; the old project artifact was not overwritten.
- `hnk3`: several existing generated clips contain wrong-language speech
  before mixing, including clip 53, whose expected Vietnamese sentence was
  decoded as English repetition. Its source reference is only 1.264 seconds.
  The separate no-vocals stem did not decode full original sentences in the
  inspected 91.185–100.338 and 111.457–119.101 second windows. This narrow
  check does not establish perfect Demucs separation across the entire video.
- Social publishing previously enabled “Publish all” from total item count,
  although the worker considered only waiting items. Completed rows hid the
  menu containing caption copy.
- Subtitle saving previously cleared focus without an explicit input-method
  commit and did not give the parent dialog an acknowledgement per save.

## Changes implemented

### Storage and cache ownership

- New processing projects no longer create an unused project-root `exports`
  directory. An empty legacy directory is removed only after the project
  manifest matches its identity and containment/no-reparse checks succeed.
  Non-empty legacy exports remain untouched and readable.
- Ten verified empty project-root export directories were removed from the
  local test collection. No source video, voice clip, manual timeline edit,
  non-empty export directory or processing artifact was deleted.
- `cache/export` is retained deliberately: it holds immutable render artifacts,
  not the user's destination exports. External export files remain under the
  explicit ownership of the user. Temporary processing files and legacy
  compatibility locations are not mass-renamed while the application is open.
- Structural observations are reused only within one tool-state evaluation.
  A subsequent evaluation sees filesystem changes. Worker consumption retains
  checksum validation; presentation shortcuts do not replace that validation.
- Voice cache contract changes apply to multiple-speaker generation only.
  Single narrator and explicit cloning keep their previous cache contracts.
- Explicit source-treatment runs include the image generation in preview
  identities. Patch → blur → patch cannot silently reuse an earlier run when
  the user requests a new treatment. OCR geometry remains separately reusable.

### Voice generation and recognition

- Multiple-speaker mode is now a voice-picker option, rather than a separate
  checkbox. Existing per-source-fragment behavior is retained; this change is
  not a new speaker-clustering or diarization algorithm.
- Multiple-speaker fragments shorter than 2.5 seconds, longer than 15 seconds,
  or with insufficient reference text use a stable library reference. The
  generator does not expand a reference into neighbouring speakers' speech.
  Chinese references are checked by character content as well as whitespace
  tokens, so ordinary Chinese sentences remain eligible for cloning.
- A fresh GPU generation of hnk3 clip 53 was written only to the ignored
  diagnostic directory. Independent Small ASR decoded it as
  “Và giờ cuối cùng nó đã là của ta.” Old project clips were not overwritten.
- Source-fragment clone prompts remain short-lived for memory safety. Library
  and single-narrator calls avoid unnecessary per-utterance CUDA allocator
  flushes. The immediately required Manual voice worker can survive the
  foreground warm-up barrier; unrelated speculative models are released.
- Logs distinguish runtime imports, checkpoint loading, reference encoding
  and synthesis, including elapsed seconds. The import interval is visible
  before Torch/Transformers finish importing.
- Suspicious stretched recognition boundaries are checked using the existing
  decoder, exact normalized transcript matching and word confidence. Only
  newly recognized output is refined. Retained artifacts and manually edited
  hnk4 boundaries are not rewritten.

### Editor and UI

- Waveform arrivals emit a coalesced clip notification rather than refreshing
  the entire document for every clip. Tiny timeline clips render only as many
  waveform bars as their display width can accommodate.
- The workspace reads the tool-state list once per binding evaluation instead
  of requesting it twice through a conditional expression.
- Basic contiguous source trims skip the intermediate full-quality sequence
  encode. Compatible treated base proxies can supply the trim, preserving
  source effects. Multi-decision/tail-extension edits retain the existing
  sequence-materialization path.
- Manual preview distinguishes source-media time from edited-sequence time.
  The source monitor uses original offsets, while the treated proxy and
  composed audio use the edited clock. Inline and fullscreen transport sliders
  suspend decoder-value bindings while the user holds the thumb.
- Subtitle Apply commits the input method before capturing the draft. A
  per-save acknowledgement closes the dialog, including subsequent saves and
  applying unchanged text. Edits made during a pending save remain drafts.
- Pointer clicks no longer show keyboard focus outlines on shared buttons,
  switches, checkboxes, menus and selection controls. Keyboard focus remains
  visible; text inputs keep their normal editing focus indication.
- Export displays the filename, quality and a compact selectable destination
  row. A global success notification remains independent of the export dialog.

### Publishing and Gemini

- “Publish all” uses the same eligible-item predicate as the worker. The backend
  also refuses already published/scheduled items; ambiguous remote-ID failures
  are excluded from bulk retry. Provider idempotency remains part of individual
  failed/partial retries.
- Completed rows retain their menu and caption-copy action.
- Gemini selection warns about token charges on billing-enabled projects.
  HTTP 402/403 billing/permission failures, 429 quota failures and temporary
  503 unavailability have distinct explanations. A 503 is not interpreted as
  evidence that a free-tier key cannot use a model. Retry remains bounded.
- Official references checked on 3 October 2026:
  [Gemini troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshooting)
  and [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing).

## Measurements and verification

| Check | Observed result |
| --- | --- |
| Full Python suite | 1,085 passed; 121 subtests passed |
| Qt Quick interaction suite | 71 passed; no failures or skips |
| Latest targeted Manual/UI suite | 86 passed |
| Latest menu/localization suite | 53 passed |
| Final voice/cache/timing/trim regressions, including Chinese references | 92 passed |
| Python error lint / changed-QML lint / diff whitespace | Passed |
| `full` tool-state read | 1.297 s before; approximately 0.136–0.166 s after |
| `full` document load / read-only reconcile | 0.157 s / 0.243 s |
| Actual 410-clip timeline in isolated offscreen harness | Initial load 0.231 s; maximum event-loop interval 0.119 s during repeated clip refreshes |
| GPU, same short sentence, sequential requests in one worker | Cold 29.919 s; warm 3.130 s |
| Cold GPU request breakdown | Imports 15.249 s; checkpoint 8.816 s; reference 1.565 s; synthesis 3.594 s |
| Warm GPU request breakdown | No import/checkpoint/reference reload; synthesis 2.897 s |

The real FFmpeg trim regression uses distinguishable raw/treated pixels. It
confirms a one-second trim comes from the treated cache, not the raw source,
without materializing an intermediate source sequence.

## Limits and follow-up validation

- Warm/cold measurements cover one short GPU utterance, not an end-to-end Auto
  CPU/GPU benchmark. Cold imports and large-model loading still cost time; no
  inference quality reduction or overlapping model allocation was introduced
  to conceal that cost.
- The long-project timeline test is isolated and offscreen. It does not replace
  reopening `full` in the user's running application and checking playback,
  live worker completion and navigation together.
- Vietnamese Unicode/repeated-save tests pass, but actual Windows input-method
  composition with the user's keyboard software still needs a live retest.
- No paid Gemini call or real social publication was made during verification.
- The development environment still warns that TorchCodec cannot load its
  native decoder. WhisperX receives predecoded waveforms, but this remains an
  environment warning rather than a claim that every dependency is flawless.
- The export layout was inspected with an isolated Qt capture. Offscreen font
  fallback is not representative of native Windows icon rendering.
- No installer/executable was built. No commit or push was made. Diagnostics
  did not replace user media or edit existing subtitle/timeline content.

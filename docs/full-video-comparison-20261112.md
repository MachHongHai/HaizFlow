# Fresh full-workflow comparison: supplied 88.511 s video

## Input and baseline

User input:
`C:/Users/ADMIN/Downloads/SnapTikTok.to_7650805150759636264.mp4`.
Size 27,086,032 bytes, 720 × 1280, duration 88.511 seconds.
SHA-256 before/after the trials:
`e18c4d89d68086535a5cdc2ed4415957c3631c910b9ee0f58a149a1a2315e160`.
The original file is unchanged.

Baseline is the complete source at `v1.0.4`, commit
`b5b28cca015d10e49324eb3d50b960e69c1a8198`, not the packaged EXE.
Critical pipeline, Gemini, OCR, engine and controller Python files are checked
byte-for-byte against the Git tag by `summarize_fresh.py`. Each child receives
the tested source tree through `PYTHONPATH`; unlike the earlier controlled
handoff test, the worker Python implementation also comes from that version.
Both trees use the same venv/native dependencies, installed models/SDK,
FFmpeg, machine and Qt offscreen/software backend.

This comparison does not establish parity with two packaged EXEs, Windows
interactive GPU rendering or app startup. The published Core asset provenance
and a separate actual-EXE UI test are documented in
[the earlier preview audit](release-dev-performance-20261112.md).

## User-selected configuration

- Manual project, automatic source language, Vietnamese target.
- Demucs separation, then Whisper Turbo (`large-v3-turbo`) on CUDA,
  float16, batch 8, 8 CPU threads.
- Gemini `gemini-3.5-flash-lite`, natural style, effective thinking level Low.
  1.0.4 has no persisted per-project reasoning field; its natural-style
  request builder selects Low automatically. Dev explicitly selects Low.
- Automatic source-caption OCR, patch treatment, original aspect ratio,
  output speed 1×, no watermark, identical explicit subtitle style.
- VieNeu GPU, multispeaker. Model retention disabled for both test runtimes.

The user explicitly authorized Gemini requests. Existing key selection metadata
is copied into isolated runtimes; the secret stays in Windows Credential
Manager and is never printed. No extra quota/status API requests are made.

## Started from empty results

Each run creates a new Manual project through the normal project/import APIs
and copies only the user's input video. No old source-audio, separation,
recognition, translation, SRT, speaker mapping, OCR, speech, waveform or preview
artifact is imported. The initial active-artifact map must be empty.
Both accepted runs log `Cache miss` for all four requested tools.
Pretrained model files are already installed; OS file caches are not flushed.

The real GUI queues separation → recognition/translation → OCR → speech.
No synthesis/recognition/translation result is stubbed. No export is requested.
Each stage waits for the preview before proceeding. The harness's artificial
1.2 s settling gaps, app startup/import and explicit startup hardware probe are
excluded from the reported processing-plus-preview total.

Processing starts immediately before the normal `runManualTool` call and ends
at the real worker-finished callback. Preview latency then includes GUI event
dispatch, reconciliation, proxy/PCM work, media attachment and a presented
result frame. After OCR, the visual source must change from the previous
unmasked preview; an old visible frame cannot complete the measurement.
After speech, all enabled voice clips must have narration timings.
Polling resolution is 20 ms plus normal Qt frame scheduling.

One initial full-workflow pilot was discarded in its entirety: it counted an
old visible frame before OCR's new mask proxy began rendering. The corrected
accepted runs were Dev followed by 1.0.4, with separate fresh runtime folders.
The discarded pilot also made a user-authorized Gemini translation request;
its apparently fast OCR preview number is not used in any comparison.

## Results

One accepted end-to-end run per version. Seconds, rounded to two decimals:

| Stage | 1.0.4 processing | Dev processing | 1.0.4 preview wait | Dev preview wait |
|---|---:|---:|---:|---:|
| Source audio + separation | 8.78 | 8.65 | 0.63 | 0.43 |
| Whisper Turbo + Gemini translation | 35.15 | 32.43 | 1.20 | 0.75 |
| Source-caption OCR | 10.81 | 12.33 | 7.53 | 7.05 |
| VieNeu GPU multispeaker | 28.71 | 26.67 | 2.86 | 2.69 |
| **Sum** | **83.45** | **80.07** | **12.21** | **10.92** |

Processing plus preview waits: **95.66 s → 90.99 s** in these runs.
This is not launch-to-export wall-clock time.

Both runs finish `manual_ready` without an error and create every required
speech file. 1.0.4 recognition/translation produces **15 cues**, dev **16 cues**;
the respective preview narration counts are 15/15 and 16/16. Therefore this is
a realistic fresh-workflow integration measurement, not a strictly identical
output-workload test. Do not attribute every model-time difference to code
optimization: recognition segmentation, Gemini latency/output, stochastic
speech duration and OS cache state can vary.

All measured post-completion preview milestones are lower on Dev in this
pair. However, OCR processing itself is **1.52 s slower** on Dev, and its
processing-plus-preview sum is **19.38 s versus 18.34 s**. The test therefore
does **not** support claiming every operation is as fast or faster. More
controlled repeated OCR trials would be needed to distinguish a regression
from startup/provider/cache variation.

## Evidence and reproduction

- Aggregated results, input hash and verified tag-file hashes:
  `build/full-compare-20261112/comparison.json`.
- Accepted dev runtime:
  `build/full-compare-20261112/d-1794485124989179200/`.
- Accepted 1.0.4 runtime:
  `build/full-compare-20261112/r-1794485227875379200/`.
- Local ignored drivers:
  `build/release-dev-compare-20261112/run_fresh.py`, `FreshMain.qml`,
  `completion_entry.py`, `summarize_fresh.py`.
- Each runtime retains technical `logs.txt`, application log, stdout/stderr,
  generated project results and the final timing JSON. Credentials are not
  included in the logs or report.

No original project/cache is modified, no production code is changed for this
follow-up measurement, and no build, push or release publication is performed.

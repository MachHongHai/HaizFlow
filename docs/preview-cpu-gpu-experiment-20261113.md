# Post-OCR preview: probe consolidation and NVENC trial

## Final decision after the user's follow-up

The user requested removing the slower GPU preview experiment. All GPU preview
selection, flags and cache-key changes have been removed. Preview remains on the
existing CPU encoder even when AI processing uses GPU. The single-probe
validation optimisation is retained, as are the original 12-second chunk cache
and all existing GPU paths for OCR, TTS and video export. The GPU figures below
are historical experiment results, not the final app configuration. The
benchmark script now supports CPU modes only.
Final retained-CPU regression suite: **226 passed**, plus 2 passing subtests
(`build/preview-retained-cpu-20261113.xml`).

## Implementation tested (GPU branch subsequently removed)

- Validate each generated proxy's duration and video/audio streams with one
  bounded FFprobe invocation. Publish that successful duration into the existing
  transaction-local, file-identity-checked probe cache. No validation is skipped.
- CPU mode retains the existing libx264 preview settings and cache keys.
- GPU mode explicitly requests verified NVIDIA `h264_nvenc` for preview encoding;
  filters, masking, resolution and playback clock are unchanged. AMD AMF is not
  enabled by this change because of the previously documented Qt colour issue.
- NVENC and CPU both declare SDR BT.709, limited range and yuv420p. Encoder
  failure retries the existing compatible CPU preview configuration, with the
  normal failed-encoder cooldown. Non-preview exports keep their existing path.
- GPU preview keys are separate from CPU keys, including per-mask chunk keys.
  App device preference is captured before handing the request to its worker.
- GPU mode was initially kept for testing at the user's request, then removed
  after the final instruction to retain only the better-performing approach.

## Controlled workload

Baseline source: commit `e75bbf555aa93036a31d25811576483853d115d2`, loaded into
private Python modules. Candidate uses local source, same Python/FFmpeg/input,
same actual OCR geometry and full 88.5-second timeline from `testocrdev`.
Source SHA-256:
`e18c4d89d68086535a5cdc2ed4415957c3631c910b9ee0f58a149a1a2315e160`.
GPU: RTX 4060 Laptop 8 GB; NVENC was exercised, not mocked.

Each trial starts with an empty private preview directory. No OCR, translation,
TTS or API calls are included. The benchmark stops at visual proxy completion;
it does not measure the exact QML busy-bar show/hide or first-frame UI delay.
Original projects/cache/settings/installed EXE are not modified.

Latest serial, counterbalanced run (no concurrent pytest/render benchmark):

| Mode | Run 1 | Run 2 | Median | FFmpeg / FFprobe |
| --- | ---: | ---: | ---: | --- |
| Baseline CPU | 6.2788 s | 7.9552 s | 7.1170 s | 9 / 19 |
| Candidate CPU | 5.4847 s | 5.7850 s | 5.6349 s | 9 / 11 |
| Candidate NVENC | 8.4675 s | 8.2531 s | 8.3603 s | 9 / 11 warm |

The first NVENC trial also includes two hardware-probe FFmpeg processes. It
records nine NVENC commands (one capability test plus eight chunk encodes);
the second records eight. Startup and GPU upload overhead outweigh the faster
encoder at these small 486x864, 12-second proxy chunks. There is no GPU decode
or GPU filter-graph migration in this trial.

Raw results: `build/ocr-preview-compare-1794520763738478900/results.json`.
An earlier balanced batch measured baseline/candidate-CPU medians 7.5166/5.7435 s;
a CPU-only batch measured 6.6066/6.3892 s while regression tests were also running.
Do not promise a fixed percentage improvement on other workloads or loads.

## Fewer FFmpeg launches: exploratory grouping, not retained

Separate short experiment: baseline 6.2486/6.0532 s; candidate 24-second CPU
chunks 4.5551 s (five FFmpeg launches); one whole CPU proxy 3.4715 s (one launch);
one whole GPU proxy 4.7239 s including initial hardware probes.
Raw results: `build/ocr-preview-compare-1794520492385146700/results.json`.

Grouping is real headroom, but these modes change chunk reuse granularity:
whole-file preview would encode much more again after a small mask edit or a
stopped partial run. They remain benchmark-only. Production retains 12-second
chunk reuse and cancellation semantics. An earlier `coarse-cpu` result in the
first exploratory batch did not change the class-level chunk size and is
excluded from grouping comparisons; the script has been corrected.

## Correctness

- Every candidate CPU result is byte-identical to baseline, SHA-256
  `827facdf8647328c1ffb1425c7a7031dbb895d0dc251ad8f7ab264343b7b09f8`.
- GPU encoding is lossy and is not byte-identical. The full-clip SSIM against
  baseline's already-lossy CPU encode is 0.963547; this is not a comparison
  against an uncompressed reference and not a claim of equal visual quality.
- Both retain 2,655 video frames, 486x864, 30 fps, yuv420p, BT.709/TV range,
  video duration 88.5 s and container duration 88.531958 s.
- Side-by-side sample inspected:
  `build/ocr-preview-gpu-side-by-side.png`. No obvious colour-channel/range
  corruption was observed in that sample; it is not an exhaustive visual audit.
- A real Qt QMediaPlayer/QVideoSink decoded the NVENC result and delivered valid
  frames after seeks to 12, 24 and 60 seconds.
- Tests cover CPU mode never probing GPU, verified/unavailable NVENC, matching
  colour contracts, captured app preference, cache-key separation, real failed
  hardware encode followed by CPU retry, malformed/invalid probe durations,
  missing audio, file mutation, cancellation, existing cache and exports.

No build, push or publish was performed.

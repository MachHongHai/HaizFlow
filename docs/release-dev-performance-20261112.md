# Preview regression comparison against 1.0.4

## Baseline and isolation

Baseline: release `v1.0.4`, commit
`b5b28cca015d10e49324eb3d50b960e69c1a8198`.
The local full-Core ZIP matches the official GitHub asset SHA-256:
`5e230388cb5f01e1f5c0f6593a23f95a34f0b066954003cc799d1877a2504157`.

Two complementary comparisons were performed:

1. Complete tag source and dev source in separate processes, using the same
   Python environment, FFmpeg and input media. ABBA order, two runs per version.
2. The actual released EXE, tag source UI and dev source UI, serially, two runs
   per version. Only private QML copies contain timing instrumentation; the
   release EXE is unchanged. All use the same offscreen/software Qt backend and
   Windows fonts. This is not a measurement of interactive GPU input latency.

All writes are confined to newly created benchmark runtimes under
`build/release-dev-compare-20261112`. Original projects, caches, exports,
settings and installed binaries are not modified. Existing speech is reused
for the controlled PCM comparisons; no inference/API request is involved there.
The separate real-processing trial below does run local OCR and VieNeu GPU.

## Confirmed regressions fixed

- Python `deepcopy` on cached timeline payloads was slower than rebuilding
  the release payloads. Use the already-installed native Pydantic serializer
  for detached JSON-shaped payload copies. Nested mutations must not leak
  into cached/model data.
- Voice prefetch was followed by another per-clip identity/cache lookup.
  Return prepared samples and consume them directly, in bounded groups of 8.
  Preserve old path-key cache compatibility, fallback decoding and cancellation.
- Reopening a hydrated editor skipped document-change signals but still waited
  the cold-start 180 ms before its first audio request. Schedule that warm
  request on the next event-loop turn; retain the 180 ms delay for cold opens.

## Same-runtime source results

Medians in milliseconds, after fixes:

| Operation | 1.0.4 source | Dev |
|---|---:|---:|
| Cold OCR-treated preview preparation, `tttk`, 88.511 s | 6956.309 | 6229.352 |
| Same visual cache, fresh controller | 43.957 | 43.966 |
| Cold fitted PCM preparation, 34 existing speech files | 5681.130 | 4098.797 |
| Memory-warm PCM lookup + hashing all samples | 6.753 | 7.201 |
| Disk-warm PCM lookup + hashing all samples | 24.679 | 25.736 |
| Timeline properties, first group of 5 reads, 72 clips | 8.232 | 6.340 |
| Timeline properties, warm median group of 5 reads | 4.442 | 1.948 |

Warm PCM has approximately 0.45/1.06 ms additional bookkeeping in this sample;
it is **not claimed to be faster**. The improvement is in cold preparation and
end-to-end UI latency. Visual warm time is effectively unchanged. These small
absolute differences should not be hidden by rounding them into speedups.

Output parity: all visual SHA-256 values match
`827facdf8647328c1ffb1425c7a7031dbb895d0dc251ad8f7ab264343b7b09f8`.
All aggregate PCM SHA-256 values match
`e6f8c1aab178d7759fd85324aebf99c8c4b43f24ef6582d0eb4b864efb72f777`.
FFprobe calls for the cold visual path drop from 42 to 19.

Raw source results:
`build/release-dev-compare-20261112/source-results-1794482972016148300/`.

## Released EXE versus dev UI

Identical relocated `workk1` fixture, 62.467 s, 34 speech clips; medians in ms.
Times start at project selection, not process launch. "Ready" here is the
controller's published visual/audio state, not an inferred model completion.

| Milestone | 1.0.4 EXE | Dev source UI |
|---|---:|---:|
| Cold editor first frame | 1514.5 | 1278.5 |
| Cold visual preview ready | 8178.5 | 7849.0 |
| Cold narration ready | 9202.0 | 7922.5 |
| Reopened editor first frame | 623.5 | 441.0 |
| Reopened visual preview ready | 1452.0 | 1021.0 |
| Reopened narration ready | 703.0 | 581.0 |

Raw records: `build/release-dev-compare-20261112/ui-comparison.json`.
Before the warm-audio fix, dev reopened narration consistently waited an extra
approximately 180 ms; preserve the earlier records in
`ui-comparison-before-warm-fix.json`.

Process startup to first catalog is **not signed off as faster**: this batch
measured 1.0.4 EXE 3.306–3.334 s, tag source 3.729–3.800 s and dev source
4.177–5.567 s. These include different packaging/import/QML cache effects.
A like-for-like packaged dev build and more startup trials are needed before
claiming startup parity. No build or publication was performed for this audit.

## Actual tool completion to displayed preview

The user additionally authorized local inference. The cloned fixture starts
with published subtitle/source tracks but without an active OCR or speech
result. Its old immutable artifacts are kept, but fresh generation identities
ensure both tools really execute. The source UI invokes the normal Manual tool
queue, actual local OCR, and VieNeu GPU multispeaker for all 34 sentences.
GPU detection is run explicitly because the isolation/smoke flag normally
skips it; no CUDA capability is fabricated.

The completion timestamp is the real queue worker's finished callback.
Readiness requires a subsequent accepted visual refresh, idle visual/audio
controllers, the result pane's actual presented-frame latch, and (after TTS)
34 narration timings. One further window frame is observed before recording.
Thus this includes completion queue dispatch, reconciliation, proxy/PCM work,
media attachment/first frame and the visible window update.

This source comparison shares the installed/current local TTS worker and SDK
between both Core versions, intentionally controlling the inference backend.
It measures the **post-processing UI handoff**, not an old/new TTS-quality or
inference-engine benchmark. Local inference outputs are not expected to be
byte-identical across independent stochastic runs.

Two valid local runs per version, medians from actual tool completion to the
displayed, ready preview (milliseconds):

| Completed tool | 1.0.4 source UI | Dev source UI | Reduction |
|---|---:|---:|---:|
| OCR, new treated proxy | 6398.996 | 5248.778 | 18.0% |
| VieNeu GPU multispeaker, 34 new speech clips | 6243.204 | 4635.033 | 25.8% |

Raw individual OCR samples: release 6594.791 / 6203.202 ms, dev
5152.330 / 5345.225 ms. Voice samples: release 6241.064 / 6245.344 ms,
dev 4601.330 / 4668.735 ms. Each voice trial actually generated and verified
34 local outputs; the resulting preview had all 34 narration timings.
The measured OCR provider was CPUExecutionProvider; speech ran on the real
RTX 4060 Laptop GPU. Model inference itself is not included in these numbers.

One pilot falsely counted the still-visible original-source frame before
the new treated proxy began rendering. That entire run was discarded, and a
replacement release trial requires a treated-proxy URL as well as the frame
latch. Earlier retained trials have a mask-render log before their displayed
frame timestamp. Failed harness pilots that skipped the GPU startup probe
are also excluded. These were diagnostic-harness issues, not claimed as app
GPU failures or performance improvements.

Raw results and selected valid trials:
`build/release-dev-compare-20261112/completion-comparison.json`.

## Regression verification

- **259 Python/model tests passed**, including real-FFmpeg PCM parity,
  persistent cache reuse, edited/selected sentence generation, cancelled
  publication, old-cache compatibility, OCR proxy reuse, project reopen,
  source replacement guards, pitch-preserving preview playback and navigation.
  Artifact: `build/release-dev-preview-regressions-20261112.xml`.
- **159 Qt Quick tests passed**, zero failures/errors.
  Artifact: `build/qml-release-compare-20261112.xml`.
- New deterministic guards verify nested cached payload detachment,
  one identity lookup per warm voice request, direct PCM consumption without
  another decoder process, and warm-only removal of the 180 ms audio delay.
  Wall-clock thresholds are deliberately not placed in CI unit tests.
- Ruff F checks, compileall and `git diff --check` passed. No new dependencies,
  build, push, publication, paid API call or user-project mutation.

## Reproduction

The local diagnostic scripts are retained under the ignored benchmark folder:
`measure_paths.py`, `run_source_compare.py`, `prepare_ui.py`, `run_ui.py`,
`run_ui_compare.py`, `completion_entry.py`, `CompletionMain.qml`, and
`run_completion.py`. Do not run UI comparison and completion instrumentation
concurrently: they deliberately reuse private QML copies. Fresh fixture
creation clears only caches within that newly copied, validated directory.

Application-cache cold does not mean OS-file-cache cold. Two samples are not
a universal performance guarantee, and the real-inference trials are
integration checks, not a statistically stable whole-app benchmark. Model
inference, export, networking and large project catalogs outside these paths
are not covered by the preview performance claim.

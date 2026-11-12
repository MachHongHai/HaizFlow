# CPU OCR comparison and correction — 2026-11-13

## User projects (read-only inspection)

`testocrdev` and installed 1.0.4 `testocrexe` contain byte-identical
`SnapTikTok.to_7650805150759636264.mp4` inputs (27,086,032 bytes).
SHA-256: `e18c4d89d68086535a5cdc2ed4415957c3631c910b9ee0f58a149a1a2315e160`.
Both ran a cache-miss image tool, sampled 36 frames and had no translated
subtitle/voice clips. Both produced the same detected region and the same
patched preview hash. Their recorded image-tool durations were 14.652482 s
(dev) and 12.673894 s (EXE). The subsequent visual-cache publication took
6.807719 s and 10.171737 s respectively; these are not exact UI bar/frame
presentation timestamps.

## Confirmed policy differences

The explicit OCR runtime applied a four-worker CPU cap and disabled ONNX memory
pattern planning for every provider. The previous RapidOCR configuration let
ORT choose its CPU thread count and retained its default memory-pattern planner.
This machine has eight physical cores / sixteen logical processors.

CPU sessions now use `min(8, max(1, logical_processors // 2))` workers and enable
memory-pattern planning. GPU sessions keep the four-worker cap and disabled
memory-pattern planning. CPU arenas remain disabled and idle thread spinning
remains disabled for every provider. Sampling, recognition models, inference
batch size, detection thresholds, caches, cancellation and GPU recovery are
unchanged.

## Paired real-frame verification

Command:

```powershell
.venv/Scripts/python.exe scripts/benchmark-ocr-runtime.py <testocrdev/input/video.mp4> --model-directory E:/HaizFlow-App/HaizFlowResources/models/subtitle-ocr --paired
```

The script samples once into a private temporary directory, warms both CPU
engines, and alternates old/fixed inference order on each identical frame.
This reduces cold-start/order bias observed during exploratory whole-run tests.

| Trial | Old dev inference | Fixed inference | Reduction |
| --- | ---: | ---: | ---: |
| 1 | 11.2947 s | 8.5703 s | 24.1% |
| 2 | 9.7634 s | 7.6024 s | 22.1% |

All four results contain 43 candidates with identical `(frame, text)` SHA-256
`fa2fe26c884f15458036100e379882d64f7a80c9f2abf8228d0c917fafbfcacd`
and identical final region: x=14.31%, y=70.31%, width=71.25%, height=4.45%,
confidence=0.991, samples=33. This is an inference-stage comparison, not a new
end-to-end EXE-versus-dev measurement or a guarantee for other hardware.

104 OCR/runtime/sampling/cache/preview tests passed
(`build/ocr-runtime-fix-20261113.xml`); Ruff F checks and `git diff --check` passed.

No original project data or installed binary was modified. No API requests,
build, push or publish. The file/folder dialog investigation was left unchanged
after the user reported that the navigation folders were normal again.

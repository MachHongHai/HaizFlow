# OCR preview cache identity after reopening a project

## Evidence

The installed app's `hnkd` project rendered all six mask chunks again at
20:47:28 on 2026-10-21. Its project log shows preview rendering, not another
OCR detection/model run. The saved project and its source file had not changed
since the first render earlier that day.

Reconstructing the preview settings from the saved video/editor metadata
reproduced both existing keys exactly:

| Crop edge serialization | Base key |
| --- | --- |
| Four integer zeros (new model defaults) | `31d4567dc9770015b51c` |
| Four float zeros (Pydantic reload) | `36c9d8663a05a0362603` |

Both preview files have identical SHA-256:
`3b0828b1a4feac39a7de2aa88af3c6bf893c11f21443e5ce4cfcb426a4cb64b8`.
The numeric spelling alone invalidated the request, source-effects and chunk
keys even though it cannot change any rendered pixels.

## Fix

- Canonicalize whole crop numbers before hashing; retain fractional precision.
- Read compatible pre-fix cache keys (including mixed integer/float edges)
  without renaming, rewriting or re-encoding the old cache.
- Keep the exact-key lookup lazy/O(1), without compatibility enumeration on
  the normal hit path.
- Reuse completed pre-fix mask chunks when resuming an incomplete proxy too.
- Continue validating completion markers and file sizes. Compatibility never
  ignores source identity, region geometry/timing, crop edits or encoding.
- Do not change OCR detections, subtitle/audio/voice artifacts or project data.

## Verification

Read-only reconstruction against `hnkd` restores the existing base directly,
with FFprobe forbidden and without starting a render. No project cache was
deleted or modified.

Regression coverage includes all 16 edge-type combinations, three repeated
project reloads, fractional edits, changed source/OCR/timing/encoding, broken
cache, multi-cut sequences and completed chunks from an interrupted preview.
The focused preview/render/cache suite plus artifact/view-state tests passed:
214 tests and 2 subtests. New tests pass Ruff; the controller passes Ruff with
its pre-existing E501 line-length findings excluded. `git diff --check` passes.

No build, push or release was performed.

# Batch and Manual project isolation — 2026-11-12

## Findings and changes

- The shared export controller intentionally retains paused batch jobs when another project exports. The progress dialog incorrectly displayed that global list. It now captures the opening project's video IDs and uses a separate, incrementally updated list model. Cancel and retry actions use that same captured scope; unrelated jobs remain owned by the global queue.
- A cached Manual document payload could be read re-entrantly after the document changed but before the final `changed` signal invalidated it. Payloads now invalidate before selection notifications. Caption input, editor overlays and the shared subtitle renderer also validate the selected video owner. Stale workspace timers cannot configure the renderer for another project.
- Batch settings previously preserved all settings of any video considered an override, even when only one field differed. The UI now defaults to explicitly replacing individual overrides, with the existing opt-out still available. Applying shared settings refreshes the selected video's facade before its autosave can restore the old settings. Initial shared defaults are normalized consistently with the active device.
- Batch processing/export accepts only unique IDs from the captured batch. The scope picker defaults to unfinished videos for processing, supports all videos and explicit selection, and only prepares/enqueues selected videos. Continue remains the separate checkpoint-resume action.
- Recursive restart preflight/cache retirement runs outside the QML click handler. Completion returns to the Qt dispatcher using captured IDs, including cancellation during preparation and navigation to another project. Batch folder selection uses a non-blocking Qt dialog with explicit overwrite confirmation.
- Batch cards now expose confirmed per-video deletion. File removal runs in a worker, respects active queue/export ownership, preserves external input/export files via the existing owned-workspace deletion service, and cannot clear a new selection after navigation.

## `w3` log assessment

Read-only inspection of the project's log found:

- `2026-11-12T15:23:35Z`: HTTP 429 returned by the provider; the existing user-facing error correctly identifies provider rate/capacity limits rather than asserting the user's quota was exhausted.
- Liquid `liquid/lfm-2.5-2.6b:free` completed three translation chunks (36/52 cues). The fourth chunk finished with `stop` but failed `missing_sentences` validation. This reason is triggered by an incorrect translation-array count, before ID/type validation. The raw provider response was not retained, so its missing content cannot be safely reconstructed. No validation was weakened or positional remapping introduced.

No new online inference/API requests were made for this investigation. Real project files were inspected, not rewritten or deleted.

## Verification

- Main related regression suite: 340 passed, including real Qt dialog updates, render/export filesystem ownership, API error/mapping validation, navigation, Manual subtitle editing and new batch/project isolation tests.
- Additional batch/media/preview integration suite: 223 passed, including deterministic offline AI substitutes with real FFmpeg media processing.
- New scope dialog rendered offscreen and visually inspected at 1050×780; footer remains inside the dialog. Artifact: `build/batch-scope-ui-20261112.png`.
- QML lint on changed screens, Python F checks, compilation and `git diff --check` passed.

These are regression/simulation checks, not a new end-to-end inference run against the user's live `work`, `w3` or `w4` projects. No release build, push or publish was performed. The earlier EXE/dev performance comparison remains separate; its final Dev voice measurement is still pending.

# Batch audit — 2026-10-24

## Scope

Reviewed Batch imports and their project/configuration snapshots; shared defaults versus per-video overrides; CPU/GPU and missing-resource preflight; serial queue ownership; Pause/Resume/Restart/Cancel; render/copy progress and destination ownership; cache signatures; settings history; and Batch dialogs/cards. Gemini translation remains supported; Gemini TTS has not been reintroduced. No release build or publication is part of this audit.

## Reproduced and corrected

1. Batch asset Undo used short-circuit restoration. If a later video was busy or missing, earlier videos could already have been changed while Undo reported failure. All members are now checked before restoration. Mid-operation restore/save failures roll back attempted members; failed rollback is reported, not silently treated as success. History is not consumed on failure.
2. Failed shared-settings commits restored configuration/assets but not lifecycle fields changed by the operation. A completed video could remain Pending with zero progress after a disk/save failure. Rollback now also restores status, progress, step, resume hint and error. Capturing the after-state is inside the guarded operation, before committing shared defaults. Shared-default persistence also restores the previous project manifest/index if the second metadata write fails; recovery metadata must not retain defaults that the operation reported as rejected.
3. Batch Pause could overwrite Done, Failed or Awaiting Review when the active video finished between queue detachment and process shutdown. Terminal/review results are now preserved at both boundaries. Waiting members still pause without clearing their completed files.
4. A Pause/Cancel received during the queue-start/device handoff could be overwritten by the startup callback's Processing write. Startup now re-reads the video after handoff, honors stop flags before writing, and reconciles stop requests received during the metadata write without erasing the resume hint.

## Verification

- `tests/test_batch_transaction_safety.py`: deterministic failure/race injection, including a busy later member, failed shared-default write, partially failed Undo, stop during device activation/metadata update, and completion during queue detachment/process shutdown.
- `tests/test_render_export_storage.py`: real filesystem regression for failed Batch settings commit. The existing completed render, its bytes, artifact identity, checkpoint and current-render validity must all survive rollback.
- Existing Batch, multi-project queue, stop/resume, translation checkpoints, resource/device preflight, export/cancel ownership and offscreen Qt tests are retained. The full test script also runs storage/clone suites in their separate Qt process and checks QML diagnostics.

Results: the main application suite passed 3,279 tests (one skipped, 317 subtests). After the final metadata recovery correction, the complete isolated storage/clone suite passed 70 tests (one skipped, five subtests); the focused Batch/queue/stop-resume suite passed 156 tests. Python correctness lint and all workspace QML diagnostics passed. Metadata fault injection covers failure both before and after the index write, preserving manifest values, index order and the previous valid recovery backup.

Tests use isolated runtime roots and synthetic service/model failures. They do not modify user projects, call paid cloud APIs, or run a multi-hour GPU inference job. Persistent OS/storage failures can also prevent rollback; those failures are reported and must not be described as a successful save/Undo.

## Real-pipeline simulation follow-up

`tests/test_batch_pipeline_simulation.py` runs the production FIFO queue, pipeline, metadata store, run-owned rollback, checkpoints, subtitle formatting, FFmpeg extraction, audio mixing, rendering, immutable publication and export copying. AI recognition/translation, Demucs/OCR inference and online speech requests are replaced with deterministic offline results. Tiny valid MP4/WAV/MP3 fixtures (synthetic test tones, not speech-quality samples) keep the tests bounded and independent of network/GPU availability. Unicode project paths exercise Windows decoding. Background-thread exceptions are test failures, not ignored warnings.

Additional reproduced corrections:

- Audio extraction decoded FFmpeg output with the Windows default code page. UTF-8 paths caused `UnicodeDecodeError` in subprocess reader threads. Extraction and tempo-fit text pipes now explicitly use UTF-8 with replacement for malformed diagnostic bytes, without changing media decoding.
- Pause during translation reran completed audio extraction and Demucs on Resume. Both have input/model-policy checkpoints now. Unchanged complete outputs are reused; missing masters/stems or changed source identity require regeneration. Explicit Restart still clears these checkpoints.
- The audio timeline cache depended only on speech-generation inputs, not the actual clips. A recreated missing clip could leave the old mix/render reusable. The timeline signature now includes each completed clip's file state so regenerated/changed audio rebuilds downstream results while unchanged clips remain reusable.

The simulation covers failures at six pipeline stages followed by successful queue continuation/retry, Pause/Resume at seven boundaries, partial voice reuse, missing files and changed sources, clean Restart, new-run Cancel cleanup, cancellation restoring previous render/clip/mix bytes, 2x output duration, translation review/approval, and both blur and patch covering through the real renderer. It does not claim to validate AI output quality or hours-long model behavior on customer hardware.

Final follow-up results: 254 combined pipeline/Batch/queue/resume/audio/GPU-recovery tests passed, plus both real cover-mode cases (25 simulation cases in total). The separately isolated storage/clone suite passed 70 tests with one skip and five subtests. Total: 326 passed, one skipped. Source correctness lint, simulation-test lint, compilation and `git diff --check` passed; no new model dependencies or QML changes were introduced.

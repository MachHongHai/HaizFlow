# Media and resource packaging — 0.1.9 technical review

Reviewer: Codex. Date: 2026-10-10 (Asia/Saigon). This is a scoped technical
packaging review, not independent legal or patent certification. The owner
explicitly requested build/publication and authorized commit and push of the
tested source for 0.1.9 in the current conversation.

The reviewed FFmpeg CLI, Qt/PySide modules, CPU/CUDA PyAV backends, model
checkpoints, preview voices, fonts, browser delivery and license terms are
unchanged from 0.1.8. Dependency lock files and media build recipes are unchanged.
No CloakBrowser component is introduced. Chromium remains an optional upstream
resource installed on explicit user request.

Owned application changes cover resource relocation, editor seek/layers/result
segments, bounded segment export, cache publication, Windows metadata retries,
Whisper compute capability selection, CPU memory handoff and OmniVoice inference
activity, and invocation-local GPU-to-CPU recovery. The corresponding-source
archive for 0.1.9 inventories the same exact reviewed media source closures,
compiler/CRT inputs, linked-library sources, Qt/PySide sources, recipes and
notices. It must be published alongside the binaries and verified against
runtime/third-party-sources-manifest.json.

CPU 11, CUDA 13 and vision 6 are rebuilt from committed owned application code
using the unchanged reviewed dependency locks and media recipes. JSON protocol
1 and runtime contract 6 remain compatible. Model files are reused, but updated
engines are required for the application-worker fixes to reach installed users.
CPU voice precision and inference steps are unchanged. The Windows source gate
passed 2,155 tests plus 254 subtests before release preparation; hardware cases
are mocked policy tests, not real 16 GiB/GTX 1070 pipeline benchmarks.

Public acceptance requires clean committed source, strict legal/resource/notices
checks, frozen startup and installer acceptance, full/delta health and rollback
tests from 0.1.6, 0.1.7 and 0.1.8, and public asset download/hash verification.
The final commit and evidence are bound by BUILD-INFO and release logs. Existing
application-source, OmniVoice-owner-asset and Qt clearances retain their hashes;
this review does not grant additional rights or remove license restrictions.
No older public release or immutable asset is overwritten by this publication.

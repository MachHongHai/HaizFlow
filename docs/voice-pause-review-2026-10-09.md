# Voice generation pause review — 2026-10-09

## Evidence and scope

The `mm` project used Manual mode, OmniVoice GPU, single-speaker synthesis,
with 294 sentences. Its log shows inference proceeding to all 294 sentences
and completion; it contains no recorded pause request for that voice run.
This alone does not prove which UI interaction prevented the pause.

Source inspection identified two weaknesses in the actual request path:

- The Manual inspector called `cancelManualTool` → `stopVideo` → `stop_video`,
  which opened a synchronous confirmation before setting cancellation (a
  nested QML event loop in the desktop app, Qt dialog as a fallback).
  An explicit Manual Pause now sends the request directly. Auto/Batch retain
  their existing confirmation behavior.
- Resident OmniVoice was registered only under its warm-runtime identifier,
  not the active video's cancellation identifier. Its cancellation polling
  also depended on progress/encoding callbacks returning, and its operation
  lock used an uninterruptible wait.

## Changes

- Bind the resident subprocess to the active request's cancellation owner for
  the duration of synthesis; detach it after that request. Its idle warm
  lifetime remains separately owned, so ordinary video cleanup cannot kill an
  idle worker reused by another request.
- Poll cancellation while waiting for the resident operation lock. A cancelled
  waiter does not launch or terminate the worker owned by another request.
- Check cancellation before one-shot launch and after worker return. Preserve
  an explicit cancellation identifier across isolated-worker fallback. A pause
  is never interpreted as a transport failure requiring fresh synthesis.
- Keep the existing Manual partial-clip publication and resume mechanism.
  No model settings, resource-pack protocol, project files, or cache formats
  are changed.

## Verification

`tests/test_voice_pause_responsiveness.py` adds six cases: direct Manual pause,
interruptible lock wait, active process termination during a blocked progress
callback on CPU and CUDA paths, cancelled one-shot startup, and preventing a
new synthesis after a paused worker exit. Process tests use a real sleeping
Python child, not an AI model. They retain a completed checkpoint and verify
pause/resume flags. Existing Manual artifact tests separately verify partial
MP3 publication and reuse of cached clips.

The focused related suites passed 155 tests and 16 subtests; the final six
new pause cases also passed independently. The full `scripts/test.ps1` gate
passed: Python compilation, correctness lint, 1,922 tests and 251 subtests
(one skipped), and Qt QML lint. Five warnings include existing Qt deprecations
and a local TorchCodec DLL loading warning; this is not model certification.

An unrelated native-folder-picker test failed in the first full run because
it assumed English copy and exact Windows separator spelling despite earlier
tests initializing Vietnamese UI state. Its assertions now compare localized
copy and canonical filesystem identity. Application dialog code is unchanged.

Actual model inference on the user's long video has not been rerun. Completed
clip publication/cleanup can still take time after inference has been stopped;
Resume remains disabled until the queue owner finishes that cleanup. Restart
the source desktop app to load the updated Python code. No build, commit,
push, or release was performed for this fix.

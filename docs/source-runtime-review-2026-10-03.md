# Source and development-runtime review — 2026-10-03

## Scope and safety

This review covers the current uncommitted changes. No commit, push, installer
build, executable build, user-media overwrite or deletion was performed.
Existing project caches remain available for inspection.

## Generality of implementation and tests

- Product source and committed tests contain no project-specific `hnk3`,
  `hnk4`, `hnk5`, `testnhe` or `testtiengviet` branches.
- Local video diagnostics remain under Git-ignored `build/`; they are not
  production modules or fixtures required by CI. Do not force-add that folder.
- `scripts/check-voice-quality.py` accepts any local transcript, voice folder,
  Whisper model and segment indices. It does not modify projects or render
  replacement audio. ASR output is diagnostic evidence, not a quality verdict.
- New speaker/runtime/storage regressions use synthetic data, mocks and
  temporary directories. Existing Windows path literals in controller tests
  represent mocked values, not paths used to read the owner's projects.
- Test-runtime setup now uses the checkout's ignored build directory instead
  of the Windows user's default temporary directory.

## Processing changes

- A fresh completed Auto rerun resets its elapsed clock without deleting valid
  checkpoints. Pause/resume retains elapsed time.
- Recognition tasks prefer the same RPC worker used for warm-up. Model/device
  changes are checked; unrelated language/voice settings do not reload Whisper.
- Warm ownership is revalidated after stage handoff, without dropping resource
  pack ownership protection. OmniVoice CPU aliases and language switches share
  the same model-device owner.
- OmniVoice prompt caches are bounded; inference step counts and sequential
  GPU execution remain unchanged. Cold imports and model loads still take time;
  this review does not claim a measured synthesis speedup or OOM immunity.
- Multiple-speaker mode now computes a source-bound CPU identity map and uses
  stable target-language library voices instead of cloning each source sentence.
  This avoids feeding English dialogue into Vietnamese synthesis. The map is
  approximate, especially for short, overlapping or stylized voices; it is not
  guaranteed diarization or preservation of the original speaker's timbre.
- Explicit authorized voice cloning remains a separate option. The UI places
  both special choices above preset categories; a missing clone sample opens
  the recorder/import workflow rather than silently selecting a normal voice.
- The optional WeSpeaker checkpoint is pinned to its publisher's revision and
  SHA-256. Its independent license is recorded in `licenses/WESPEAKER-NOTICE.md`.
  The packaged ONNX engine needs the new operation at the next release build;
  no resource-engine build was performed in this review.

## Development storage containment

The configured local home is on D:. App models, engine packs, package downloads,
HF/Torch/pip/uv caches and temporary files resolve beneath that home. The new
speaker model uses the same resource manager and download destination.

Python `tempfile` can retain an earlier system-directory choice independently
of TMP/TEMP. Configuration now updates that cached choice; speaker analysis and
manual audio-preview work also pass the selected temporary directory explicitly.

`scripts/configure-dev-storage.py` creates an ignored startup hook and pip
configuration **only inside this checkout's `.venv`**. The hook sets cache/temp
environment variables before third-party imports; it does not import HaizFlow,
Qt or ML runtimes at interpreter startup. Isolated smoke-test environments opt
out. Re-run the script after changing the development storage location.

Use `scripts/dev-env.ps1 -Tool uv ...` for standalone uv commands. A globally
installed uv invoked elsewhere is outside this checkout's environment; global
Windows/user settings have not been changed. Native file pickers retain a
read-only reference to the original Windows profile.

Existing C: caches are not proof of current model downloads: the inspected pip
cache (~402 MiB) and uv cache (~4012 MiB) were last modified on September 30.
Windows CrashDumps contained ~5411 MiB of Python dumps, including a ~607 MiB
dump from October 3. An Application event identifies Qt6Gui as the faulting
module. These shared/OS-generated files were not deleted or moved. Redirecting
Windows dumps for `python.exe` would affect other Python applications and needs
separate approval. Windows paging, crash reporting and other applications may
still change C: usage; application cache containment cannot prevent that.

## Verification and remaining limits

Before the storage fix: 1100 Python tests and 121 subtests passed; 76 Qt Quick
tests passed. Ruff F/E9, targeted qmllint, translation compilation, legal-state
consistency and whitespace checks passed. The legal check is not release clearance.

After the storage fix: 1101 Python tests and 129 subtests passed, with one
cross-volume integration test skipped because the selected test temporary
directory and workspace are on the same drive. Ruff F/E9 and whitespace checks
passed again. New child-process regressions verify containment after an earlier
`tempfile` selection and after conflicting model/cache environment overrides.
Fresh `.venv` Python and pip, plus uv through the development wrapper, resolve
their temporary/cache destinations to D:. Restart an already-running development
app to adopt the updated configuration.

The read-only speaker pass over a real 62-segment source completed in about
4.3 seconds on CPU. Full replacement-speech/audio-quality benchmarking was not
run with only about 3.2 GiB RAM free; pronunciation and residual hallucination
must be verified by listening to newly generated output. Existing bad audio
has not been overwritten. Multi-speaker voice cache signatures are versioned
so a subsequent processing run does not silently reuse that old synthesis.

The development environment still emits a TorchCodec/pyannote warning. The
recognition path supplies decoded waveforms to VAD, but optional file-decoder
compatibility remains a packaging check, not a reason to claim a flawless release.

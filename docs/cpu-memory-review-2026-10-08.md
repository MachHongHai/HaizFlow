# CPU memory review — 2026-10-08

Scope: source changes and verification only. No commit, push, installer build,
engine repack or release was performed. Baseline HEAD:
`7cb6d18581dfb1fe283e00fc9db20e611c7e9f41`.

## 1. Root cause and evidence

The Auto/Batch route was:

`ProjectCommandsController._resources_ready_for_videos`
→ `ResourcePackController._hardware_compatibility("engine-cpu-py313")`
→ `validate_processing_device("cpu")`
→ `HardwareCapabilities.cpu_supported`.

The last check used `total_ram_bytes >= 14 * 1024**3`. That field came from
`GlobalMemoryStatusEx.ullTotalPhys`: **OS-usable physical RAM**, not installed
RAM. The pack controller then replaced the reason with the generic Vietnamese
“Cấu hình CPU cần máy có ít nhất 16 GB RAM.” A 16 GiB installation with only
13.9 GiB usable failed this proxy threshold. The Manual resource check used the
same pack compatibility route. CPU Small/OmniVoice choices themselves were
valid; this was not a GPU-model selection error.

Other issues found: unknown RAM passed the old capacity check and defaulted to
a 16 GiB balanced CPU profile; usable RAM ≥14 GiB retained the balanced batch
and longer model lifetime. Auto released ASR before translation only for named
low-memory profiles. CPU Demucs could start up to four workers. OmniVoice's
imports-only retention checked free RAM but not commit or usable capacity;
Manual local TTS could leave a loaded model for five minutes. Warm-up skipped
memory limits when integer telemetry returned zero/unknown.

## 2. Files and logic changed

| Files (under `src/haizflow/`) | Change |
| --- | --- |
| `core/memory.py` (new) | Typed live snapshots, Windows APIs, stage admission, memory-pressure policy and numeric diagnostics |
| `core/hardware.py` | Installed-vs-usable eligibility, explicit unknown handling, GiB labels, constrained/live CPU profiles |
| `core/processing_errors.py` | Preserve admission numbers and remediation text in the UI |
| `desktop/resource_pack_controller.py`, `settings_controller.py`, `qml_controller.py` | Shared capacity validation, localized detailed reasons and installed/usable RAM display |
| `desktop/runtime_device_controller.py` | Diagnostic snapshot and no unsafe fallback to an ineligible CPU configuration |
| `desktop/processing_lifecycle_controller.py`, `smart_warmup_controller.py` | Foreground memory barrier, one resident model under pressure, fail-closed speculative budget and stale-residency revalidation |
| `pipeline/process_video.py`, `manual_tools.py` | CPU stage handoff, ASR admission and constrained Manual voice cleanup after publishing valid clips |
| `pipeline/audio_separation.py` | Retire unrelated CPU workers, preflight and one Demucs CPU worker |
| `pipeline/transcribe.py` | Live CPU batch/thread sizing; CPU INT8 unchanged |
| `pipeline/voice_reference.py` | Admission before CPU sample-recognition child process |
| `pipeline/omnivoice_tts.py` | Cold/resident admission matched to model/device, reset residency on release/exit, retire imports-only process under pressure, CPU threads |
| `services/external_engine.py` | Warm ownership tied to live process generation and context; clear on release, preemption, engine switch or close |
| `services/translation.py`, `hymt2_worker.py` | CPU Q4 admission, live idle timeout and constrained llama.cpp evaluation batch/threads |

New policy tests: `tests/test_cpu_memory_policy.py` (23 parameter-expanded
cases). Existing synthetic-runtime fixtures were updated in
`test_cpu_runtime.py`, `test_mixed_language_pipeline.py`,
`test_omnivoice_batching.py`, and `test_voice_reference_device.py` to avoid
depending on the developer machine's changing free RAM.

User hardware guidance: `docs/install.md`, `docs/install.vi.md`.
Detailed thresholds/API semantics: `docs/cpu-memory-policy.md`.

## 3. RAM optimizations and unchanged contracts

Installed capacity remains 16 GiB minimum. Usable capacity selects workload;
it no longer stands in for installed capacity. A separate 8 GiB usable floor
rejects severely restricted 16 GiB installations. Free physical RAM and commit
are sampled immediately before CPU inference, after stage handoff where
applicable. No model checkpoint, voice precision, inference steps, translation
context or Demucs quality settings were changed.

On <24 GiB usable CPU systems, Whisper defaults to batch 2/up to 4 threads;
live pressure can lower it to batch 1/up to 2 threads. Q4 keeps 4096 context
and single-prompt inference, with llama.cpp evaluation batch 128. OmniVoice
remains CPU FP32 and synthesis batch 1. Demucs uses one worker. CPU recognition
is released before translation, HY-MT2 before voice; constrained Manual voice
also releases its local runtime after publishing valid/partial clips.
Speculative voice/translation/separation warm-up is disabled on constrained
CPU systems; unknown counters cannot authorize warming.

The installed pinned OmniVoice tensor headers were read without loading model
weights. Model tensors account for approximately 2.28 GiB and codec tensors
0.75 GiB at FP32. The 6 GiB cold-load commit reserve includes approximately
3 GiB extra for imports/load/synthesis buffers. This is a header inventory and
an admission estimate, **not measured inference peak memory**.

With mocked installed16/usable13.9/free4.34/commit6.15 GiB, capacity validation
and the current CPU stage-admission reserves pass. Lower live budgets are
rejected before dispatch with numeric guidance. Passing admission is not a
claim that every video will fit that machine's memory.

Serial Auto/Batch queue, protocol version 1, pack identifiers, dependency
requirements, checkpoint signatures, pause/resume and atomic artifact
publication remain unchanged. Core admission/process handoff protects existing
engine packs. Worker-side batch/thread changes require future engine repacking;
old packs keep their existing inference configurations.

## 4. Executed verification

Latest source verification (2026-10-09),
`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test.ps1`:

- Python compilation: passed.
- Python correctness lint: passed.
- **1,902 tests passed; 251 subtests passed; 1 skipped; 4 warnings.**
- QML lint: no diagnostics; script exit 0.

The full suite covers resource install/pause/cancel, queue serialization,
checkpoints/resume, worker ownership, Manual workflow and GPU recovery.
New memory tests use deterministic mocked Windows counters and fake clients;
they are not full real-model integration tests.

The final suite also includes long-preview regressions: a synthetic 30-minute
Unicode-path H.264 source, persistent PCM/waveform cache reuse, caption indexing,
cancelled/stale deliveries, timing-only voice preservation and bounded recovery
with a mocked older OmniVoice engine. These are not a real 30-minute AI pipeline
benchmark. The existing GPU shutdown test now mocks memory admission so its fake
worker dispatch does not depend on RAM pressure from the rest of the suite.

Follow-up coverage includes direct source-audio playback without full PCM
decoding for unedited Manual clips, independent subtitle/audio cache identities,
same-path media replacement, Windows mapping-handle release while retaining
completed disk PCM caches, and owned-download hardlink/copy fallback. A real
local HTTP stream through yt-dlp and a real FFmpeg remux verify cancellation;
Douyin pagination, late URL-import results and project deletion ownership use
deterministic mocks. These do not measure live Douyin reliability or customer
machine import/reopen latency.

The 2026-10-09 follow-up found an unedited 27:54 HEVC/yuv420p source was
excluded by the H.264-only native preview gate. SDR HEVC now uses Qt's native
decoder as well. In one isolated local check with that source, preview
preparation including artifact bookkeeping took 0.399 seconds, and a separate
Qt decoding check delivered its first frame in 0.135 seconds. These are single
local observations, not end-to-end UI or hardware-matrix benchmarks. Cleanup
now releases Manual producer leases on cancellation/error, and project deletion
does not proceed until its owning processing runner has exited.

Additional checks:

- `verify-engine-dependency-locks.py`: passed (CPU/CUDA/vision locks).
- `verify-resource-pack-manifest.py --strict`: passed (3 engine packs ready).
- `verify-dependency-lock.py --no-installed-check`: passed (47 locked packages,
  source hashes and manifest consistent).
- `git diff --check`: passed.
- Real Windows API sampling returned separate installed/usable/free/commit
  counters on this development machine; this is not a clean-room benchmark.

`verify-dependency-lock.py` **with installed-environment checking failed**:
the existing `.venv` is not identical to the lock. Missing: coloredlogs15.0.1,
humanfriendly10.0, pyreadline3.5.6. Different: greenlet3.5.3 vs3.5.6,
onnxruntime1.27.0 vs1.23.2, protobuf7.35.1 vs7.36.2. No environment packages or
lockfiles were changed. The suite also emitted an existing libtorchcodec
decoder warning and Qt deprecation warnings. Environment repair/verification
is required before treating a future build environment as release-ready.

## 5. Remaining risks on 16 GB CPU systems

OmniVoice CPU, multiple-speaker analysis and long audio still need substantial
RAM/commit and can be slow. A small page file and other apps can exhaust commit
despite adequate installed RAM. Preflight is a momentary snapshot: allocation
races, native DLL commit, fragmentation and model activation peaks may still
cause controlled worker failure. Paging can reduce responsiveness. “Keep
models” is budget-dependent, not a guarantee of permanent residency.

## 6. Not verified in this change

No complete real Whisper → HY-MT2 → OmniVoice → export benchmark was run on a
controlled Windows machine with 16 GiB installed /13–14 GiB usable RAM. Peak
working set/commit, long-video throughput, voice-quality comparison and a
Windows hardware matrix remain unmeasured. No installer or already-published
engine pack was rebuilt or replaced. Native failure handling and valid-result
retention are covered by tests; absence of all possible OOM/native crashes is
not guaranteed.

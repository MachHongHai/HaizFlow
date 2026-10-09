# CPU memory policy

## Telemetry and eligibility

`core/memory.py` reads bytes, never mixed decimal GB/binary GiB. Windows installed
capacity comes from `GetPhysicallyInstalledSystemMemory` (KiB × 1024); OS-usable
and immediately available physical RAM come from `GlobalMemoryStatusEx`.
`K32GetPerformanceInfo` supplies system commit limit/usage (pages × PageSize).
Admission uses the smaller of system headroom and the current process's
`ullAvailPageFile`. Virtual address-space counters are not commit counters.
Failed telemetry is `None`; a measured zero remaining budget means exhaustion.

Minimum eligibility remains 16 GiB installed DIMM capacity, not 14 GiB usable
RAM as a proxy. At least 8 GiB must remain OS-usable; this is a separate safety
floor for severely restricted systems, not support for 8 GiB installations.
When installed capacity cannot be read, known usable RAM ≥16 GiB proves the
minimum; smaller usable RAM cannot establish installed capacity and requires a
successful hardware probe. Settings and CPU/GPU pack compatibility share this
policy; Auto, Manual and Batch use those pack checks before queueing work.

References: [installed memory API](https://learn.microsoft.com/en-us/windows/win32/api/sysinfoapi/nf-sysinfoapi-getphysicallyinstalledsystemmemory),
[MEMORYSTATUSEX semantics](https://learn.microsoft.com/en-us/windows/win32/api/sysinfoapi/ns-sysinfoapi-memorystatusex),
[GetPerformanceInfo](https://learn.microsoft.com/en-us/windows/win32/api/psapi/nf-psapi-getperformanceinfo).

## CPU workload and lifetime

Usable RAM below 24 GiB selects batch 2 / up to 4 CPU threads, no startup ASR
warm-up and a 90-second HY-MT2 idle timeout. Under 7 GiB usable selects batch 1 /
up to 2 threads (not automatically eligible hardware). Unknown capacity never
selects the balanced profile. Live physical/commit pressure can reduce batches
to 1 and threads to 2 at inference boundaries. GPU precision/batches are not
changed by the CPU policy.

Whisper keeps CPU INT8 and one resident ASR model. HY-MT2 retains Q4,
4096-token context, inference batch 1, and lowers llama.cpp evaluation batch
to 128 on constrained CPU profiles. OmniVoice keeps the original checkpoint,
CPU FP32 and synthesis batch 1; existing bounded prompt caches remain intact.
Demucs uses one CPU worker without changing segment/shifts/overlap settings.

Auto and Manual release ASR/separation/OCR ownership before translation; voice
handoff also shuts down HY-MT2. Terminating the last engine owner releases
native-library commit, not just weight tensors. CPU Demucs retires unrelated
idle workers before loading. OmniVoice releases weights/prompts after Auto
voice completion; on <24 GiB usable RAM its imports-only process is retired as
well. Manual voice runs also release the local runtime on constrained memory,
including partial/cancelled runs after completed clips are published.
Cancellation, checkpoint signatures, artifact publication and the
protocol-v1 contract are unchanged. Admission and process handoff live in Core,
so already-distributed engine packs receive these protections without repacking.
Live batching/thread adjustments inside workers require the updated worker
source in future packs; old packs keep their existing inference settings.

## Stage admission and warm-up

Conservative cold-load reserves (GiB) are:

| Stage | Available physical RAM | Additional commit |
| --- | ---: | ---: |
| Whisper Small CPU | 1 | 3 |
| HY-MT2 Q4 | 1 | 3 |
| Demucs CPU | 1.5 | 4 |
| OmniVoice CPU FP32 | 2 | 6 |

These are admission reserves, **not benchmarked peak-RSS guarantees**. The
OmniVoice reserve is based on the installed pinned checkpoint's tensor headers:
~2.28 GiB model + ~0.75 GiB codec in FP32, plus ~3 GiB for SDK/loading/buffers.
This header inventory is not an inference benchmark and does not reduce voice
quality. Resident models require only a 0.5 GiB physical / 1 GiB commit working
reserve, and residency is matched to model/device/process generation. A
one-shot OmniVoice process cannot claim the persistent process's residency.
Preflight failure occurs before model dispatch and uses normal recoverable
pipeline errors; complete checkpoints/artifacts are not deleted.

Speculative warm-up reserves more free memory for UI/decoding; voice,
translation and separation predictions are disabled on constrained CPU
systems. Missing telemetry denies speculative warm-up; idle memory pressure
releases models even when a counter is unavailable. “Keep models” is a request
to reuse idle models while budgets allow, never an unlimited-memory guarantee.

Logs contain stage, resident/cold state and numeric memory budgets, not user
identity, cookies or API keys. Free RAM/commit are sampled live, not cached with
the static hardware profile.

## Verification limits

`tests/test_cpu_memory_policy.py` mocks native API results and inference clients;
it does not load Whisper, HY-MT2 or OmniVoice. Existing queue, checkpoint,
pause/resume, pack and GPU suites remain part of `scripts/test.ps1`.
API sampling on a development Windows machine is not a 16 GB pipeline
benchmark. Real peak working set, commit, paging latency and long-video
throughput still require a clean Windows machine/VM under controlled load.
Other processes can consume memory after preflight; native DLL allocation and
fragmentation can still fail. The UI reports those errors and preserves valid
results instead of promising that no OOM can ever happen.

# Subtitle OCR acceleration

## Confirmed issue

The vision-engine lock previously installed CPU-only `onnxruntime==1.23.2`.
`_ocr_engine()` also left RapidOCR's GPU flags disabled. Selecting GPU for
recognition/TTS or NVENC for export did not accelerate the OCR models.

## Implementation

- The isolated Windows vision-engine lock now contains only
  `onnxruntime-directml==1.24.4`, not overlapping ORT wheel distributions.
  Core and CPU/CUDA speech locks are unchanged. No Torch import or CUDA/cuDNN
  installation is required by this vision engine.
- `pipeline/ocr_runtime.py` chooses an available CUDA provider when present,
  otherwise DirectML on Windows, otherwise CPU. DirectML selects a
  high-performance hardware GPU rather than hard-coding display adapter 0.
- RapidOCR's pre-built-session hook provides detection/recognition sessions
  with sequential execution and memory-pattern optimisation disabled, as
  [required by DirectML](https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html).
  Sessions are checked for the effective provider, not merely GPU hardware presence.
- Inference is serialised; recognition batches are bounded at four. CPU
  session threads are capped at four (fewer on small CPUs) and idle spinning
  is disabled. GPU failure during initialisation or a frame triggers one
  CPU recovery; the failed frame is retried, and later frames stay on CPU.
  CPU failures still propagate, so failed scans never publish a completed cache.
- Per-video logs identify the actual provider and CPU fallback reason.
  GPU selection does not alter model files, geometry rules, sampling count,
  detector/cache versions or existing cached regions. Cache hits do not
  initialise OCR or allocate GPU sessions.
- CPU work remains for frame decoding, image preprocessing, polygons and
  region selection. FFmpeg blur/patch/subtitle filters also remain CPU filters;
  export encoding independently uses the existing hardware-encoder path.
  This patch does not claim the entire rendering graph is GPU-only.

## Native evidence (2026-11-01)

The opt-in `scripts/verify-subtitle-ocr-runtime.py` compared the same 36 frames
from the local `lol` source, writing evidence only under `build/ocr-gpu-validation`.
It did not modify project metadata, source media or project cache.

- Unprofiled warm inference: CPU **17.05 s**, DirectML **6.35 s** (about 2.7x
  faster for this sample; excluding frame extraction, model initialisation
  and warm-up; not a claim for every machine).
- A second, profiled run measured CPU 18.49 s / DirectML 7.75 s; its detector
  and recogniser traces recorded **20,572 DirectML node events** and 74 CPU
  node events, confirming actual GPU execution instead of provider registration alone.
- Both paths returned the same final region: x=20.97%, y=69.69%, width=78.47%,
  height=5.31%, confidence=0.978, 35 accepted frame observations.
- Unit tests cover missing GPU providers, driver/init failure, mid-frame GPU
  failure, single CPU retry, effective-provider validation, thread/session
  settings and packaging isolation. Existing OCR/cache tests remain applicable.

## Delivery

This is a source and vision-engine packaging change. The existing immutable
published vision pack still contains the old CPU-only runtime; changing Core
alone cannot update code frozen inside it. A release must rebuild the vision
engine with the new lock/source and pin its new immutable version, sizes and
hashes through the normal resource-pack finalisation workflow. Do not repoint
an old release URL or edit its hash without building the artifact. No such
build, publication or live manifest change is performed by this patch.

Binary/license provenance is recorded in
[`ONNX-DIRECTML-NOTICE.md`](../licenses/ONNX-DIRECTML-NOTICE.md).

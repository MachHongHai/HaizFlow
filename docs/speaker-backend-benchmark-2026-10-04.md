# Speaker identification: CPU / CUDA comparison

## Decision

Keep speaker identification on CPU, built into Core. It does not inherit the
device preference used by Whisper, translation and OmniVoice. Remove the CUDA
ONNX dependency from the GPU resource engine. This decision applies to the
current small WeSpeaker model and sequential, per-turn inference path.

## Method

- AMD Ryzen 7 7735H; NVIDIA GeForce RTX 4060 Laptop GPU; Windows.
- Identical pinned WeSpeaker VoxCeleb ResNet34 checkpoint and ONNX Runtime 1.23.2
  for both execution providers. CPU inference uses two threads.
- CUDA uses direct DLL preloading (without importing Torch), heuristic cuDNN
  convolution selection and a 512 MiB arena cap. Confirmed CUDA was active;
  no CPU fallback was accepted as a GPU result.
- Three fresh-process trials per real source recording; provider order alternates.
  Sessions are not reused. Times include checkpoint verification, runtime import,
  model/session initialization and inference. These are cold **process/session**
  measurements, not a flushed OS disk-cache test.
- Existing source audio and recognition segments are read only. Decoder and
  filterbank preparation happen before the timed model sections for both devices.
  No project cache, speaker map, render or settings are changed by the benchmark.
- The isolated GPU runtime and all temporary files live under `build` on D:.
  User API keys and remote services are not used.

## Real speech results (median seconds)

| Input | Voiced turns | Backend | Load | Inference | Total |
| --- | ---: | --- | ---: | ---: | ---: |
| discord | 19 | CPU | 0.168 | 0.579 | 0.748 |
| discord | 19 | CUDA | 1.700 | 0.861 | 2.561 |
| full | 203 | CPU | 0.174 | 7.387 | 7.561 |
| full | 203 | CUDA | 1.705 | 7.408 | 9.182 |

Total medians are calculated independently, not by adding column medians.
CPU is faster in every paired real-speech trial. Minimum corresponding embedding
cosine similarity is 0.99999928 (discord) and 0.99999744 (full); complete-link
cluster labels are identical in all six comparisons.

This establishes numerical/backend equivalence on these recordings, **not**
ground-truth speaker accuracy. Neither backend fixes incorrect segmentation or
speaker assignments by itself.

## Synthetic cross-check and scope

Synthetic harmonic/noise segments show that CUDA can win for a workload with many
long turns: 120 turns took 15.13 s on CPU and 10.23 s on CUDA. For 30 turns, CPU
took 2.13 s and CUDA 6.86 s. Synthetic results are not used as a substitute for
the real-media results or as evidence of speaker accuracy.

The CPU decision is not a claim that GPU is slower on every possible recording
or machine. Revisit it if the model, batching strategy or hardware changes.

## Reproduction

`scripts/benchmark-speaker-backends.py` accepts arbitrary media/segment inputs;
there are no project-specific branches in the script or application code.

```powershell
# Use an isolated ONNX Runtime GPU 1.23.2 environment on D:, not the app runtime.
$env:PYTHONPATH = 'D:/Du-an/HaizFlow/build/speaker-gpu-check;D:/Du-an/HaizFlow/src'
.venv/Scripts/python.exe scripts/benchmark-speaker-backends.py `
  --audio '<source-audio>' --segment-file '<source-segments.json>' `
  --segments 500 --trials 3
```

The segment file must contain a JSON list with start/end times in seconds. The
benchmark skips unvoiced and shorter-than-0.5-second turns, and caps each sample
at eight seconds, matching the production embedding path. The script reports
actual provider, load/inference times, embedding similarity and cluster agreement.

# Auto restart and OmniVoice performance review — 3 October 2026

## Evidence and scope

The latest Auto test's log (hnk3, 13:46 UTC) recorded a translation checkpoint
hit at the start of a new processing attempt. `process_for_export` incorrectly
set a resume hint for all attempts. Batch processing did the same.

The same log attributed 54.98 seconds to SDK imports and 5.72 seconds to model
weight loading. These are separate startup costs, not 55 seconds spent reading
weights. User project files were inspected, not rerun or manually cleared.

No installer build, commit, push, dependency upgrade, or model download is
part of this change. Diagnostic output and temporary files stay on drive D.

## Fresh processing versus resume

- Auto and Batch processing from the quality/output confirmation starts a new
  attempt. It removes the owning video's generated temporary directory and
  managed artifact cache, clears checkpoints and recovery hints, and resets
  the processing clock. Source video, imported assets, settings, export history
  and external exported files are preserved.
- Resume continues the saved attempt. Matching signatures and valid clips
  remain required; mismatched or missing output is never accepted as complete.
- Batch validates all members and resource/output requirements before clearing
  generated work. A runtime consumer pin or invalid owner rejects the request.
  This is not a cross-video filesystem transaction: a late disk I/O error can
  still interrupt preparation; no batch is enqueued after that failure.
- Partial voice reuse in Auto/Batch additionally requires a resume/recovery
  hint. Manual's intentional separate-tool workflow remains supported.
- Installed model files and bounded in-memory performance measurements are
  runtime resources, not project-result checkpoints; fresh processing does
  not redownload models or deliberately repeat SDK imports.
- A final verification exposed an intermittent Windows `WinError 5` while
  publishing the Demucs staging directory. Publication/backup restoration now
  use bounded sibling-only rename retries (six attempts, at most 1.55 seconds
  backoff), with cancellation checks during publication. Non-permission errors
  propagate immediately; restoration remains possible after cancellation.

## OmniVoice changes

1. A model-release control request unloads weights and voice prompts while
   retaining imported modules when at least 3 GiB of RAM remains. Otherwise the
   worker closes. Shutdown, cancellation, device changes and memory-pressure
   release still fully terminate workers.
   Imports-only workers are explicitly closed during shutdown, storage moves,
   device switches and memory-pressure cleanup even when no resident-model
   marker remains. Resource-pack removal also uses full worker shutdown.
2. The pinned Transformers 5.3 Higgs codec has an `lru_cache` on
   `_get_conv1d_layers(self, module)`. Cached keys retain the codec and its CUDA
   weights after dropping the outer model. Clear that specific cache before
   collection. Measurement dropped residual allocation from 776.9 MiB to
   8.1 MiB. A release response with more than 64 MiB still allocated is rejected
   and the process is terminated instead of retained across GPU handoff.
3. GPU synthesis supports real SDK batches of up to two adjacent, similar-length
   short utterances with the same voice/reference. Long or mismatched utterances
   stay single; timeline order is never sorted or rearranged.
4. Memory policy includes free driver VRAM and reclaimable allocator blocks,
   retaining a 1.5 GiB reserve plus 0.5 GiB per concurrent short utterance.
   A genuine allocation failure halves the batch; failure at one item uses the
   existing error/fallback path. Other inference failures are not disguised as
   batch allocation failures. This cannot guarantee that OOM is impossible.
5. Runtime trials use actual pending utterances, not additional generated audio.
   Bounded scalar profiles compare synthesis seconds per generated audio second
   by device, language, length bucket and inference steps. Preview and full
   quality never share a timing profile. Batch two is retained only when median
   throughput improves by at least 5%; otherwise the worker chooses one.
6. CPU retains batch one, avoiding extra padding/RAM without proven CPU gain.
   Weight loading runs with one thread for Windows loader safety, followed by
   up to eight inference threads. GPU retains 32 inference steps and CPU 16;
   no quality reduction or experimental quantization was introduced.
7. Encode all preset/authorized voice references inside `torch.inference_mode()`.
   SDK 0.2.1 decorates generation but not `create_voice_clone_prompt`; the latter
   otherwise builds unnecessary acoustic-codec gradient activations. In matched
   production-worker reference benchmarks, this reduced peak allocation from
   6867 MiB to 2424 MiB. Reference transcript/audio, model precision and codec
   quality are unchanged. Reference encoding measured 0.108 seconds before and
   0.050 seconds after in these already-warmed samples; this is not an end-to-end
   CPU or full-video speedup measurement.

## Measurements and limits

RTX 4060 Laptop, 8 GiB VRAM. A warmed, matched workload of the same four short
Vietnamese sentences repeated twice produced:

| Batch | Seconds / utterance | Peak allocated VRAM |
| --- | ---: | ---: |
| 1 | 2.600 | 2143 MiB |
| 2 | 2.623 | 2340 MiB |
| 4 | 2.853 | 2735 MiB |

Increasing batch is therefore not a demonstrated general speedup on this
machine. An earlier single cold sample suggested a 15% gain; the matched run
did not confirm it. This is why automatic measured selection, rather than a
fixed larger batch, is used.

Model reload after releasing weights retained SDK imports (0 seconds reimport)
and took about 4.5 seconds in an isolated benchmark with warmed OS file cache.
This is not a claim of the same timing in every full Auto run. Imported modules
expire with the existing idle policy and are discarded under low RAM.

Four production-worker WAVs were finite, nonempty, 24 kHz PCM16. Offline Whisper
decoded Vietnamese in all four with substantially matching text, but some word
and accent discrepancies. This narrow check does not establish perfect speech
quality or unchanged perceptual quality over an entire user video.

CPU benchmark was skipped because available RAM was below the diagnostic's
6 GiB safety threshold; no CPU throughput percentage is claimed.

## Verification

Generic tests cover fresh processing of completed/paused/failed attempts,
resume preservation, batch preflight and external-export preservation,
voice/reference/length grouping, ordered audio outputs, CUDA allocation
backoff, adaptive throughput selection, codec cache release, and parent-worker
RAM/VRAM release guards. No product/test logic targets a named user video.

Final full suite: **1118 passed, 1 skipped, 148 subtests passed**. One existing
TorchCodec/FFmpeg loader warning remains in the recognition test environment;
this change does not upgrade that dependency or treat the warning as resolved.
Ruff F/E9 and whitespace diff checks passed.

Standalone diagnostics: `scripts/benchmark-omnivoice.py` and
`scripts/check-voice-quality.py`. Raw reports/media are under ignored `build/`,
not checked-in assets. The post-inference-mode production benchmark generated
eight valid clips, selected batch one after its real-workload trials, retained
imports across weight release, and reported 8.1 MiB residual CUDA allocation.

The integration uses the installed checksum-pinned SDK implementation; its
batch API and quality parameters are documented by the upstream project:
https://github.com/k2-fsa/OmniVoice/blob/master/docs/generation-parameters.md

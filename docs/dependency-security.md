# Dependency and model security policy

[Documentation](README.md) · [Release readiness](release-readiness.md) · [Tiếng Việt](dependency-security.vi.md)

Last reviewed: **2026-09-08**
Next review: **before every release and no later than 2026-10-08**

This policy defines the trust boundary for Python packages, native tools, and model artifacts used by HaizFlow. A listed exception is temporary and does not waive future advisories.

## Mandatory audit

Every release candidate must run:

```powershell
.\scripts\audit-dependencies.ps1
```

The script audits the environment that will be packaged with a pinned `pip-audit`. A new advisory fails the gate unless it is identified, threat-modeled, mitigated, time-bounded, and recorded here. Production must match `pyproject.toml`, the SHA-256-locked `requirements-lock-py313-win64.txt`, and `dependency-lock-manifest.json`.

## Baseline controls

- The Windows lock fixes exact versions and SHA-256 hashes. Environment sync uses uv's `unsafe-first-match` only to reach the exact locked version across the dedicated PyTorch, llama.cpp, and PyPI indexes; it never uses unconstrained best-match resolution.
- Model repository, immutable revision, filename, expected size, and full SHA-256 are fixed in the bootstrap manifest.
- Downloads are staged and atomically promoted only after integrity verification.
- HY-MT2 uses `local_files_only=True`, `use_safetensors=True`, and `trust_remote_code=False`.
- Runtime loaders receive verified local paths and do not silently fall back to unpinned model downloads.
- Release artifacts must not accidentally contain model payloads.
- User-provided checkpoints are not accepted as trusted production models.

## Controlled exceptions

### Transformers 4.57.6

Temporarily accepted: [PYSEC-2025-217](https://osv.dev/vulnerability/PYSEC-2025-217), [PYSEC-2026-2288](https://osv.dev/vulnerability/PYSEC-2026-2288), [PYSEC-2026-2289](https://osv.dev/vulnerability/PYSEC-2026-2289), [PYSEC-2026-2290](https://osv.dev/vulnerability/PYSEC-2026-2290), and [CVE-2026-9856](https://github.com/advisories/GHSA-xrqw-3rrv-vx5w).

The affected paths load untrusted checkpoints/configuration, expose Trainer/conversion surfaces, or write caller-controlled `chat_template` keys through `save_pretrained()`. HaizFlow loads a fixed, checksum-verified HY-MT2 artifact, refuses remote code, requires safetensors, and never calls tokenizer or processor `save_pretrained()`. Transformers 5 is not substituted until its interpretation of the HY-MT2 RoPE configuration passes compatibility and translation-quality gates.

### NLTK 3.10.3

Temporarily accepted: [PYSEC-2026-3740 / CVE-2026-81726](https://github.com/advisories/GHSA-8mgp-746c-j5xp).

NLTK 3.10.3 fixes the earlier parser, corpus-reader, recursion, and denial-of-service advisories. The remaining finding concerns caller-controlled paths in model-artifact loading and persistence APIs. HaizFlow does not expose those APIs: its WhisperX alignment wrapper replaces the NLTK resource loader with an internal sentence splitter, performs no NLTK download, and accepts no user-selected NLTK model path. Remove this exception when a compatible patched NLTK release is available.

### DiskCache 5.6.3

Temporarily accepted: [PYSEC-2026-2447](https://osv.dev/vulnerability/PYSEC-2026-2447).

DiskCache is transitive through `llama-cpp-python`. HaizFlow neither uses DiskCache for model acquisition nor calls `Llama.from_pretrained`; the CPU path opens a fixed GGUF file verified by size and SHA-256. Remove this exception when upstream provides a compatible fixed dependency path.

### Lightning 2.6.5

Temporarily accepted: [PYSEC-2026-3624 / CVE-2026-58659](https://osv.dev/vulnerability/PYSEC-2026-3624).

`pyannote-audio` requires Lightning. Until a compatible fixed release is available, `haizflow.core.dependency_security` rejects checkpoint-requested `_instantiator` imports outside the official CLI paths in both Lightning namespaces. The guard is regression-tested and disables itself after a fixed upstream version is detected.

### Torch 2.8.0+cu128 family

Because `pip-audit` cannot directly map the CUDA local-version suffix, the release gate also audits canonical Torch, TorchAudio, and TorchVision versions. Temporarily accepted advisories are [PYSEC-2025-203](https://osv.dev/vulnerability/PYSEC-2025-203), [PYSEC-2025-204](https://osv.dev/vulnerability/PYSEC-2025-204), [PYSEC-2025-206](https://osv.dev/vulnerability/PYSEC-2025-206), [PYSEC-2026-139](https://osv.dev/vulnerability/PYSEC-2026-139), [PYSEC-2026-2286](https://osv.dev/vulnerability/PYSEC-2026-2286), [PYSEC-2025-194](https://osv.dev/vulnerability/PYSEC-2025-194), [CVE-2025-2999](https://osv.dev/vulnerability/CVE-2025-2999), and [CVE-2025-3001](https://osv.dev/vulnerability/CVE-2025-3001).

WhisperX 3.8.6 declares the Torch 2.8 compatibility family. HaizFlow does not accept user Torch checkpoints or expose PT2, JIT, Trainer, or the affected operator paths. HY-MT2 uses pinned safetensors; Whisper uses a pinned CTranslate2 model. Only five checksum-pinned torchaudio alignment assets (`en`, `fr`, `de`, `es`, `it`) are allowed. Other languages retain Whisper timing and use internal segmentation. VAD is commit-, size-, and checksum-pinned.

### Demucs checkpoint format

Demucs 4.0.1 loads an upstream model class through `torch.load`. HaizFlow fixes the `htdemucs` host, URL, size, and full SHA-256 and prevents arbitrary repository resolution. Only the isolated Demucs subprocess receives `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1`, after verification. The main process and other workers never receive that override.

## Network and data exposure

| Feature | Data crossing the local boundary |
| --- | --- |
| Model bootstrap | Requests for fixed model files and transport metadata |
| URL/channel import | Submitted public URL, configured platform cookies, provider response |
| Edge TTS | Subtitle text required for speech synthesis |
| Social publishing | Explicitly selected media, post content, provider credentials |
| Diagnostic export | Bounded redacted application/model logs; no project media or metadata |

WhisperX, HY-MT2, OmniVoice, Demucs, OCR, FFmpeg, and project storage remain local after verified assets are present.

## Review requirements

A package, model, download host, deserializer, native binary, or provider change requires compatibility evidence, license review, vulnerability audit output, immutable integrity metadata where applicable, failure/corruption/cancellation tests, and an updated threat model. An exception expires when its mitigation no longer matches the implementation or a compatible fixed release becomes available.

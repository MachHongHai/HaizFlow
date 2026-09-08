# Release readiness

[Documentation](README.md) · [Dependency security](dependency-security.md) · [Tiếng Việt](release-readiness.vi.md)

Last reviewed: **2026-09-08**

This is the authoritative checklist for a public Windows build. A source checkout passing unit tests is not, by itself, a releasable artifact.

## Status vocabulary

- **Complete:** implemented and covered by automated evidence.
- **Release blocker:** public distribution is prohibited until the acceptance condition is satisfied.
- **Production follow-up:** not required for an internal engineering build, but required before broad production use.

## Control register

| ID | Control | Status | Acceptance condition |
| --- | --- | --- | --- |
| 1 | Project identity and deletion | Complete | UUID identity, registered roots, legacy preservation, shared-root/path-traversal checks, and deletion tests. |
| 2 | License and third-party compliance | **Release blocker** | Apache source notices, all third-party texts, OmniVoice checkpoint review, FFmpeg/GPL corresponding-source obligations, and legal approval. |
| 3 | Clean reproducible artifact | **Release blocker until clean build** | Committed clean tree, complete gate, isolated frozen smoke, build metadata, and verified checksums. |
| 4 | Installer and signing | **Release blocker for public build** | Clean artifact, Windows acceptance matrix, real Authenticode certificate, signed executable/installer, signature verification. |
| 5 | Model integrity | Complete | Immutable revision, size, and SHA-256 for HY-MT2 CPU/GPU, Whisper, OmniVoice, OCR, Demucs, VAD, and alignment assets. |
| 6 | Single instance | Complete | Per-user local server, activation handoff, stale-server recovery, and smoke isolation. |
| 7 | Project index recovery | Complete | Interprocess lock, atomic write, backup, quarantine, manifest rebuild, and write blocking after unrecoverable corruption. |
| 8 | Schema migration | Complete for current schema | Sequential migration, backup, defaults, legacy roots, and future-schema rejection. Project/video schema versions must match current source at release time. |
| 9 | Dependency reproducibility | Complete | Hash-locked Windows/Python 3.13 set, CUDA variant, source/lock fingerprint, and environment verification. |
| 10 | Disk and cache policy | Complete for tooling | Artifact-derived preflight, first-run model allowance, safe headroom, resumable partials, and bounded Manual caches. |
| 11 | Offline/privacy claims | Complete | UI and documentation distinguish local processing from model download, Edge TTS, URL import, and social publishing. |
| 12 | Diagnostics | Complete | Rotating logs, build ID, Python/thread/Qt capture, redacted bounded diagnostic export excluding project media. |
| 13 | Shutdown and recovery | Complete | Confirmation, pause/cancel, bounded worker wait, child-process containment, and interrupted-video recovery. |
| 14 | Runtime containment | Complete | Frozen mutable data below the chosen local install root; source mode supports `HAIZFLOW_HOME`. |
| 15 | Source hygiene | **Release blocker until clean build** | No obsolete source/build output, documentation matches architecture, and `git status --porcelain` is empty. |
| 16 | Vulnerability audit | Complete with controlled exceptions | Audit gate passes with only the reviewed exceptions in [dependency-security.md](dependency-security.md). |
| 17 | Zernio publishing | Production follow-up | Real-account end-to-end validation for each platform, quotas, failure recovery, consent, and current third-party terms. |

## License gate

Primary references:

- [Qt for Python licensing](https://doc.qt.io/qtforpython-6/licenses.html)
- [FFmpeg legal checklist](https://ffmpeg.org/legal.html)
- [FFmpeg license](https://ffmpeg.org/doxygen/trunk/md_LICENSE.html)
- [HY-MT2 model card](https://huggingface.co/tencent/Hy-MT2-1.8B)
- [Whisper large-v3-turbo model card](https://huggingface.co/openai/whisper-large-v3-turbo)
- [OmniVoice source](https://github.com/k2-fsa/OmniVoice)
- [OmniVoice model](https://huggingface.co/k2-fsa/OmniVoice)
- [Edge TTS source](https://github.com/rany2/edge-tts)

Each artifact must contain:

```text
LICENSE.txt
NOTICE.txt
THIRD_PARTY_NOTICES.md
licenses/
BUILD-INFO.json
SHA256SUMS.txt
```

`scripts/generate-third-party-notices.py --strict` must pass. The HaizFlow source license does not override a model, font, codec, or dependency license. In particular, the OmniVoice SDK and checkpoint require separate analysis, and an upstream FFmpeg source archive alone does not prove that all corresponding-source obligations of statically linked GPL components are satisfied.

## Source verification gate

Run from a clean committed checkout:

```powershell
.\scripts\test.ps1
.\scripts\audit-dependencies.ps1
```

The test gate compiles Python, runs correctness lint, executes the unit/integration suite, and requires `qmllint` without diagnostics. Packaging changes also require runtime, dependency-lock, third-party notice, and model-manifest verification.

Do not record a permanent test count here. The authoritative count is the output of the release commit's gate.

## Frozen artifact gate

The only supported build entry point is:

```powershell
$env:HAIZFLOW_SIGN_CERT_PASSWORD = "<certificate-password>"
.\scripts\build-exe.ps1 -SignCertificatePath C:\secure\haizflow-signing.pfx
```

For an internal engineering artifact from a working tree that is still under review:

```powershell
.\scripts\build-exe.ps1 -AllowDirtyBuild -AllowUnsigned
```

`-AllowUnsigned` never produces a public-release candidate. `-AllowDirtyBuild` records the dirty provenance and makes the resulting artifact ineligible for the public installer gate.

The build must:

1. reject an unsuitable or dirty release source state;
2. run source, dependency, native-tool, and notice checks;
3. remove only the validated previous artifact target;
4. create a PyInstaller `onedir` distribution;
5. copy licenses and notices;
6. prove that model payloads are absent;
7. run frozen self-tests, FFmpeg/FFprobe checks, and isolated Qt/QML startup;
8. create `BUILD-INFO.json` and `SHA256SUMS.txt` only after smoke success;
9. verify every declared artifact file and checksum.

Models are first-run downloads and must not be folded into the executable distribution. `prepare-offline-models.ps1` is a development/runtime probe helper, not packaging input.

## Installer gate

Build an installer only from a verified frozen artifact:

```powershell
.\scripts\build-installer.ps1 -SignCertificatePath C:\secure\haizflow-signing.pfx
```

The installer must use an artifact-derived disk estimate, permit a writable local drive, reject network destinations, preserve mutable runtime data during ordinary upgrades, and delete runtime data only after a separate explicit uninstall choice. Silent uninstall retains runtime data.

Public distribution requires signing with a real certificate through `-SignCertificatePath` and `HAIZFLOW_SIGN_CERT_PASSWORD`, followed by signature verification. The installer build performs an isolated silent install, installed-layout smoke test, uninstall, runtime-retention check, and checksum verification. `-SkipFrozenSmokeTest` and `-SkipInstallerSmokeTest` are diagnostic-only and invalidate a release candidate.

An unsigned installer may be produced only from an otherwise installer-eligible artifact for local engineering verification:

```powershell
.\scripts\build-installer.ps1 -AllowUnsigned
```

Its filename contains `UNSIGNED`. The installer smoke test can also be run explicitly:

```powershell
.\scripts\test-installer.ps1 -InstallerPath .\dist\installer\HaizFlow-<version>-Setup.exe -RequireSignature
```

## Windows acceptance matrix

- Windows 10 version 1809 or later and Windows 11 x64 clean installations.
- CPU-only Intel and AMD systems with representative 8/16/32 GB memory.
- NVIDIA systems with 6 GB, 8 GB, and larger VRAM; unsupported BF16 and missing/older drivers.
- Offline first launch, slow network, interrupted model download, and Edge TTS outage.
- Supported public URL imports, extractor changes, cookies, rate limiting, and cancellation.
- Unicode Windows account, project path, file name, and Vietnamese IME input.
- Low disk, alternate local drive, removable drive behavior, sleep/hibernate, and interrupted GPU work.
- Repeated preview seek/source swap, audio shutdown, pause/resume/restart, and long batch queue.
- Upgrade from every supported persisted schema and a corrupted-index recovery case.
- Zernio test accounts for every advertised destination platform before production approval.

## Release decision

An internal engineering build may be produced for verification when its intended scope and unsigned status are explicit. Public release remains blocked until legal/license review, a clean reproducible artifact, source hygiene, Windows acceptance, and Authenticode requirements are satisfied. This checklist records engineering evidence and does not replace professional legal review.

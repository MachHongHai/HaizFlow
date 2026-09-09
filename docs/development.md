# HaizFlow development guide

[Documentation](README.md) · [Architecture](architecture.md) · [Tiếng Việt](development.vi.md)

This document defines the contributor workflow for the Windows desktop application. It complements the architecture specification; it does not replace subsystem-level tests or release gates.

## 1. Supported development environment

The reproducible source environment targets:

- Windows 10 version 1809 or later, or Windows 11 x64;
- CPython 3.13 x64;
- PowerShell;
- Git;
- an NVIDIA CUDA environment for GPU-path verification, when available.

Do not install production dependencies ad hoc into a global interpreter. The repository maintains a hash-locked Windows dependency set and validates the installed environment.

## 2. Clone and install

```powershell
git clone https://github.com/MachHongHai/HaizFlow.git
cd HaizFlow
powershell -ExecutionPolicy Bypass -File .\scripts\install-desktop-env.ps1
```

The script:

1. validates Python 3.13 x64 on Windows;
2. creates `.venv` when absent;
3. redirects package caches and temporary files below the configured runtime boundary;
4. synchronizes `requirements-lock-py313-win64.txt` with `uv` or hash-checked pip;
5. installs HaizFlow in editable mode;
6. verifies the dependency lock and runtime imports.

Use `-Recreate` only when a clean environment is required:

```powershell
.\scripts\install-desktop-env.ps1 -Recreate
```

This deletes only the repository-owned `.venv` after an absolute-path safety check.

## 3. Runtime containment

Copy `.env.example` to `.env` only when an override is needed. For a portable development data root:

```dotenv
HAIZFLOW_HOME=D:\HaizFlowData
```

When `HAIZFLOW_HOME` is set, models, application data, third-party caches, and temporary work are contained below that root. Avoid redirecting individual caches unless diagnosing a migration.

Never commit `.env`, credentials, downloaded models, project media, `runtime`, `build`, or `dist` artifacts.

## 4. Run the application

```powershell
.\.venv\Scripts\python.exe .\haizflow_desktop.py
```

The launcher configures cache/model/temp paths before importing Qt or Torch. Internal worker flags are process contracts and are not user-facing CLI commands.

For a bounded UI bootstrap test:

```powershell
.\.venv\Scripts\python.exe .\haizflow_desktop.py --ui-smoke-test
```

## 5. Repository structure

```text
src/haizflow/
  core/           runtime policy, hardware selection, logging, integrity
  desktop/        Qt bootstrap, facade, controllers, models, presenters
    qml/          shell, pages, workspaces, controls, dialogs
    assets/       branding and pre-rendered voice samples
    translations/ Qt translation catalogs
  pipeline/       deterministic media and model transforms
  schemas/        persisted and cross-layer contracts
  services/       use cases, storage, queues, cache, integrations
  utils/          stateless process and media helpers
  vendor/         audited compatibility code
tests/            unit, integration, QML creation, and regression tests
scripts/          environment, audit, verification, build, release tools
installer/        Inno Setup definition
licenses/         third-party notices and license texts
docs/             user, architecture, security, and release documentation
```

Dependency direction is presentation → controller → service/pipeline → schema/core. Services and pipelines must not import QML.

## 6. Change workflow

1. Establish the current behavior with a focused test or reproducible case.
2. Identify the owning layer; avoid fixing a service invariant in a QML delegate.
3. Add or update a regression test before broad refactoring.
4. Implement the smallest coherent change that preserves project data.
5. Run focused tests while iterating.
6. Run the full verification gate before review.
7. Update user or engineering documentation when behavior, data, network access, or release assumptions change.

Avoid mixing a UI redesign, persisted-schema migration, and media-algorithm rewrite in one unreviewable change.

## 7. Python conventions

- Use explicit types for persisted and cross-layer data.
- Keep long-running work off the Qt GUI thread.
- Marshal worker results to the owning QObject thread through signals or an established event queue.
- Every cancellable operation must check a cancellation primitive at bounded intervals.
- Publish files atomically from project-owned staging after validation.
- Preserve exception context internally; present bounded, actionable messages to users.
- Do not catch broad exceptions without either recovery, cleanup, or propagation.
- Do not introduce an implicit network fallback for a local model path.

`qml_controller.py` is a facade. New behavior should belong to a focused controller or service and expose a narrow property/signal/slot surface.

## 8. QML conventions

- Use design tokens and shared Studio controls; do not introduce local color systems or duplicate button implementations.
- QML owns presentation state, focus, direct manipulation, and transient UI behavior—not inference or filesystem mutation.
- Type properties whenever the type is known.
- Avoid assigning to a property that is expected to retain a binding.
- Treat delegates as reusable objects; do not depend on `Component.onCompleted` for per-row identity.
- Activate heavy pages through guarded `Loader` instances and release media resources when a workspace closes.
- Provide `Accessible.name`, a visible focus state, correct tab order, and Escape behavior for dialogs/popovers.
- Keep the Windows IME composition path intact; save only committed text and preserve Unicode without trimming user content.
- Translate user-visible strings with `qsTr()`; do not place new UI literals outside the catalogs.

Run `qmllint` through the repository test script rather than against a different system Qt version.

## 9. Persistence and migration

Project and video identifiers are immutable. Display names are not filesystem identity. A persisted-schema change requires:

- a version increment;
- deterministic migration from every supported prior version;
- backup before mutation;
- default and validation behavior;
- rejection of unknown future schemas;
- tests for valid, incomplete, corrupt, and interrupted migration states.

Never delete a path derived only from user-visible text. Resolve and validate project ownership before destructive filesystem operations.

## 10. Manual artifacts and cache

Manual artifacts are content-addressed by declared inputs and relevant configuration. A new artifact kind needs:

- a stable signature definition;
- explicit input/output metadata;
- a staging and atomic publication path;
- validation for existence, non-zero size, and checksum where applicable;
- invalidation rules limited to true descendants;
- cancellation behavior;
- LRU/pinning behavior;
- cache-hit, partial-output, and corruption tests.

A setting change may select an existing variant but must not delete all historical variants. Input and final user output are not disposable cache.

## 11. Model and provider integration

For local models, pin immutable repository/revision, filename, expected size, and full SHA-256. Runtime loaders receive an explicit verified local path and must not call an unpinned network loader.

For online providers:

- make network use explicit in UI and documentation;
- bound retries and timeouts;
- distinguish transient failure from authentication/access failure;
- support cancellation where the provider permits;
- store secrets through Windows Credential Manager;
- avoid logging credentials or private URLs.

Provider behavior and licensing are part of the integration contract, not implementation details.

## 12. Tests

Run the complete gate:

```powershell
.\scripts\test.ps1
```

It performs:

1. Python compilation;
2. Ruff correctness checks;
3. unit and integration test discovery;
4. `qmllint` across the QML source set.

Focused Python tests use `unittest` discovery:

```powershell
$env:PYTHONPATH=(Resolve-Path .\src).Path
.\.venv\Scripts\python.exe -m unittest discover -s test -p "test_video_download.py"
```

Behavior changes should test both success and failure. Concurrency tests must cover stale callbacks, cancellation, shutdown, and repeated operations. Media tests should use small deterministic fixtures or fakes unless real codec behavior is the subject.

## 13. Translation and documentation

English is canonical and appears first. Vietnamese documents use the matching `.vi.md` name. UI translation uses Qt `.ts/.qm` catalogs.

User documentation should state an action, expected result, and recovery path. Engineering documentation should state ownership, invariants, failure semantics, and evidence. Do not present a plan, test count, or development artifact as a permanent product capability.

## 14. Security checklist

Before review, ask:

- Does the change expand network access?
- Does it parse untrusted media, URLs, archives, JSON, or model files?
- Can a path escape the registered project/runtime boundary?
- Can a stale worker overwrite newer state?
- Can a partial output be mistaken for a valid cache hit?
- Are credentials or private paths exposed in logs?
- Does a new binary/model/library require a notice or different redistribution terms?

Dependency or model changes also require [dependency security](dependency-security.md) review.

## 15. Pull request checklist

- [ ] The change has one clear purpose.
- [ ] User-owned data and unrelated working-tree changes are preserved.
- [ ] New behavior has regression coverage.
- [ ] QML remains responsive and accessible.
- [ ] Persisted data remains backward-readable or has a tested migration.
- [ ] Network, privacy, license, and cache effects are documented.
- [ ] `scripts/test.ps1` passes.
- [ ] No generated models, media, caches, credentials, or build output are committed.

Open an issue at [MachHongHai/HaizFlow](https://github.com/MachHongHai/HaizFlow/issues) when an architectural decision needs discussion before implementation.

## 16. External engine packs

Core and inference engines have separate dependency boundaries. Do not add Torch, ONNX Runtime, WhisperX,
Transformers, Demucs, or model checkpoints to the Core lock or PyInstaller profile.

Dependencies imported by HaizFlow code in every engine belong in `requirements-engine-common.in`. Profile-only
inference dependencies remain in `requirements-engine-cpu.in`, `requirements-engine-cuda128.in`, or
`requirements-engine-vision.in`. The verifier requires both sets in every engine lock and rejects Qt desktop
packages from those locks.

Regenerate all reviewed engine locks after changing an engine input:

```powershell
.\scripts\lock-engine-dependencies.ps1 -Profile all
.\.venv\Scripts\python.exe .\scripts\verify-engine-dependency-locks.py
```

Build an unsigned internal engine only for local acceptance:

```powershell
.\scripts\build-resource-engine.ps1 -Profile cpu -Version 1 -AllowUnsigned
```

Valid profiles are `cpu`, `cuda128`, and `vision`. Each build uses an isolated virtual environment, validates
the exact hash lock, freezes only that profile, generates profile-specific third-party notices, and runs a smoke
test that imports the promised native modules. The smoke command is embedded in `engine.json`; Resource Manager
runs it again before atomically activating a downloaded pack.

Dependency resolution, PyInstaller work, and temporary files stay below `build/` on the repository drive. Do not
redirect these jobs to the system temporary directory; CPU and CUDA environments can consume many gigabytes.

A public pack must be Authenticode-signed and uploaded to an immutable HTTPS release URL. Pin the built archive
only after upload:

```powershell
$env:HAIZFLOW_SIGN_CERT_PASSWORD = "<certificate-password>"
.\scripts\build-resource-engine.ps1 `
  -Profile cuda128 `
  -Version 1 `
  -SignCertificatePath C:\secure\haizflow-signing.pfx `
  -ReleaseUrl https://github.com/MachHongHai/HaizFlow/releases/download/v1/engine-cuda128-py313-1.zip
.\.venv\Scripts\python.exe .\scripts\verify-resource-pack-manifest.py --strict
```

Never invent archive sizes or checksums. `finalize-resource-pack.py` reads the finished ZIP and writes the actual
compressed size, installed size, SHA-256, version, and URL to `runtime/resource-pack-manifest.json`. Public Core
builds fail while any engine entry is unpinned. Model assets remain separately pinned by repository revision,
filename, byte size, and SHA-256 in the model-integrity catalog.

## 17. Packaging verification

An unsigned build is an explicit engineering artifact, not a public release:

```powershell
.\scripts\build-exe.ps1 -AllowDirtyBuild -AllowUnsigned
```

A public build must start from a clean committed checkout and use Authenticode signing:

```powershell
$env:HAIZFLOW_SIGN_CERT_PASSWORD = "<certificate-password>"
.\scripts\build-exe.ps1 -SignCertificatePath C:\secure\haizflow-signing.pfx
.\scripts\build-installer.ps1 -SignCertificatePath C:\secure\haizflow-signing.pfx
```

The installer gate verifies the frozen artifact, calculates real disk requirements, builds the Inno Setup package, verifies its checksum and signature, then performs an isolated install/startup/uninstall smoke cycle. Skipping either frozen or installer smoke is diagnostic-only. See [release readiness](release-readiness.md) for the legal, clean-source, and Windows acceptance requirements.

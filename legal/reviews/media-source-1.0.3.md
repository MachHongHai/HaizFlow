# HaizFlow 1.0.3 — scoped technical packaging review

Reviewer: Codex. Date: 2026-10-20 (Asia/Saigon). This is a scoped technical
packaging review, not independent legal, ownership or patent certification.

The owner explicitly requested this patch release and updates from 1.0.1.
Also retain direct updating from the current stable 1.0.2. Previous releases
and immutable assets remain unchanged. Reviewed source baseline:
f40a7e350b3a1f413bdb329e1dc25d4bd7f3b7f5. Final BUILD-INFO binds the clean
release commit after actual resource archive pinning.

Changes since 1.0.2 are application-owned Windows metadata/cache recovery,
bounded background refresh, registry CPU fallback, explicit supported flat
engine app-root handling, a SciPy hidden-import hook and smoke-test/error
coverage. No dependency version, checkpoint, voice preview, artwork, font,
codec or media recipe changes. Locked wheel bytes remain unchanged; lock
provenance is refreshed only for the application version metadata.

Existing application-scope, owner-asset/OmniVoice noncommercial and Qt
replacement clearances keep their original limitations. The exact pinned
ThirdPartySources 1.0.0 archive continues to provide the unchanged FFmpeg
CLI/engine, Qt/PySide, compiler, recipe and library source closures at its
original public URL. No notice, restriction or blocker is waived. User media,
projects, cookies, credentials and diagnostic audio are not redistributed.

Rebuild CPU 16, CUDA 18 and vision 8 with the existing reviewed engine locks.
The shared app-root source is embedded in all three engines; CPU/CUDA also
explicitly collect and smoke-check the existing SciPy Pythran extension.
Only newly built archive bytes/sizes/hashes may be pinned; old published
archives must never be replaced. Engine protocol 1, runtime contract 7,
model/checkpoint formats and update protocol remain compatible.

Require strict legal/resource/dependency gates; clean Core/bootstrap and
engine packaging; real frozen CPU/CUDA/vision smoke and app-root checks;
installer acceptance; actual Full/Delta health, rollback and data-preservation
tests from 1.0.1 and 1.0.2; public asset/part/hash checks and original-updater
preparation over GitHub. Native import smoke on the build machine is not an
RTX 3050 or Ryzen 4750G hardware benchmark or an all-machine certification.
The user-specific SciPy failure remains unconfirmed without their log.

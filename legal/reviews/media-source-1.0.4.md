# HaizFlow 1.0.4 — scoped technical packaging review

Reviewer: Codex. Date: 2026-10-24 (Asia/Saigon). This is a scoped technical
packaging review, not independent legal, ownership or patent certification.

The owner directly requested building and publishing 1.0.4 with updates from
1.0.1. Preserve earlier releases and immutable assets; also provide direct
updates from 1.0.2 and 1.0.3. Reviewed application baseline is f9a4a7e plus
the Douyin media transport fix and release preparation in 2541f77. Final clean
release commit and actual packaged files are bound by BUILD-INFO and hashes.

Changes since 1.0.3 concern application-owned subtitle editing/voice identity,
preview cache identity, project deletion transactions, bounded TTS inactivity
watchdogs and short-audio checks, Douyin request-level transport selection,
and bounded parallel Core verification. No package version, checkpoint,
voice preview, font, artwork, codec, media build recipe or license is changed.
The dependency-lock provenance is refreshed only for the application version
bump; locked dependency archive hashes and versions remain unchanged.

Existing application-scope, owner-asset/OmniVoice noncommercial and Qt
replacement clearances retain all limitations. The pinned ThirdPartySources
1.0.0 archive continues to provide the unchanged FFmpeg CLI/engine, Qt/PySide,
compiler, recipes and library source closures at its original public URL.
Keep all required notices and source access. Do not redistribute user media,
projects, cookies, API keys or private diagnostic audio.

Rebuild CPU 17 and CUDA 19 so worker-side TTS fixes reach users; retain the
unchanged vision 8 archive. Pin only actual archive bytes, sizes and SHA-256
at new immutable 1.0.4 URLs. Engine protocol 1, runtime contract 7, model
formats and update protocol remain compatible. Rebuild bootstrap and Core
from the same final clean commit; old launchers are not silently replaced by
Core-only updates. Explain the Setup path for the launcher optimization.

Require strict legal/resource/dependency audits, complete source/QML tests,
real frozen CPU/CUDA smoke, packaged Douyin transport validation, installer
acceptance, actual frozen Full/Delta health/rollback/data-preservation tests
from 1.0.1 onward, and public release asset digest/download checks. These are
publication conditions, not assertions of completed tests at review time.
Local acceptance is not an all-machine benchmark or Windows certification.
The owner-selected unsigned distribution caveat and OmniVoice noncommercial
restriction remain visible; no gate, license restriction or blocker is waived.

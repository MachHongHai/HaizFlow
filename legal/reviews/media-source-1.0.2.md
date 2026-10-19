# HaizFlow 1.0.2 — scoped technical packaging review

Reviewer: Codex. Date: 2026-10-19 (Asia/Saigon). This is a scoped technical
packaging review, not independent legal, ownership or patent certification.

The owner explicitly requested push, build and publication of the next patch,
then specified direct updating from 1.0.0. Version 1.0.2 also retains direct
updating from 1.0.1. Previous releases and immutable assets remain unchanged.
Reviewed source baseline: bb27f93ae3ca87b4b577ff14d96b31535056ab36.
Final BUILD-INFO binds the clean release commit including version metadata.

Changes since 1.0.1 cover short atomic metadata staging names for Windows,
HY-MT2 worker handoff/memory admission and installed-Q4 fallback, explicit
social-post queues during import/upload, processing model-picker state and
Douyin Chromium lifecycle reporting. All are application-owned source changes.
No third-party dependency version, model checkpoint, preview/branding asset,
font, codec, or media build recipe is introduced. The editable project's
uv.lock version is aligned with pyproject; dependency package bytes are not
changed. User media, cookies, diagnostic audio and credentials are excluded.

Existing application-scope, owner-asset, OmniVoice noncommercial and Qt
replacement clearances retain their original scope and limitations. The exact
unchanged ThirdPartySources 1.0.0 archive remains checksum-pinned at its original
public URL and supplies the FFmpeg CLI/engine, Qt/PySide, compiler, recipe and
dependency source closures. No notices, restrictions or blockers are waived.

Reuse the immutable CPU 15/CUDA 17 archives from 1.0.1 and vision 7 from 0.1.10.
The fixes are in Core orchestration/UI; the speaker engine only returns the
identity map, while Core performs the repaired atomic cache publication.
HY-MT2 admission/child configuration likewise reside in Core. Engine RPC,
checkpoint/model formats and update protocol stay unchanged.

Require strict legal/resource/dependency checks, clean-source Core/bootstrap,
frozen startup, installer acceptance, actual Full/Delta health/rollback and
data-preservation tests from 1.0.0 and 1.0.1, and public asset/hash verification.
Automated simulations of low-memory 4/6 GiB GPUs are not a real RTX 3050 hardware
benchmark, and local Windows tests do not certify every machine/network.

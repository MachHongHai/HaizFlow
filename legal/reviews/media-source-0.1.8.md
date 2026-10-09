# Media and resource packaging — 0.1.8 technical review

Reviewer: Codex. Date: 2026-10-09 (Asia/Saigon). This is a scoped technical
packaging review, not independent legal or patent certification. The owner
explicitly authorized build/publication, source commit/push, and removal of
releases older than 0.1.5 after protecting the new release's resource delivery.

The previously reviewed FFmpeg CLI, Qt/PySide modules, CPU/CUDA PyAV backends,
model checkpoints, bundled preview voices, fonts, and license terms are
unchanged. No CloakBrowser binary or vendor license is added. Chromium remains
an optional unmodified upstream resource, not included in the installer.

Certifi 2026.6.17 is now a direct dependency and its CA data is explicitly
collected by PyInstaller. It was already present in the exact hashed Core lock
as a curl-cffi dependency; that lock's byte checksum is unchanged. The exact
installed certifi license is retained by the strict notices generator. The
yt-dlp FFmpeg command adaptation for cancellation is documented in the
repository inventory; no upstream license text is replaced.

The corresponding-source archive for 0.1.8 inventories the exact unchanged
CLI/engine source closures, compiler/CRT inputs, linked-library sources,
Qt/PySide sources, recipes and notices. It must be published alongside the
binaries and verified against runtime/third-party-sources-manifest.json.

CPU 10, CUDA 12 and vision 5 engines are rebuilt from the current owned application
code, using the exact unchanged reviewed dependency locks and media recipes.
This is necessary because the old frozen engines retain older hardware and
inference-worker code even when Core is updated. Runtime contract 6 and the
JSON protocol remain compatible; no checkpoint or third-party binary is
deliberately changed. Vision is rebuilt as well so the shared hardware and
engine entrypoint code does not remain stale. Removing v0.1.0 through v0.1.4 is authorized only
after those replacement public URLs and all
new-release assets are verified. Keep v0.1.5 through v0.1.7 and their sources.
Old installed applications referencing deleted resource URLs must upgrade
before downloading more engine packs. After updating, users install the new
CPU/CUDA engine version when requested; downloaded model files are reused.
No claim of continued old resource URLs is made.

Public acceptance requires the source gate, strict legal/resource/notices
checks, actual frozen installer and Core startup checks, full/delta upgrade
and rollback tests from 0.1.6 and 0.1.7, and download/hash verification through
the application update client. Windows Application Control, every TLS trust
configuration, all upstream social-platform access, and whole-pipeline
inference on all 16 GiB machines are not certified by these checks.

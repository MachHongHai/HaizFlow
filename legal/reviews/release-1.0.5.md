# HaizFlow 1.0.5 — scoped technical packaging review

Reviewer: Codex. Date: 2026-11-15 (Asia/Saigon). Technical provenance and packaging
review only; not independent legal certification or ownership verification.

The owner explicitly requested push, build and publication of the next release,
with direct updates from 1.0.2. Preserve earlier public assets. Final source,
Core and bootstrap identities must be bound to clean commits by BUILD-INFO.

The release includes application-owned API translation adapters and model policy,
MCP, manual/batch and preview/cache isolation fixes, and OCR/TTS worker changes.
Publish rebuilt CPU 18, CUDA 20 and vision 10 packs, not the old worker payloads.
Model formats, engine protocol and update protocol remain compatible. Engine
archives must be measured, hashed and pinned at immutable new URLs before Core
assembly. Do not claim all-machine GPU compatibility or complete model quality
from synthetic probes. Paid APIs require user-selected accounts and permissions.

## New packaged material since 1.0.4

- MCP 2.3.0 is an MIT dependency pinned in the Core lock. Preserve its installed
  license inventory and those of its transitive dependencies.
- Noto Sans SC/TC/JP/KR Black, Dela Gothic One and Pretendard ExtraBold are
  unmodified bundled font files. Preserve their copyright notices and full
  SIL OFL 1.1 texts (`NotoSansCJK-OFL.txt`, `DelaGothicOne-OFL.txt`,
  `Pretendard-OFL.txt`); do not assign the application's proprietary terms to
  those fonts. Manifest sizes and SHA-256 are checked by the font tests.
- Vision replaces CPU-only ORT with the official hash-pinned Windows x64
  `onnxruntime-directml` 1.24.4 wheel. Core and speech engines retain CPU ORT in
  separate environments. Preserve ONNX Runtime MIT and ThirdPartyNotices, plus
  the separate DirectML 1.15.4 binary license. Technical provenance, DLL hash,
  Windows-only integration scope and original binary terms are recorded in
  `licenses/ONNX-DIRECTML-NOTICE.md` and `DirectML-1.15.4-LICENSE.txt`.
- Twelve generated OmniVoice reference WAVs retain the same pinned model and
  its NonCommercial restriction. Their manifest bootstrap hashes were checked
  against the existing male/female preview MP3s: all twelve match an existing
  preview source. These are not imported user recordings or new human identity
  attestations. Keep original provenance and model-use restrictions; do not
  claim commercial rights to the checkpoint or generated voice identity.

Existing application/contributor, owner-asset, model and Qt clearance limitations
remain in force. FFmpeg/Qt binaries and media recipe are unchanged; retain the
existing complete ThirdPartySources 1.0.0 archive at its pinned public URL and
all original licenses/replacement documentation. No private projects, API keys,
cookies, models or diagnostic audio may enter the immutable Core.

## Conditions before publication

Require complete source/QML and dependency audits, strict catalog/legal checks,
actual frozen engine smoke, Core/installer acceptance, and real frozen Full/Delta
reconstruction, health, rollback and data-preservation checks from 1.0.2 onward.
Confirm GitHub asset sizes and SHA-256 and verify public downloads after publishing.
The owner-selected unsigned-build caveat remains visible. No licensing blocker
or release gate is waived by this record.

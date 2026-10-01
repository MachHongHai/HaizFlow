# Licensing review and proposed transition

Review date: 2026-10-01. **Engineering inventory, not legal approval.** Current
source license: Apache-2.0. No custom license or application terms are active.
No installer was built and no release was published in this change.

## Quyết định cần chủ dự án xác nhận

1. Duyệt [toàn văn giấy phép source-available](../legal/LICENSE-SOURCE-AVAILABLE-DRAFT.md)
   và [điều khoản sử dụng ứng dụng](../legal/APPLICATION-TERMS-DRAFT.md).
2. Xác nhận phạm vi mã/tài liệu/branding thực sự sở hữu, quyền của contributors,
   quyền sử dụng mẫu giọng và ảnh/logo. Không tự nhận quyền của bên thứ ba.
3. Chọn phiên bản bắt đầu áp dụng; quyền Apache đã cấp không bị thu hồi.
4. Duyệt [cơ chế đóng góp tự nguyện](../legal/CONTRIBUTOR-PERMISSION-DRAFT.md)
   và [chính sách nhận diện bản chính thức](../legal/BRAND-POLICY-DRAFT.md).
5. Giải quyết các blocker dưới đây, rồi mới kích hoạt và phát hành. Các văn bản
   EN là bản đề xuất đầy đủ; phần VI này là giải thích, không phải bản dịch
   pháp lý có hiệu lực. Không có tuyên bố đã được luật sư xác nhận.

Mô hình dự kiến cho phép sử dụng miễn phí, xem/clone/build/chỉnh sửa nội bộ,
tạo video thương mại; không mặc định cấp quyền phân phối phần mềm, bán bộ cài,
rebrand, sublicense hoặc phát hành build sửa đổi của phần mã được hạn chế.
Không đòi quyền sở hữu video của người dùng. Giấy phép thành phần độc lập vẫn
điều chỉnh model, codec, font, thư viện và nội dung người dùng đưa vào.

## Ownership evidence and limits

User-provided creator identity, the official repository and existing installer
publisher metadata name Mach Hong Hai. Local history contains 78 commits under
`Hai Huong <machhonghaipr@gmail.com>`, matching the contact email, but commit
identity is not proof of exclusive ownership, employer authority, or rights in
incorporated assets. No history was rewritten. The contributor notice is kept.
No blanket copyright header was applied. NOTICE scopes Mach Hong Hai's claim
to work he owns and preserves independent attribution, including Evil0ctal's
adapted Douyin helper, Microsoft icons and Bangers font.

Before activation create a reviewed, versioned file/commit rights inventory;
obtain explicit contributor permissions where necessary. A CLA draft is not
an accepted CLA. Previously distributed Apache copies retain their permissions;
the new license can cover only appropriately identified future work for which
the licensor has authority. Merely changing a README does not establish that
authority or erase existing redistribution rights.

## LICENSE COMPLIANCE BLOCKER

| Gate | Local evidence | Required before public release |
| --- | --- | --- |
| Owned-code / contributors | Current Apache LICENSE, contributor notice and Git authors | Reviewed ownership scope and sufficient permission for future restricted licensing; no retroactive withdrawal. |
| OmniVoice commercial workflow and samples | Pinned model revision `c5fdb5ccb189668d56333f77ba2629f4cd7535f4`, local notice and upstream card declare NonCommercial; SDK is Apache | Clarify commercial permission with rights holders or approve an alternative in a separate technical change; confirm generated preview/reference voice provenance. Do not advertise unrestricted monetization using this model. |
| FFmpeg corresponding source | Actual buildconf has `--enable-gpl --enable-version3 --enable-static`, x264/x265; source bundle covers FFmpeg only | Complete exact source/build/license closure for covered static dependencies through the distribution channel. Review whether subprocess integration qualifies as an aggregate; no unsupported assertion that all app code must be GPL or that integration is cleared. |
| Qt/PySide6 LGPL path | PySide6 6.11.1 installed metadata declares LGPL/GPL options; onedir DLL packaging | Audit actual modules for GPL-only code; provide exact required source/notices; demonstrate library replacement/relinking and required debugging/reverse-engineering freedoms. No evidence of a commercial Qt license. |

The full [component inventory](../THIRD_PARTY_NOTICES.md) distinguishes Core,
engines, downloaded models, fonts/icons and PyInstaller. SDK licenses do not
establish checkpoint rights. VAD, alignment, OCR and Demucs checkpoint terms
still require per-pack verification. A successful notice generator checks text
evidence, not license compatibility or the completeness of corresponding source.
No library, model, security gate or pipeline was removed to bypass compliance.

## Build synchronization and activation

`legal/license-state.json` records Apache as active, the custom proposal as
draft, no owner approval/effective release and unresolved public-release gates.
`scripts/verify-legal-state.py` checks the source text, draft markers, metadata,
notice links and packaged active license. `--public-release` fails closed until
all reviewed clearance evidence is recorded. Internal source/test work remains
available. Existing signing, updater, engine isolation and model delivery gates
are unchanged; no delta updater is introduced.

Core packages LICENSE.txt (Apache), NOTICE.txt, generated third-party inventory,
component license texts and the `legal/` review bundle. Engines carry the same
HaizFlow state and their own generated dependency inventory. Inno Setup still
shows LICENSE.txt, never unapproved Application Terms. Installer packaging
verifies matching legal metadata for the selected artifact. No update rewrites
terms retroactively or silently accepts a new agreement.

Activation is deliberately a reviewed change, not a toggle: approve exact text
hashes, effective version, owned-code inventory and contributor permissions;
resolve component blockers; install the approved source/application documents;
update active metadata, badge, About and installer LicenseFile together; extend
the verifier for the approved state and run release gates again. Do not just
empty the blocker list or mark a draft approved. Record clearance evidence and
approval identity/date against the actual release and dependency revisions.

## Primary references

- [Apache-2.0 sections 2, 4 and 5](https://www.apache.org/licenses/LICENSE-2.0): existing grant, attribution and contributions.
- [GitHub Terms, section D](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service#d-user-generated-content): public viewing/forking and contribution terms.
- [OSI definition](https://opensource.org/osd): access alone is not open source; unrestricted redistribution/derivatives are required.
- [Qt LGPL obligations](https://www.qt.io/development/open-source-lgpl-obligations) and [Qt for Python notices](https://doc.qt.io/qtforpython-6/licenses.html).
- [FFmpeg legal guidance](https://ffmpeg.org/legal.html): configured binaries and corresponding source matter.
- [Pinned OmniVoice model card](https://huggingface.co/k2-fsa/OmniVoice/blob/c5fdb5ccb189668d56333f77ba2629f4cd7535f4/README.md): model and SDK license distinction.
- [PyInstaller exception](https://pyinstaller.org/en/stable/license.html): bundling exception does not override other dependencies.

Legal enforcement, mandatory local rights, tax/trademark issues and commercial
permissions need owner/qualified counsel review. No jurisdiction, trademark
registration or universal enforceability is presumed.

## Change inventory

| Files | Change |
| --- | --- |
| `LICENSE` | Unchanged Apache-2.0; no unapproved restriction made active. |
| `NOTICE`, `pyproject.toml` | Scoped creator/copyright, contributor preservation, active license and official links. |
| `README.md`, `README.vi.md`, both `CONTRIBUTING` files | Same current/proposed rights, output and model caveats, opt-in contributor permission. Apache badge retained because Apache is still active. |
| `legal/*-DRAFT.md` | Full source license, application terms, contribution permission and brand proposal, all not in force. |
| `legal/license-state.json`, `legal/rights-inventory.json` | Explicit pending approval/effective release, known blockers, candidate scope and excluded/unverified material. |
| `THIRD_PARTY_NOTICES.md` | Repository delivery inventory; does not replace generated per-artifact notices. |
| `AboutDialog.qml`, EN `.ts`/`.qm` | Version, creator, scoped copyright, license/notices links and a scrollable body without footer overlap; existing design retained. |
| Three build scripts, `installer/HaizFlow.iss` | Source/artifact legal checks, draft bundle packaging, stale app-owned legal bundle cleanup; installer still displays approved Apache text. Signing and checksum gates remain. |
| `scripts/verify-legal-state.py`, `tests/test_legal_state.py` | Consistency, mismatched packaged documents, draft activation, malformed state and unresolved release gate regressions. |
| `dependency-lock-manifest.json` | Input metadata hash refreshed after pyproject author/license metadata edits; dependency versions and hashed lock unchanged. |
| Documentation indexes and release-readiness EN/VI | Links and explicit legal blockers. Security policies need no license edits; their reporting/security rules are unchanged. |

Existing component notices and source headers were preserved. The notice
generator was not replaced. No installer, engine or model was rebuilt in this
change, so source consistency does not certify a fresh packaged release.

## Verification in this change

- Full pytest run: 1002 passed, 96 subtests passed; one existing TorchCodec native
  decoder warning in the development environment. The tested path supplies
  preloaded waveforms; this does not certify all optional decoder paths.
- Qt Quick suite: 51 passed. Full qmllint and Ruff correctness lint passed;
  modified PowerShell scripts parsed successfully. English catalog compiled.
- Legal consistency and source/artifact mismatch regressions passed. Public
  release check intentionally refused unresolved clearances and missing approval.
- Strict Core third-party generator completed for 36 installed distributions;
  dependency lock verifier accepted unchanged 35-package lock and refreshed
  metadata input hash. No dependencies were installed, removed or upgraded.
- About rendered and was visually checked offscreen at 1120×900 and 1120×720;
  the body scrolls separately from its footer. Native Windows Large text,
  keyboard/screen-reader audit and frozen installer rendering were not exercised.
- No full build, installer run, updater end-to-end upgrade or separate engine
  inventory rebuild was performed. Corresponding-source closure, model
  commercial permissions, artwork/voice provenance and legal enforceability
  remain unresolved. These results are not a production-ready declaration.

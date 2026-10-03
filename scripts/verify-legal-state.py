"""Read-only legal consistency gate; it cannot approve or activate a license."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRAFTS = (
    "LICENSE-SOURCE-AVAILABLE-DRAFT.md", "APPLICATION-TERMS-DRAFT.md",
    "CONTRIBUTOR-PERMISSION-DRAFT.md", "BRAND-POLICY-DRAFT.md",
)
REQUIRED_CLEARANCES = frozenset({
    "owned-code-and-contributor-scope",
    "omnivoice-noncommercial-checkpoint-and-preview-assets",
    "ffmpeg-complete-corresponding-source",
    "qt-lgpl-module-and-relinking-evidence",
})


def text_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def verify(root: Path = ROOT, *, artifact: Path | None = None, public_release: bool = False) -> list[str]:
    errors: list[str] = []
    try:
        state = json.loads((root / "legal/license-state.json").read_text(encoding="utf-8"))
        project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        if state.get("schema_version") != 1:
            errors.append("Unknown legal-state schema.")
        active = "LicenseRef-HaizFlow-Source-Available-1.0"
        if state.get("active_source_license") != active or project.get("license") != active:
            errors.append("Active source license and project metadata differ.")
        if text_hash(root / "LICENSE") != state.get("active_license_sha256"):
            errors.append("Active LICENSE changed without a reviewed activation change.")
        approval = state.get("owner_approval")
        if (state.get("proposal_status") != "adopted" or not isinstance(approval, dict)
                or not all(approval.get(key) for key in ("approved_by", "approved_at", "basis"))
                or approval.get("language_precedence") != "vi" or not state.get("effective_release")):
            errors.append("Active license requires explicit owner approval and Vietnamese precedence.")
        content = (root / "LICENSE").read_text(encoding="utf-8")
        if not content.startswith("# Giấy phép") or content.find("Bản quyền") > content.find("Copyright"):
            errors.append("Vietnamese license/copyright must precede English.")
        notice = (root / "NOTICE").read_text(encoding="utf-8")
        for required in ("Bản quyền (c) 2026 Mạch Hồng Hải", "Copyright (c) 2026 Mach Hong Hai",
                         "Source-Available", "Third-party"):
            if required not in notice:
                errors.append(f"NOTICE is missing attribution/state: {required}")
        for filename in DRAFTS:
            content = (root / "legal" / filename).read_text(encoding="utf-8")
            if "DRAFT" not in content or "NOT IN FORCE" not in content:
                errors.append(f"Unapproved document is not clearly marked as draft: {filename}")
        for filename in ("README.md", "README.vi.md"):
            content = (root / filename).read_text(encoding="utf-8")
            for link in ("(LICENSE)", "(NOTICE)", "(THIRD_PARTY_NOTICES.md)",
                         "(legal/LICENSE-SOURCE-AVAILABLE-DRAFT.md)", "(docs/licensing-review.md)"):
                if link not in content:
                    errors.append(f"Missing legal link in {filename}: {link}")
        if not (root / "THIRD_PARTY_NOTICES.md").is_file():
            errors.append("Repository third-party inventory is missing.")
        if artifact is not None:
            license_path = artifact / "LICENSE.txt"
            if not license_path.is_file():
                license_path = artifact / "LICENSE"
            notice_path = artifact / "NOTICE.txt"
            if not notice_path.is_file():
                notice_path = artifact / "NOTICE"
            if text_hash(license_path) != text_hash(root / "LICENSE"):
                errors.append("Artifact/installer LICENSE differs from the active source license.")
            if text_hash(notice_path) != text_hash(root / "NOTICE"):
                errors.append("Artifact NOTICE differs from the source attribution.")
            packaged_state = json.loads((artifact / "legal/license-state.json").read_text(encoding="utf-8"))
            if packaged_state != state:
                errors.append("Artifact legal state is stale or different from the source.")
            for filename in DRAFTS:
                if text_hash(artifact / "legal" / filename) != text_hash(root / "legal" / filename):
                    errors.append(f"Artifact legal draft differs: {filename}")
            if not (artifact / "THIRD_PARTY_NOTICES.md").is_file() or not (artifact / "licenses").is_dir():
                errors.append("Artifact third-party inventory/license directory is missing.")
        if public_release:
            blockers = state.get("blockers")
            if not isinstance(blockers, list) or blockers:
                errors.append("LICENSE COMPLIANCE BLOCKER: unresolved review gates: " + str(blockers))
            review = state.get("public_release_review")
            if not isinstance(review, dict) or not all(review.get(key) for key in ("approved_by", "approved_at", "source_commit")):
                errors.append("LICENSE COMPLIANCE BLOCKER: no explicit public release review.")
            elif review.get("release_version") != project["version"]:
                errors.append("LICENSE COMPLIANCE BLOCKER: review does not cover this release version.")
            else:
                clearances = review.get("clearances") or {}
                if set(clearances) != REQUIRED_CLEARANCES:
                    errors.append("LICENSE COMPLIANCE BLOCKER: incomplete reviewed clearance evidence.")
                for name, evidence in clearances.items():
                    if not isinstance(evidence, dict):
                        errors.append(f"Invalid clearance evidence: {name}")
                        continue
                    path = (root / str(evidence.get("path") or "")).resolve()
                    allowed = (root / "legal/reviews").resolve()
                    if allowed not in path.parents or not path.is_file() or path.is_symlink():
                        errors.append(f"Missing scoped clearance evidence: {name}")
                    elif text_hash(path) != evidence.get("sha256"):
                        errors.append(f"Changed clearance evidence: {name}")
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        errors.append(f"Legal state is incomplete or unreadable: {error}")
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--public-release", action="store_true")
    args = parser.parse_args(argv)
    errors = verify(artifact=args.artifact, public_release=args.public_release)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("Legal documents are consistent. Active license: HaizFlow Source-Available 1.0. Not release clearance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

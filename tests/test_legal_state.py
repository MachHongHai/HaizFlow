from __future__ import annotations

import importlib.util
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify_legal_state", ROOT / "scripts/verify-legal-state.py")
legal = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(legal)


class LegalStateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="haizflow-legal-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "source"
        self.root.mkdir()
        for name in ("LICENSE", "NOTICE", "pyproject.toml", "README.md", "README.vi.md", "THIRD_PARTY_NOTICES.md"):
            shutil.copy2(ROOT / name, self.root / name)
        shutil.copytree(ROOT / "legal", self.root / "legal")

    def update_state(self, **values):
        path = self.root / "legal/license-state.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        state.update(values)
        path.write_text(json.dumps(state), encoding="utf-8")

    def artifact(self):
        artifact = Path(self.temporary.name) / "artifact"
        artifact.mkdir()
        shutil.copy2(self.root / "LICENSE", artifact / "LICENSE.txt")
        shutil.copy2(self.root / "NOTICE", artifact / "NOTICE.txt")
        shutil.copy2(self.root / "THIRD_PARTY_NOTICES.md", artifact / "THIRD_PARTY_NOTICES.md")
        shutil.copytree(self.root / "legal", artifact / "legal")
        (artifact / "licenses").mkdir()
        return artifact

    def test_current_state_is_consistent_but_not_legal_approval(self):
        self.assertEqual(legal.verify(self.root), [])
        self.assertEqual(legal.verify(ROOT), [])

    def test_public_release_is_blocked_until_review(self):
        self.assertTrue(any("LICENSE COMPLIANCE BLOCKER" in error for error in legal.verify(self.root, public_release=True)))

    def test_emptying_blockers_does_not_bypass_review(self):
        self.update_state(blockers=[])
        self.assertTrue(any("no explicit" in error for error in legal.verify(self.root, public_release=True)))

    def test_approval_field_cannot_activate_unapproved_terms(self):
        self.update_state(proposal_status="approved", owner_approval="owner")
        self.assertTrue(any("explicit owner approval" in error for error in legal.verify(self.root)))

    def test_changed_license_requires_reviewed_hash(self):
        (self.root / "LICENSE").write_text("Restricted redistribution", encoding="utf-8")
        self.assertTrue(any("Active LICENSE changed" in error for error in legal.verify(self.root)))

    def test_each_draft_is_not_in_force(self):
        for filename in legal.DRAFTS:
            self.assertIn("NOT IN FORCE", (self.root / "legal" / filename).read_text(encoding="utf-8"))

    def test_draft_marker_removal_fails(self):
        (self.root / "legal" / legal.DRAFTS[0]).write_text("Active terms", encoding="utf-8")
        self.assertTrue(any("not clearly marked" in error for error in legal.verify(self.root)))

    def test_packaged_terms_must_match_active_license(self):
        artifact = self.artifact()
        self.assertEqual(legal.verify(self.root, artifact=artifact), [])
        (artifact / "LICENSE.txt").write_text("wrong agreement", encoding="utf-8")
        self.assertTrue(any("Artifact/installer LICENSE" in error for error in legal.verify(self.root, artifact=artifact)))

    def test_packaged_drafts_are_checked(self):
        artifact = self.artifact()
        (artifact / "legal" / legal.DRAFTS[1]).write_text("changed", encoding="utf-8")
        self.assertTrue(any("Artifact legal draft differs" in error for error in legal.verify(self.root, artifact=artifact)))

    def test_malformed_state_fails_closed(self):
        (self.root / "legal/license-state.json").write_text("[]", encoding="utf-8")
        self.assertTrue(legal.verify(self.root))

    def test_readme_local_file_links_exist(self):
        for filename in ("README.md", "README.vi.md"):
            content = (ROOT / filename).read_text(encoding="utf-8")
            for target in re.findall(r"\]\(([^)\s]+)\)", content):
                if "://" in target or target.startswith(("#", "mailto:")):
                    continue
                self.assertTrue((ROOT / target.split("#", 1)[0]).exists(), f"{filename}: {target}")

    def test_creator_and_legal_ui_match_current_state(self):
        about = (ROOT / "src/haizflow/desktop/qml/AboutDialog.qml").read_text(encoding="utf-8")
        self.assertIn("root.controller.currentAppVersion", about)
        self.assertNotIn("Khởi tạo bởi", about)
        self.assertNotIn("THIRD_PARTY_NOTICES.md", about)
        copyright = (ROOT / "src/haizflow/desktop/qml/CopyrightDialog.qml").read_text(encoding="utf-8")
        self.assertIn("© 2026 Mạch Hồng Hải", copyright)
        self.assertIn("HaizFlow Source-Available 1.0", copyright)
        self.assertIn("THIRD_PARTY_NOTICES.md", copyright)
        installer = (ROOT / "installer/HaizFlow.iss").read_text(encoding="utf-8")
        self.assertIn('LicenseFile={#SourceDir}\\LICENSE.txt', installer)
        self.assertNotIn("LicenseFile={#SourceDir}\\legal", installer)

    def test_packaging_scripts_keep_existing_verification_and_copy_legal_bundle(self):
        for filename in ("build-exe.ps1", "build-resource-engine.ps1", "build-installer.ps1"):
            text = (ROOT / "scripts" / filename).read_text(encoding="utf-8")
            self.assertIn("verify-legal-state.py", text)
            self.assertIn("--public-release", text)
        self.assertIn("Sign-ReleaseExecutable", (ROOT / "scripts/build-exe.ps1").read_text(encoding="utf-8"))
        self.assertIn("verify-installer-eligibility", (ROOT / "scripts/build-installer.ps1").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

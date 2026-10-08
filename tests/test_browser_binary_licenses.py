import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_active_browser_notices_match_pinned_inventory():
    folder = ROOT / "licenses"
    manifest = json.loads((folder / "BROWSER-BINARY-LICENSES.json").read_text(encoding="utf-8"))
    assert "not redistributed" in manifest["browser_delivery"]
    for component in manifest["components"]:
        path = folder / component["text"]
        assert path.parent == folder
        assert hashlib.sha256(path.read_bytes()).hexdigest() == component["sha256"]
        assert component["source"].startswith("https://raw.githubusercontent.com/")
        assert "cloak" not in component["name"].lower()
    assert not (folder / "CloakBrowser-MIT.txt").exists()
    assert not (folder / "CloakBrowser-BINARY-LICENSE.md").exists()


def test_packaging_retains_notices_and_excludes_browser_binaries():
    generator = (ROOT / "scripts/generate-third-party-notices.py").read_text(encoding="utf-8")
    for name in ("Chromium-BSD-3-Clause.txt", "Playwright-NOTICE.txt"):
        assert name in generator
    assert "CloakBrowser-BINARY-LICENSE.md" not in generator
    build = (ROOT / "scripts/build-exe.ps1").read_text(encoding="utf-8")
    assert '"runtime\\douyin-cloak"' in build and '"runtime\\douyin-browser"' in build
    assert '"runtime\\douyin-chromium"' in build
    assert build.count('"cloakbrowser"') == 2  # Exclusion and artifact guard.
    assert '"--collect-all", "playwright"' in build


def test_backend_uses_explicit_pack_and_locked_driver():
    backend = (ROOT / "src/haizflow/services/douyin_browser.py").read_text(encoding="utf-8")
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "cloakbrowser" not in backend.lower()
    assert "cloakbrowser" not in project.lower()
    assert '"playwright==1.63.0"' in project
    assert "douyin_component" in backend and "installed()" in backend
    assert "urlopen" not in backend


def test_source_inventory_distinguishes_direct_download_from_redistribution():
    document = (ROOT / "docs/douyin-distribution.md").read_text(encoding="utf-8")
    assert "do not contain Chromium" in document
    assert "directly over TLS" in document
    assert "not a complete license inventory" in document
    assert "CloakBrowser is not imported" in document

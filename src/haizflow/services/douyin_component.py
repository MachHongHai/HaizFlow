"""Chromium resource-pack identity and integrity. No implicit downloads."""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

PACK_ID = "browser-douyin-chromium"
REVISION = "1714059"
VERSION = "157.0.8092.0"
URL = f"https://storage.googleapis.com/chromium-browser-snapshots/Win_x64/{REVISION}/chrome-win.zip"
SHA256 = "bcd33aa9cd52ae75da0f84cbc5915c7583f0f791e5abe711ab1ca2ef37b00b19"
ARCHIVE_BYTES = 361641954
INSTALLED_BYTES = 484202247
MISSING_MESSAGE = "Install the Douyin browser in Resource Packs before creating a session."
EXCLUDED = {"interactive_ui_tests.exe", "setup.exe", "First Run"}


def component_root():
    from haizflow.core.paths import engines_dir
    return engines_dir() / PACK_ID / REVISION


def file_digest(path, cancel_event=None):
    from haizflow.services.model_bootstrap import ModelBootstrapCancelled
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            if cancel_event and cancel_event.is_set():
                raise ModelBootstrapCancelled("Browser verification paused.")
            digest.update(block)
    return digest.hexdigest()


def write_inventory(root: Path, cancel_event=None):
    from haizflow.services.model_bootstrap import ModelBootstrapCancelled
    if cancel_event and cancel_event.is_set():
        raise ModelBootstrapCancelled("Browser verification paused.")
    rows = [{"file": path.relative_to(root).as_posix(), "size": path.stat().st_size,
             "sha256": file_digest(path, cancel_event)} for path in sorted((root / "chrome-win").rglob("*")) if path.is_file()]
    (root / "browser-files.json").write_text(json.dumps(rows, indent=2), "utf-8")


def verify_files(root: Path, *, full=False, cancel_event=None):
    from haizflow.services.model_bootstrap import ModelBootstrapCancelled
    from haizflow.update.filesystem import no_links
    root = Path(root)
    no_links(root)
    rows = json.loads((root / "browser-files.json").read_text("utf-8"))
    if not rows or not isinstance(rows, list):
        raise ValueError("Missing Chromium file inventory")
    names = set()
    for row in rows:
        if cancel_event and cancel_event.is_set():
            raise ModelBootstrapCancelled("Browser verification paused.")
        path = root / row["file"]
        if not path.resolve().is_relative_to(root.resolve()) or not row["file"].startswith("chrome-win/"):
            raise ValueError("Unsafe Chromium file inventory")
        no_links(path)
        if row["file"] in names or not path.is_file() or path.stat().st_size != row["size"]:
            raise ValueError("Chromium file missing or changed")
        names.add(row["file"])
        if full and file_digest(path, cancel_event) != row["sha256"]:
            raise ValueError("Chromium file checksum mismatch")
    if not {"chrome-win/chrome.exe", "chrome-win/chrome.dll", "chrome-win/resources.pak", "chrome-win/icudtl.dat"} <= names:
        raise ValueError("Chromium files incomplete")


def installed(root: Path | None = None):
    root = root or component_root()
    try:
        marker = json.loads((root / "complete.json").read_text("utf-8"))
        if (marker.get("pack_id") != PACK_ID or marker.get("version") != REVISION
                or marker.get("archive_sha256") != SHA256
                or marker.get("browser_inventory_sha256") != file_digest(root / "browser-files.json")):
            return False
        verify_files(root)
        return True
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def smoke(root: Path, cancel_event=None):
    """Test an owned headless blank window; never open Douyin during install."""
    from playwright.sync_api import sync_playwright
    verify_files(root, full=True, cancel_event=cancel_event)
    with tempfile.TemporaryDirectory(prefix="browser-smoke-", dir=root.parent) as profile:
        with sync_playwright() as driver:
            context = driver.chromium.launch_persistent_context(
                profile, executable_path=str(root / "chrome-win/chrome.exe"), headless=True,
                chromium_sandbox=True, timeout=15000,
                args=["--no-first-run", "--no-default-browser-check", "--disable-background-networking"])
            try:
                (context.pages[0] if context.pages else context.new_page()).goto("about:blank")
            finally:
                context.close()

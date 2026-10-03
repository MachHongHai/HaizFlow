"""Public official GitHub Releases only; checks integrity, not authorship."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from .filesystem import UpdateError, child, no_links, version
from .manifest import Manifest

API = "https://api.github.com/repos/MachHongHai/HaizFlow/releases/latest"
REPOSITORY = "https://github.com/MachHongHai/HaizFlow"
CDN_HOSTS = {"release-assets.githubusercontent.com", "objects.githubusercontent.com"}


def allowed_url(url: str, *, api: bool = False) -> None:
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in {None, 443}
            or parsed.fragment or (api and url != API)):
        raise UpdateError("Nguồn tải cập nhật không được phép.")
    if not api and not (parsed.hostname in CDN_HOSTS or (
            parsed.hostname == "github.com" and parsed.path.startswith("/MachHongHai/HaizFlow/releases/download/"))):
        raise UpdateError("Nguồn tải cập nhật không được phép.")


class RedirectPolicy(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        # Validate BEFORE opening a redirected connection, not only after read.
        if request.full_url == API:
            raise UpdateError("GitHub API chuyển hướng không được phép.")
        allowed_url(request.full_url)
        allowed_url(newurl)
        return super().redirect_request(request, response, code, message, headers, newurl)


class GitHubClient:
    def __init__(self, *, opener=None):
        self.opener = opener or urllib.request.build_opener(RedirectPolicy()).open

    def latest(self) -> dict:
        request = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json",
            "User-Agent": "HaizFlow-CoreUpdater/1", "X-GitHub-Api-Version": "2026-03-10"})
        with self.opener(request, timeout=15) as response:
            if response.geturl() != API:
                raise UpdateError("GitHub API trả về nguồn không được phép.")
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise UpdateError("Release metadata quá lớn.")
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("draft") is not False or data.get("prerelease") is not False:
            raise UpdateError("Release không phải bản stable đã công bố.")
        tag = data.get("tag_name")
        if not isinstance(tag, str) or not tag.startswith("v"):
            raise UpdateError("Release tag không hợp lệ.")
        version(tag[1:])
        if data.get("html_url") != f"{REPOSITORY}/releases/tag/{tag}" or not isinstance(data.get("assets"), list):
            raise UpdateError("Release không thuộc repository chính thức.")
        return data

    def asset(self, release: dict, name: str, *, maximum: int = 8 * 1024**3) -> dict:
        candidates = [entry for entry in release["assets"] if isinstance(entry, dict) and entry.get("name") == name]
        if len(candidates) != 1:
            raise UpdateError("Bản phát hành thiếu hoặc trùng asset cập nhật.")
        entry = candidates[0]
        expected_url = f"{REPOSITORY}/releases/download/{release['tag_name']}/{name}"
        if (entry.get("browser_download_url") != expected_url or type(entry.get("size")) is not int
                or not 0 < entry["size"] <= maximum or entry.get("state") != "uploaded"
                or not re.fullmatch(r"sha256:[a-fA-F0-9]{64}", str(entry.get("digest")))):
            raise UpdateError("Asset không có metadata toàn vẹn hợp lệ.")
        return {"name": name, "size": entry["size"], "sha256": entry["digest"][7:].lower(), "url": expected_url}

    def download(self, asset: dict, directory: Path, *, progress=lambda *_: None) -> Path:
        allowed_url(asset["url"])
        no_links(directory)
        directory.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(directory).free < asset["size"] + 64 * 1024**2:
            raise UpdateError("Không đủ dung lượng đĩa để tải bản cập nhật.")
        destination = child(directory, asset["name"])
        partial = child(directory, asset["name"] + ".part")
        digest = hashlib.sha256()
        count = 0
        try:
            request = urllib.request.Request(asset["url"], headers={"User-Agent": "HaizFlow-CoreUpdater/1"})
            with self.opener(request, timeout=30) as response, partial.open("wb") as output:
                allowed_url(response.geturl())
                for block in iter(lambda: response.read(1024 * 1024), b""):
                    count += len(block)
                    if count > asset["size"]:
                        raise UpdateError("Dung lượng tải xuống không khớp asset.")
                    output.write(block)
                    digest.update(block)
                    progress("downloading", min(50, int(50 * count / asset["size"])))
                output.flush()
                os.fsync(output.fileno())
            if count != asset["size"] or digest.hexdigest() != asset["sha256"]:
                raise UpdateError("Tải xuống chưa đầy đủ hoặc SHA-256 không khớp.")
            os.replace(partial, destination)
            return destination
        finally:
            partial.unlink(missing_ok=True)

    def fetch_manifest(self, release: dict, name: str, directory: Path) -> Manifest:
        from .filesystem import read_json
        path = self.download(self.asset(release, name, maximum=8 * 1024**2), directory)
        manifest = Manifest.parse(read_json(path))
        if name != manifest.data["package_name"].removesuffix(".zip") + ".manifest.json":
            raise UpdateError("Tên manifest không khớp loại package.")
        if manifest.data["target_version"] != release["tag_name"][1:]:
            raise UpdateError("Manifest không khớp release tag.")
        return manifest

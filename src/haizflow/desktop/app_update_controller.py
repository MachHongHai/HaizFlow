"""Non-blocking stable-release checks for the desktop application."""

from __future__ import annotations

import json
import hashlib
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QObject, Signal

from haizflow import __version__

LATEST_RELEASE_API = "https://api.github.com/repos/MachHongHai/HaizFlow/releases/latest"
RELEASES_URL = "https://github.com/MachHongHai/HaizFlow/releases"
_RELEASE_URL_PREFIX = "https://github.com/MachHongHai/HaizFlow/releases/"
_DOWNLOAD_URL_PREFIX = _RELEASE_URL_PREFIX + "download/"


def installer_asset(payload: dict, version: str) -> dict:
    """Accept only this release's signed Windows setup with an API checksum."""
    name = f"HaizFlow-{version}-Setup.exe"
    tag = str(payload.get("tag_name") or "")
    assets = payload.get("assets")
    for asset in assets if isinstance(assets, list) else []:
        if not isinstance(asset, dict) or asset.get("name") != name:
            continue
        url = str(asset.get("browser_download_url") or "")
        digest = str(asset.get("digest") or "")
        size = asset.get("size")
        if (url != f"{_DOWNLOAD_URL_PREFIX}{tag}/{name}"
                or not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest)
                or not isinstance(size, int) or not 0 < size <= 2 * 1024**3):
            continue
        return {"name": name, "url": url, "sha256": digest[7:].lower(), "size": size}
    return {}


def verify_installer_signature(path: Path) -> None:
    """Do not execute an unsigned, tampered or untrusted Windows installer."""
    import base64

    quoted = str(path).replace("'", "''")
    command = (
        f"$s = Get-AuthenticodeSignature -LiteralPath '{quoted}'; "
        "if ($s.Status -ne 'Valid') { exit 1 }"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand",
         base64.b64encode(command.encode("utf-16-le")).decode("ascii")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False,
    )
    if result.returncode:
        raise ValueError("Bộ cài chưa có chữ ký hợp lệ. Không thể cập nhật tự động.")


def version_key(value: str) -> tuple[int, int, int, int]:
    """Return a comparable key for stable SemVer-like tags."""
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?", str(value).strip())
    if not match:
        raise ValueError(f"Invalid release version: {value}")
    major, minor, patch = (int(match.group(index)) for index in range(1, 4))
    return major, minor, patch, 0 if match.group(4) else 1


class AppUpdateController(QObject):
    changed = Signal()

    def __init__(self, host):
        super().__init__(host)
        self._host = host
        self._state = "idle"
        self._latest_version = ""
        self._release_notes = ""
        self._release_url = RELEASES_URL
        self._error = ""
        self._events: queue.Queue[dict] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._manual_request = False
        self._installer = {}
        self._download_thread: threading.Thread | None = None
        self._download_progress = 0
        self._last_checked = 0.0
        self._stop = threading.Event()
        self._installer_process = None

    @property
    def current_version(self) -> str:
        return str(__version__)

    @property
    def latest_version(self) -> str:
        return self._latest_version

    @property
    def release_notes(self) -> str:
        return self._release_notes

    @property
    def release_url(self) -> str:
        return self._release_url

    @property
    def state(self) -> str:
        return self._state

    @property
    def error(self) -> str:
        return self._error

    @property
    def available(self) -> bool:
        return bool(self._latest_version and version_key(self._latest_version) > version_key(self.current_version))

    @property
    def download_progress(self) -> int:
        return self._download_progress

    @property
    def blocked(self) -> bool:
        return any(bool(getattr(self._host, name, False)) for name in (
            "isProcessing", "resourcePackBusy", "mediaImportBusy", "channelImportBusy", "videoExportBusy",
            "backgroundMusicImportBusy", "tiktokPublishBusy", "editorPreviewBusy",
        ))

    def check_if_needed(self) -> None:
        if self._state in {"idle", "error"} or time.monotonic() - self._last_checked > 15 * 60:
            self.check()

    def install(self) -> bool:
        if self._state in {"downloading", "verifying", "installing"}:
            return False
        if self.blocked:
            self._error = "Dừng hoặc chờ các tác vụ hoàn tất trước khi cập nhật."
        elif not self.available:
            return False
        elif not getattr(sys, "frozen", False) or sys.platform != "win32":
            self._error = "Cập nhật trực tiếp chỉ dùng trong bản HaizFlow đã cài đặt."
        elif not self._installer:
            self._error = "Bản phát hành chưa có bộ cài Windows kèm mã kiểm tra. Hãy xem chi tiết cập nhật."
        else:
            self._error = ""
            self._state = "downloading"
            self._download_progress = 0
            asset = dict(self._installer)
            self._download_thread = threading.Thread(
                target=self._download_installer, args=(asset,), name="app-update-download", daemon=True,
            )
            self._download_thread.start()
            self.changed.emit()
            return True
        self.changed.emit()
        return False

    def _download_installer(self, asset: dict) -> None:
        from haizflow.config import TMP_DIR

        root = Path(TMP_DIR) / "app-updates"
        output = root / asset["name"]
        partial = None
        try:
            root.mkdir(parents=True, exist_ok=True)
            if root.is_symlink() or root.is_junction() or output.is_symlink():
                raise ValueError("Vị trí lưu bộ cài không hợp lệ.")
            descriptor, name = tempfile.mkstemp(prefix=output.stem + "-", suffix=".part", dir=root)
            os.close(descriptor)
            partial = Path(name)
            digest = hashlib.sha256()
            downloaded = 0
            request = urllib.request.Request(asset["url"], headers={"User-Agent": f"HaizFlow/{self.current_version}"})
            with urllib.request.urlopen(request, timeout=30) as response, partial.open("wb") as target:
                final_url = urlparse(response.geturl())
                if final_url.scheme != "https" or final_url.hostname not in {
                    "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com",
                }:
                    raise ValueError("Địa chỉ tải bộ cài không hợp lệ.")
                while chunk := response.read(1024 * 1024):
                    if self._stop.is_set():
                        return
                    downloaded += len(chunk)
                    if downloaded > asset["size"]:
                        raise ValueError("Dung lượng bộ cài không khớp bản phát hành.")
                    target.write(chunk)
                    digest.update(chunk)
                    self._events.put({"kind": "download_progress", "value": int(downloaded * 100 / asset["size"])})
            if downloaded != asset["size"] or digest.hexdigest() != asset["sha256"]:
                raise ValueError("Bộ cài tải xuống chưa đầy đủ hoặc mã kiểm tra không khớp. Hãy thử lại.")
            self._events.put({"kind": "verifying"})
            os.replace(partial, output)
            verify_installer_signature(output)
            if self._stop.is_set():
                return
            self._events.put({"kind": "installer_ready", "path": str(output)})
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            self._events.put({"kind": "install_error", "message": str(exc) if isinstance(exc, ValueError)
                              else "Không thể tải bản cập nhật. Kiểm tra kết nối mạng rồi thử lại."})
        finally:
            if partial is not None:
                try:
                    partial.unlink(missing_ok=True)
                except OSError:
                    pass

    def check(self, *, manual: bool = False) -> None:
        if self._state in {"downloading", "verifying", "installing"}:
            return
        if self._thread is not None and self._thread.is_alive():
            self._manual_request = self._manual_request or bool(manual)
            return
        self._manual_request = bool(manual)
        self._state = "checking"
        self._error = ""
        self.changed.emit()

        def worker() -> None:
            try:
                request = urllib.request.Request(
                    LATEST_RELEASE_API,
                    headers={
                        "Accept": "application/vnd.github+json",
                        "User-Agent": f"HaizFlow/{self.current_version}",
                    },
                )
                with urllib.request.urlopen(request, timeout=8) as response:
                    payload = json.loads(response.read(512 * 1024).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("Invalid release metadata.")
                tag = str(payload.get("tag_name") or "").strip()
                url = str(payload.get("html_url") or "").strip()
                if not url.startswith(_RELEASE_URL_PREFIX):
                    raise ValueError("GitHub returned an unexpected release address.")
                available = version_key(tag) > version_key(self.current_version)
                self._events.put(
                    {
                        "kind": "result",
                        "available": available,
                        "version": tag.removeprefix("v"),
                        "notes": str(payload.get("body") or "").strip()[:1600],
                        "url": url,
                        "installer": installer_asset(payload, tag.removeprefix("v")),
                    }
                )
            except urllib.error.HTTPError as exc:
                # GitHub returns 404 until the first stable release exists.
                # This is not a connectivity failure during pre-release builds.
                self._events.put(
                    {"kind": "no_release"} if exc.code == 404
                    else {"kind": "error", "message": str(exc)}
                )
            except (OSError, ValueError, KeyError, json.JSONDecodeError, urllib.error.URLError) as exc:
                self._events.put({"kind": "error", "message": str(exc)})

        self._thread = threading.Thread(target=worker, name="app-update-check", daemon=True)
        self._thread.start()

    def drain_events(self) -> None:
        if self._installer_process is not None and self._installer_process.poll() is not None:
            self._installer_process = None
            self._state = "available"
            self._error = "Bộ cài đã đóng. Nếu cập nhật thành công, hãy khởi động lại HaizFlow."
            self.changed.emit()
        # Apply only on Qt's thread; the workers never mutate QML properties.
        for _ in range(128):
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            self._apply_event(event)

    def _apply_event(self, event: dict) -> None:
        if event["kind"] == "download_progress":
            self._download_progress = event["value"]
            self.changed.emit()
            return
        if event["kind"] == "verifying":
            self._state = "verifying"
            self.changed.emit()
            return
        if event["kind"] == "installer_ready":
            if self._stop.is_set():
                return
            if self.blocked:
                self._apply_event({"kind": "install_error", "message": "Tác vụ đang chạy. Dừng hoặc chờ hoàn tất rồi cập nhật lại."})
                return
            try:
                # Inno Setup uses the previous install directory and preserves
                # project data; its wizard handles closing the running app.
                self._installer_process = subprocess.Popen([event["path"], "/SP-", "/NORESTART"])
                self._state = "installing"
                self._error = ""
            except OSError:
                self._state = "available"
                self._error = "Không thể mở bộ cài. Hãy thử lại."
            self.changed.emit()
            return
        if event["kind"] == "install_error":
            self._state = "available"
            self._error = event.get("message", "")
            self.changed.emit()
            return
        self._last_checked = time.monotonic()
        if event["kind"] == "result":
            self._latest_version = event["version"]
            self._release_notes = event["notes"]
            self._release_url = event["url"]
            self._installer = event.get("installer", {})
            self._state = "available" if event["available"] else "current"
            self._error = ""
            self.changed.emit()
        elif event["kind"] == "no_release":
            self._state = "no_release"
            self._error = ""
            self._latest_version = ""
            self._installer = {}
            self.changed.emit()
        else:
            self._state = "error"
            self._error = event.get("message", "")
            self.changed.emit()
        if self._manual_request:
            self._host.appUpdateAvailable.emit()

    def shutdown(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=0.2)

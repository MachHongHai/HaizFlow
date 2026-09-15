"""Non-blocking stable-release checks for the desktop application."""

from __future__ import annotations

import json
import queue
import re
import threading
import urllib.error
import urllib.request

from PySide6.QtCore import QObject, Signal

from haizflow import __version__

LATEST_RELEASE_API = "https://api.github.com/repos/MachHongHai/HaizFlow/releases/latest"
RELEASES_URL = "https://github.com/MachHongHai/HaizFlow/releases"
_RELEASE_URL_PREFIX = "https://github.com/MachHongHai/HaizFlow/releases/"


def version_key(value: str) -> tuple[int, int, int, int]:
    """Return a comparable key for stable SemVer-like tags."""
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:[-+]([0-9A-Za-z.-]+))?", str(value).strip())
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

    def check(self, *, manual: bool = False) -> None:
        if self._thread is not None and self._thread.is_alive():
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
                    }
                )
            except (OSError, ValueError, KeyError, json.JSONDecodeError, urllib.error.URLError) as exc:
                self._events.put({"kind": "error", "message": str(exc)})

        self._thread = threading.Thread(target=worker, name="app-update-check", daemon=True)
        self._thread.start()

    def drain_events(self) -> None:
        try:
            event = self._events.get_nowait()
        except queue.Empty:
            return
        if event["kind"] == "result":
            self._latest_version = event["version"]
            self._release_notes = event["notes"]
            self._release_url = event["url"]
            self._state = "available" if event["available"] else "current"
            self._error = ""
            self.changed.emit()
            if event["available"]:
                self._host.appUpdateAvailable.emit()
            elif self._manual_request:
                self._host.appAlertRequested.emit(
                    "HaizFlow đã được cập nhật",
                    f"Bạn đang dùng phiên bản {self.current_version} mới nhất.",
                    "information",
                )
        else:
            self._state = "error"
            self._error = event.get("message", "")
            self.changed.emit()
            if self._manual_request:
                self._host.appAlertRequested.emit(
                    "Không kiểm tra được bản cập nhật",
                    "Kiểm tra kết nối mạng rồi thử lại.",
                    "warning",
                )

    def shutdown(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=0.2)

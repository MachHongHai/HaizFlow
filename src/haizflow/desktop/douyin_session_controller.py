"""UI-owned consent action; all browser work stays off the Qt thread."""
from __future__ import annotations

import threading

from PySide6.QtCore import Property, QObject, Signal, Slot


class DouyinSessionController(QObject):
    changed = Signal()
    _finished = Signal(str)
    _progress = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False
        self._ready = False
        self._status = ""
        self._cancel = threading.Event()
        self._thread = None
        self._verified_during_refresh = False
        self._finished.connect(self._complete)
        self._progress.connect(self._set_status)

    @Property(bool, notify=changed)
    def busy(self):
        return self._busy

    @Property(str, notify=changed)
    def status(self):
        return self._status

    @Property(bool, notify=changed)
    def ready(self):
        return self._ready

    @Slot()
    def create(self):
        if self._busy:
            return
        self._busy = True
        self._verified_during_refresh = False
        self._status = "Creating Douyin session"
        self._cancel = threading.Event()
        self.changed.emit()

        def run():
            from haizflow.services.douyin_adapter import get_douyin_adapter
            from haizflow.services.video_download import DownloadCancelled
            try:
                get_douyin_adapter().create_browser_session(self._cancel, status_callback=self._progress.emit)
                result = "Douyin session ready"
            except DownloadCancelled:
                result = "Douyin session cancelled"
            except Exception as exc:
                result = str(exc)
            self._finished.emit(result)

        self._thread = threading.Thread(target=run, name="douyin-session", daemon=True)
        self._thread.start()

    @Slot()
    def cancel(self):
        self._cancel.set()

    def _complete(self, status):
        self._busy = False
        if status != "Douyin session ready" and self._verified_during_refresh:
            status = "Douyin session ready"
        elif status != "Douyin session ready" and self._ready:
            status = ("Douyin refresh cancelled; previous session retained" if status == "Douyin session cancelled"
                      else "Douyin refresh failed; previous session retained")
        self._set_status(status)

    def _set_status(self, status):
        if status == "Douyin request succeeded":
            self._verified_during_refresh = self._busy
            status = "Douyin session ready"
            self._ready = True
        elif status == "Douyin session ready" and self._busy:
            # An SDK signing probe is not the completed refresh operation.
            status = "Checking the Douyin session"
        self._status = str(status)
        if self._status == "Douyin session ready":
            self._ready = True
        self.changed.emit()

    def shutdown(self):
        self._cancel.set()
        if self._thread:
            self._thread.join(timeout=1)
        from haizflow.services.douyin_adapter import close_douyin_browser
        close_douyin_browser()

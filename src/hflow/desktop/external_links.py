"""Hand web links to the operating system's default URL handler through Qt."""

from __future__ import annotations

import logging

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


LOGGER = logging.getLogger(__name__)


def open_external_url(value: str) -> bool:
    """Open a valid HTTP(S) URL without choosing a browser or managing windows.

    A true result means Qt accepted the request, not that the page has loaded.
    The OS and default browser decide whether to reuse an existing session.
    """
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text or any(ord(character) < 32 or ord(character) == 127 for character in text):
        return False
    try:
        url = QUrl(text, QUrl.ParsingMode.StrictMode)
        if (
            not url.isValid()
            or url.isRelative()
            or url.scheme().lower() not in {"http", "https"}
            or not url.host()
            or url.userInfo()
        ):
            return False
        return bool(QDesktopServices.openUrl(url))
    except (RuntimeError, TypeError, ValueError, OSError):
        LOGGER.warning("Could not hand the external link to the system URL handler", exc_info=True)
        return False

"""Qt translation catalog lifecycle for the desktop presentation layer."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTranslator


_translator: QTranslator | None = None
_installed_language = ""


def install_ui_translator(language: str) -> bool:
    """Install the catalog for *language* and return whether it changed."""
    global _translator, _installed_language
    normalized = "vi" if str(language or "").lower().startswith("vi") else "en"
    if normalized == _installed_language:
        return False
    app = QCoreApplication.instance()
    if app is None:
        return False
    if _translator is not None:
        app.removeTranslator(_translator)
        _translator = None
    if normalized == "en":
        catalog = Path(__file__).resolve().parent / "translations" / "haizflow_en.qm"
        candidate = QTranslator(app)
        if catalog.is_file() and candidate.load(str(catalog)):
            app.installTranslator(candidate)
            _translator = candidate
    _installed_language = normalized
    return True

"""Desktop workflow for exporting redacted support diagnostics."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from haizflow.config import RUNTIME_DATA_DIR
from haizflow.core.diagnostics import export_diagnostics
from haizflow.desktop.localization import QFileDialog, QMessageBox


class DiagnosticsController:
    def __init__(self, host):
        self._host = host

    def export(self) -> bool:
        diagnostics_directory = Path(RUNTIME_DATA_DIR) / "diagnostics"
        diagnostics_directory.mkdir(parents=True, exist_ok=True)
        suggested = diagnostics_directory / f"HaizFlow-diagnostics-{datetime.now():%Y%m%d-%H%M%S}.zip"
        selected_path, _selected_filter = QFileDialog.getSaveFileName(
            None,
            "Export diagnostics",
            str(suggested),
            "ZIP archives (*.zip)",
        )
        if not selected_path:
            return False
        try:
            output_path = export_diagnostics(selected_path)
        except Exception as exc:
            QMessageBox.critical(None, "Export diagnostics", f"Cannot export diagnostics: {exc}")
            return False
        QMessageBox.information(
            None,
            "Export diagnostics",
            "A redacted diagnostics archive was created. It excludes project media, project names, and project logs.\n\n"
            f"{output_path}",
        )
        return True

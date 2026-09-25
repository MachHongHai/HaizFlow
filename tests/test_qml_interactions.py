from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_qml_interactions_run_offscreen():
    root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ)
    environment["QT_QPA_PLATFORM"] = "offscreen"
    environment["QT_QUICK_CONTROLS_STYLE"] = "Basic"

    result = subprocess.run(
        [sys.executable, str(root / "tests" / "run_qml_tests.py")],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr

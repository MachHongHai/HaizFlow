from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtQuickTest import QUICK_TEST_MAIN


def main() -> int:
    test_directory = Path(__file__).resolve().parent / "qml"
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    arguments = [
        str(Path(__file__).resolve()),
        "-input",
        str(test_directory),
        *sys.argv[1:],
    ]
    return int(QUICK_TEST_MAIN("haizflow_qml", arguments, str(test_directory)))


if __name__ == "__main__":
    raise SystemExit(main())

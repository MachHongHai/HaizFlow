"""Interactive, project-free QA of native selection/cancel and owner restoration."""
import json
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QGridLayout, QLabel, QPushButton, QWidget

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from haizflow.desktop.native_file_picker import pick

app = QApplication([])
window = QWidget()
window.setWindowTitle("HaizFlow - Native Picker QA")
window.resize(640, 240)
layout = QGridLayout(window)
status = QLabel("Open / Multiple / Folder / Save: no project is modified.")
layout.addWidget(status, 0, 0, 1, 4)


def start(kind):
    state = window.windowState()
    try:
        directory = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "build"
        paths, selected = pick(kind, "HaizFlow QA - " + kind, str(directory),
                               "Video (*.mp4 *.mkv);;All files (*)", ("", 4))
        result = dict(kind=kind, paths=paths, selected_filter=selected)
    except Exception as exc:
        result = dict(kind=kind, error=str(exc))
    def report():
        result.update(minimized=window.isMinimized(), active=window.isActiveWindow(),
                      owner_state_restored=state == window.windowState())
        status.setText(json.dumps(result, ensure_ascii=False))
        print(json.dumps(result), flush=True)
    QTimer.singleShot(150, report)


for index, kind in enumerate(("open", "multiple", "folder", "save")):
    button = QPushButton(kind.title())
    button.clicked.connect(lambda _checked=False, value=kind: start(value))
    layout.addWidget(button, 1, index)
window.show()
raise SystemExit(app.exec())

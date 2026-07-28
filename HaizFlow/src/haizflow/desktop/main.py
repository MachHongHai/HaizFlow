import sys
from pathlib import Path

import haizflow.config as _runtime_config  # noqa: F401

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication

from haizflow.core.logging_config import configure_app_logging
from haizflow.desktop.qml_controller import HaizFlowController
from haizflow.desktop.single_instance import SingleInstanceCoordinator


def _configure_windows_app_identity() -> None:
    """Keep the development Python launcher from owning HaizFlow's taskbar icon."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MachHongHai.HaizFlow")
    except (AttributeError, OSError):
        pass


def _app_icon_path() -> Path | None:
    branding_dir = Path(__file__).resolve().parent / "assets" / "branding"
    for filename in ("haizflow.ico", "haizflow-mark.png"):
        candidate = branding_dir / filename
        if candidate.is_file():
            return candidate
    return None


def main(*, smoke_test: bool = False) -> None:
    configure_app_logging()
    _configure_windows_app_identity()
    app = QApplication(sys.argv)
    app.setApplicationName("HaizFlow")
    app_icon_path = _app_icon_path()
    app_icon = QIcon(str(app_icon_path)) if app_icon_path is not None else QIcon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)
    coordinator = None if smoke_test else SingleInstanceCoordinator()
    if coordinator is not None and not coordinator.acquire():
        return

    controller = None
    engine = None
    activation_pending = False

    def activate_window() -> None:
        nonlocal activation_pending
        roots = engine.rootObjects() if engine is not None else []
        if not roots:
            activation_pending = True
            return
        window = roots[0]
        if window.windowState() & Qt.WindowMinimized:
            window.showNormal()
        else:
            window.show()
        window.raise_()
        window.requestActivate()
        activation_pending = False

    if coordinator is not None:
        coordinator.activationRequested.connect(activate_window)

    try:
        engine = QQmlApplicationEngine()
        qml_dir = Path(__file__).resolve().parent / "qml"
        engine.addImportPath(str(qml_dir))
        engine.load(str(qml_dir / "Main.qml"))
        if not engine.rootObjects():
            raise SystemExit(1)
        window = engine.rootObjects()[0]
        if not app_icon.isNull():
            window.setIcon(app_icon)
        window.showMaximized()
        controller = HaizFlowController._qml_instance
        if controller is None:
            raise RuntimeError("QML did not create the AppController singleton")
        engine.rootObjects()[0].installEventFilter(controller)
        if activation_pending:
            QTimer.singleShot(0, activate_window)
        if smoke_test:
            QTimer.singleShot(1500, app.quit)
        exit_code = app.exec()
    finally:
        if controller is not None:
            controller.shutdown()
        if coordinator is not None:
            coordinator.close()
        if engine is not None:
            del engine
        if controller is not None:
            del controller
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

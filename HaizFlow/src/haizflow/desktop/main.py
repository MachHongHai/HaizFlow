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
from haizflow.desktop.translations import install_ui_translator
from haizflow.services import desktop_settings


def _configure_windows_app_identity() -> None:
    """Give frozen and Python-launched windows the same non-Python taskbar identity."""
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


def _set_windows_native_window_icon(window: object, icon_path: Path | None) -> tuple[int, ...]:
    """Set HWND icons explicitly so the Python launcher also has HaizFlow's taskbar icon."""
    if sys.platform != "win32" or icon_path is None or icon_path.suffix.lower() != ".ico":
        return ()
    try:
        import ctypes
        from ctypes import wintypes

        hwnd = int(window.winId())  # type: ignore[attr-defined]
        if not hwnd:
            return ()

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        load_image = user32.LoadImageW
        load_image.argtypes = (
            wintypes.HINSTANCE,
            wintypes.LPCWSTR,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        )
        load_image.restype = wintypes.HANDLE
        send_message = user32.SendMessageW
        send_message.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        send_message.restype = ctypes.c_ssize_t
        set_class_long = getattr(user32, "SetClassLongPtrW", user32.SetClassLongW)
        set_class_long.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
        set_class_long.restype = ctypes.c_ssize_t

        image_icon = 1
        lr_load_from_file = 0x0010
        wm_seticon = 0x0080
        icon_small = 0
        icon_big = 1
        icon_small2 = 2
        gclp_hicon = -14
        gclp_hiconsm = -34
        sm_cxicon = 11
        sm_cyicon = 12
        sm_cxsmicon = 49
        sm_cysmicon = 50

        def load_icon(width_metric: int, height_metric: int) -> int:
            width = user32.GetSystemMetrics(width_metric)
            height = user32.GetSystemMetrics(height_metric)
            return int(
                load_image(
                    None,
                    str(icon_path),
                    image_icon,
                    width,
                    height,
                    lr_load_from_file,
                )
                or 0
            )

        big_icon = load_icon(sm_cxicon, sm_cyicon)
        small_icon = load_icon(sm_cxsmicon, sm_cysmicon)
        if big_icon:
            send_message(hwnd, wm_seticon, icon_big, big_icon)
            set_class_long(hwnd, gclp_hicon, big_icon)
        if small_icon:
            send_message(hwnd, wm_seticon, icon_small, small_icon)
            send_message(hwnd, wm_seticon, icon_small2, small_icon)
            set_class_long(hwnd, gclp_hiconsm, small_icon)
        return tuple(handle for handle in (big_icon, small_icon) if handle)
    except (AttributeError, OSError, TypeError, ValueError):
        return ()


def _destroy_windows_icons(icon_handles: tuple[int, ...]) -> None:
    if sys.platform != "win32" or not icon_handles:
        return
    try:
        import ctypes

        for handle in icon_handles:
            ctypes.windll.user32.DestroyIcon(handle)
    except (AttributeError, OSError):
        pass


def main(*, smoke_test: bool = False) -> None:
    configure_app_logging()
    _configure_windows_app_identity()
    app = QApplication(sys.argv)
    app.setApplicationName("HaizFlow")
    app.setApplicationDisplayName("\u200B")
    install_ui_translator(desktop_settings.load_settings().get("language", "en"))
    app_icon_path = _app_icon_path()
    app_icon = QIcon(str(app_icon_path)) if app_icon_path is not None else QIcon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)
    coordinator = None if smoke_test else SingleInstanceCoordinator()
    if coordinator is not None and not coordinator.acquire():
        return

    controller = None
    engine = None
    native_icon_handles: tuple[int, ...] = ()
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
        # Maximized windowed mode keeps the native title bar, taskbar and Snap Layout.
        window.showMaximized()
        app.processEvents()
        native_icon_handles = _set_windows_native_window_icon(window, app_icon_path)

        last_non_minimized_state = window.windowState()
        was_minimized = False
        restore_maximized = False

        def preserve_pre_minimize_state(state: Qt.WindowState) -> None:
            nonlocal last_non_minimized_state, restore_maximized, was_minimized
            if state & Qt.WindowMinimized:
                if not was_minimized:
                    restore_maximized = bool(last_non_minimized_state & Qt.WindowMaximized)
                was_minimized = True
                return

            if was_minimized:
                was_minimized = False
                if restore_maximized and not state & Qt.WindowMaximized:
                    restore_maximized = False
                    QTimer.singleShot(0, window.showMaximized)
                    return

            restore_maximized = False
            last_non_minimized_state = state

        window.windowStateChanged.connect(preserve_pre_minimize_state)
        controller = HaizFlowController._qml_instance
        if controller is None:
            raise RuntimeError("QML did not create the AppController singleton")
        engine.rootObjects()[0].installEventFilter(controller)

        def retranslate_ui() -> None:
            if install_ui_translator(controller.settingsLanguage):
                engine.retranslate()

        controller.settingsChanged.connect(retranslate_ui)
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
        _destroy_windows_icons(native_icon_handles)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

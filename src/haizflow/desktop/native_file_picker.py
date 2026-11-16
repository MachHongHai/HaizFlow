"""Standard Qt/Windows pickers in a fresh, real-user Shell environment.

Do not import runtime configuration here: it deliberately redirects the model
workers' profile. Windows Shell caches known folders for the process lifetime.
"""

import json
import os
import sys
from pathlib import Path

PROFILE_KEYS = ("USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA")


def shell_environment() -> dict[str, str]:
    """Get the current Windows user's environment, not portable cache hints."""
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    userenv = ctypes.WinDLL("userenv", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    userenv.CreateEnvironmentBlock.argtypes = [ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.BOOL]
    userenv.DestroyEnvironmentBlock.argtypes = [ctypes.c_void_p]
    token, block = wintypes.HANDLE(), ctypes.c_void_p()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x000A, ctypes.byref(token)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not userenv.CreateEnvironmentBlock(ctypes.byref(block), token, False):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            native = {}
            address = block.value
            while entry := ctypes.wstring_at(address):
                key, _, value = entry.partition("=")
                if key:
                    native[key.upper()] = value
                address += len(entry.encode("utf-16-le", errors="surrogatepass")) + 2
        finally:
            userenv.DestroyEnvironmentBlock(block)
    finally:
        kernel.CloseHandle(token)
    environment = dict(os.environ)
    for key in PROFILE_KEYS:
        if not native.get(key):
            raise OSError(f"Windows user environment is missing {key}")
        environment[key] = native[key]
    environment["HOME"] = native["USERPROFILE"]
    environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return environment


def command(request_path: Path) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--native-file-dialog", str(request_path)]
    return [sys.executable, "-m", "haizflow.desktop.native_file_picker", str(request_path)]


def pick(kind: str, caption: str, directory: str, name_filter: str = "", args=(), parent=None):
    """Keep the Qt event loop responsive without changing host environment."""
    import tempfile
    from PySide6.QtCore import QEventLoop, QProcess, QProcessEnvironment
    from PySide6.QtGui import QGuiApplication
    from haizflow.config import TMP_DIR

    application = QGuiApplication.instance()
    window = application.focusWindow() if application else None
    owner = int(parent.winId()) if parent is not None else int(window.winId()) if window else 0
    with tempfile.TemporaryDirectory(prefix="native-picker-", dir=TMP_DIR, ignore_cleanup_errors=True) as temporary:
        request_path = Path(temporary) / "request.json"
        result_path = Path(temporary) / "result.json"
        request_path.write_text(json.dumps(dict(kind=kind, caption=str(caption), directory=str(directory or ""),
            name_filter=name_filter, selected_filter=str(args[0]) if args else "",
            options=int(getattr(args[1], "value", args[1])) if len(args) > 1 else 0,
            owner=owner, result=str(result_path)), ensure_ascii=False), encoding="utf-8")
        process = QProcess()
        environment = QProcessEnvironment()
        for key, value in shell_environment().items():
            environment.insert(key, value)
        process.setProcessEnvironment(environment)
        process.setWorkingDirectory(str(Path(environment.value("USERPROFILE"))))
        process.setProgram(command(request_path)[0])
        process.setArguments(command(request_path)[1:])
        process.setStandardOutputFile(QProcess.nullDevice())
        loop = QEventLoop()
        process.finished.connect(loop.quit)
        process.errorOccurred.connect(loop.quit)
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.IsWindowEnabled.argtypes = [wintypes.HWND]
        user32.IsWindowEnabled.restype = wintypes.BOOL
        user32.EnableWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
        host_windows = {int(item.winId()) for item in application.topLevelWindows()} if application else set()
        host_windows.add(owner)
        enabled_windows = {handle for handle in host_windows if handle and user32.IsWindowEnabled(handle)}
        try:
            for handle in enabled_windows:
                user32.EnableWindow(handle, False)
            process.start()
            # Windows can report FailedToStart synchronously. Entering an event
            # loop after its quit signal would otherwise leave the owner locked.
            if process.state() != QProcess.NotRunning:
                loop.exec()
            if process.exitStatus() != QProcess.NormalExit or process.exitCode() != 0 or not result_path.is_file():
                detail = bytes(process.readAllStandardError())[-16384:].decode("utf-8", errors="replace")
                raise OSError("Windows file picker could not start: " + process.errorString() + "\n" + detail)
            result = json.loads(result_path.read_text("utf-8"))
            if result.get("error"):
                raise OSError(result["error"])
            paths = result.get("paths")
            if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
                raise OSError("Invalid Windows file picker response")
            return paths, str(result.get("selected_filter") or "")
        finally:
            if process.state() != QProcess.NotRunning:
                process.kill()
                process.waitForFinished(5000)
            for handle in enabled_windows:
                user32.EnableWindow(handle, True)
            if window:
                try:
                    window.requestActivate()
                except RuntimeError:
                    pass  # Owner was closed during application shutdown.


def main(request_path: str) -> int:
    """Called before config, splash, single-instance IPC or worker imports."""
    from PySide6.QtWidgets import QApplication, QFileDialog, QWidget

    request = json.loads(Path(request_path).read_text("utf-8"))
    application = QApplication.instance() or QApplication([])
    application.setApplicationName("HaizFlow")
    application.setOrganizationName("MachHongHai")
    owner = QWidget()
    owner.setWindowTitle("HaizFlow")
    if request.get("owner") and os.name == "nt":
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        set_owner = user32.SetWindowLongPtrW
        set_owner.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        set_owner.restype = ctypes.c_ssize_t
        set_owner(int(owner.winId()), -8, int(request["owner"]))  # GWLP_HWNDPARENT
    result = dict(paths=[], selected_filter="", error="")
    try:
        options = QFileDialog.Option(int(request.get("options") or 0)) & ~QFileDialog.Option.DontUseNativeDialog
        caption, directory = request["caption"], request["directory"]
        kind = request["kind"]
        if kind == "folder":
            path = QFileDialog.getExistingDirectory(owner, caption, directory, options | QFileDialog.Option.ShowDirsOnly)
            result["paths"] = [path] if path else []
        elif kind in {"open", "multiple", "save"}:
            method = {"open": QFileDialog.getOpenFileName, "multiple": QFileDialog.getOpenFileNames,
                      "save": QFileDialog.getSaveFileName}[kind]
            paths, selected_filter = method(owner, caption, directory, request["name_filter"],
                                           request.get("selected_filter", ""), options)
            result.update(paths=paths if isinstance(paths, list) else [paths] if paths else [],
                          selected_filter=selected_filter)
        else:
            raise ValueError("Unsupported native picker operation")
    except Exception as error:
        result["error"] = str(error)
    Path(request["result"]).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    owner.deleteLater()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))

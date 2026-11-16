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
    # A development .pth hook redirects APPDATA/USERPROFILE before any module
    # is imported. A clean environment alone cannot defeat that hook. This
    # helper uses only stdlib: skip site, user startup and PYTHON* overrides.
    return [sys.executable, "-I", "-S", str(Path(__file__).resolve()), str(request_path)]


def pick(kind: str, caption: str, directory: str, name_filter: str = "", args=(), parent=None):
    """Keep the Qt event loop responsive without changing host environment."""
    import tempfile

    from PySide6.QtCore import QEventLoop, QProcess, QProcessEnvironment
    from PySide6.QtGui import QGuiApplication

    from haizflow.config import TMP_DIR

    application = QGuiApplication.instance()
    window = application.focusWindow() if application else None
    # A menu/tooltip may own focus while its native picker request is queued.
    # Modal ownership must stay with the persistent main window, not that popup.
    while window is not None and window.transientParent() is not None:
        window = window.transientParent()
    if window is None and application:
        window = next((item for item in application.topLevelWindows() if item.isVisible()), None)
    owner = int(parent.winId()) if parent is not None else int(window.winId()) if window else 0
    previous_state = window.windowState() if window else None
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
        try:
            # IModalWindow.Show owns native modality and restores its real
            # owner. Do not disable every Qt window across process boundaries.
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
            if window:
                try:
                    if previous_state is not None and window.windowState() != previous_state:
                        window.setWindowState(previous_state)
                    window.requestActivate()
                except RuntimeError:
                    pass  # Owner was closed during application shutdown.


def main(request_path: str) -> int:
    """Called before config, splash, single-instance IPC or worker imports."""
    request = json.loads(Path(request_path).read_text("utf-8"))
    result = dict(paths=[], selected_filter="", error="")
    try:
        if not __package__:
            # Isolated script invocation deliberately omits editable-install
            # .pth files; add only this checkout's known source root.
            sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from haizflow.desktop.windows_file_dialog import show
        result = show(request)
    except Exception as error:
        result["error"] = str(error)
    Path(request["result"]).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))

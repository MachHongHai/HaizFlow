"""Lightweight Windows startup feedback, independent of Qt and model imports."""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path


class StartupSplash:
    def __init__(self, *, language="vi", icon_path: Path | None = None):
        self.language = language
        self.icon_path = icon_path
        self._hwnd = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self.error = None
        self.status = self._text("Đang khởi động…", "Starting…")
        self._thread = None

    def _text(self, vi, en):
        return en if self.language == "en" else vi

    def show(self):
        if sys.platform == "win32" and self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True, name="startup-splash")
            self._thread.start()
            self._ready.wait(1)
        return self

    def opening_interface(self):
        self.status = self._text("Đang mở giao diện…", "Opening interface…")
        if self._hwnd:
            import ctypes
            ctypes.windll.user32.SetWindowTextW(self._hwnd, "HaizFlow — " + self.status)

    def close(self):
        self._stop.set()
        if self._hwnd:
            import ctypes
            ctypes.windll.user32.PostMessageW(self._hwnd, 0x0010, 0, 0)
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(2)

    def _run(self):
        try:
            self._window_loop()
        except Exception as exc:
            # Startup feedback must never prevent the application from opening.
            self.error = str(exc)
        finally:
            self._hwnd = None
            self._ready.set()

    def _window_loop(self):
        import ctypes as c
        from ctypes import wintypes as w

        user, gdi, kernel = c.windll.user32, c.windll.gdi32, c.windll.kernel32
        set_dpi_context = getattr(user, "SetThreadDpiAwarenessContext", None)
        if set_dpi_context is not None:
            set_dpi_context.argtypes, set_dpi_context.restype = [c.c_void_p], c.c_void_p
            set_dpi_context(c.c_void_p(-4))  # crisp text without changing Qt's main-thread DPI policy
        callback_type = c.WINFUNCTYPE(c.c_ssize_t, w.HWND, w.UINT, w.WPARAM, w.LPARAM)

        class WindowClass(c.Structure):
            _fields_ = [("style", w.UINT), ("proc", callback_type), ("extra", c.c_int),
                        ("window_extra", c.c_int), ("instance", w.HINSTANCE),
                        ("icon", w.HICON), ("cursor", w.HANDLE), ("brush", w.HBRUSH),
                        ("menu", w.LPCWSTR), ("name", w.LPCWSTR)]

        class Paint(c.Structure):
            _fields_ = [("dc", w.HDC), ("erase", w.BOOL), ("rect", w.RECT),
                        ("restore", w.BOOL), ("update", w.BOOL), ("reserved", c.c_byte * 32)]

        # Explicit pointer-sized signatures are essential in frozen x64 Python.
        signatures = [
            (kernel.GetModuleHandleW, [w.LPCWSTR], w.HMODULE),
            (user.DefWindowProcW, [w.HWND, w.UINT, w.WPARAM, w.LPARAM], c.c_ssize_t),
            (user.CreateWindowExW, [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
                                   c.c_int, c.c_int, c.c_int, c.c_int, w.HWND,
                                   w.HMENU, w.HINSTANCE, c.c_void_p], w.HWND),
            (user.BeginPaint, [w.HWND, c.POINTER(Paint)], w.HDC),
            (user.EndPaint, [w.HWND, c.POINTER(Paint)], w.BOOL),
            (user.FillRect, [w.HDC, c.POINTER(w.RECT), w.HBRUSH], c.c_int),
            (user.DrawTextW, [w.HDC, w.LPCWSTR, c.c_int, c.POINTER(w.RECT), w.UINT], c.c_int),
            (user.LoadImageW, [w.HINSTANCE, w.LPCWSTR, w.UINT, c.c_int, c.c_int, w.UINT], w.HANDLE),
            (user.DrawIconEx, [w.HDC, c.c_int, c.c_int, w.HICON, c.c_int, c.c_int,
                               w.UINT, w.HBRUSH, w.UINT], w.BOOL),
            (gdi.CreateSolidBrush, [w.DWORD], w.HBRUSH),
            (gdi.CreateFontW, [c.c_int] * 5 + [w.DWORD] * 8 + [w.LPCWSTR], w.HANDLE),
            (gdi.SelectObject, [w.HDC, w.HANDLE], w.HANDLE),
            (gdi.DeleteObject, [w.HANDLE], w.BOOL),
            (gdi.SetTextColor, [w.HDC, w.DWORD], w.DWORD),
            (gdi.SetBkMode, [w.HDC, c.c_int], c.c_int),
            (gdi.GetTextExtentPoint32W, [w.HDC, w.LPCWSTR, c.c_int, c.POINTER(w.SIZE)], w.BOOL),
            (gdi.CreateCompatibleDC, [w.HDC], w.HDC),
            (gdi.CreateCompatibleBitmap, [w.HDC, c.c_int, c.c_int], w.HBITMAP),
            (gdi.DeleteDC, [w.HDC], w.BOOL),
            (gdi.BitBlt, [w.HDC, c.c_int, c.c_int, c.c_int, c.c_int,
                         w.HDC, c.c_int, c.c_int, w.DWORD], w.BOOL),
        ]
        for function, arguments, result in signatures:
            function.argtypes, function.restype = arguments, result
        user.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
        user.SetWindowTextW.argtypes = [w.HWND, w.LPCWSTR]
        user.DestroyWindow.argtypes = [w.HWND]
        user.ShowWindow.argtypes = [w.HWND, c.c_int]
        user.UpdateWindow.argtypes = [w.HWND]
        user.InvalidateRect.argtypes = [w.HWND, c.c_void_p, w.BOOL]
        user.SetTimer.argtypes = [w.HWND, c.c_size_t, w.UINT, c.c_void_p]
        user.KillTimer.argtypes = [w.HWND, c.c_size_t]
        user.DestroyIcon.argtypes = [w.HICON]
        user.GetMessageW.argtypes = [c.POINTER(w.MSG), w.HWND, w.UINT, w.UINT]
        user.TranslateMessage.argtypes = [c.POINTER(w.MSG)]
        user.DispatchMessageW.argtypes = [c.POINTER(w.MSG)]
        user.RegisterClassW.argtypes = [c.POINTER(WindowClass)]
        user.UnregisterClassW.argtypes = [w.LPCWSTR, w.HINSTANCE]

        scale = getattr(user, "GetDpiForSystem", lambda: 96)() / 96
        px = lambda value: round(value * scale)
        width, height = px(500), px(280)
        color = lambda rgb: int(rgb[1:3], 16) | int(rgb[3:5], 16) << 8 | int(rgb[5:7], 16) << 16
        brushes = [gdi.CreateSolidBrush(color(value)) for value in ("#1B1A18", "#332F2A", "#C4915E", "#211F1C")]
        fonts = [gdi.CreateFontW(-px(size), 0, 0, 0, weight, 0, 0, 0, 1, 0, 0, 5, 0,
                                "Segoe UI") for size, weight in ((32, 600), (16, 400))]
        icon = user.LoadImageW(None, str(self.icon_path), 1, px(64), px(64), 0x10) if self.icon_path else None
        started = time.monotonic()
        animation = w.BOOL(True)
        user.SystemParametersInfoW(0x1042, 0, c.byref(animation), 0)

        def fill(dc, rect, brush):
            user.FillRect(dc, c.byref(w.RECT(*rect)), brush)

        @callback_type
        def procedure(hwnd, message, wp, lp):
            if message == 0x000F:
                paint = Paint()
                screen_dc = user.BeginPaint(hwnd, c.byref(paint))
                dc = gdi.CreateCompatibleDC(screen_dc)
                bitmap = gdi.CreateCompatibleBitmap(screen_dc, width, height)
                previous_bitmap = gdi.SelectObject(dc, bitmap)
                fill(dc, (0, 0, width, height), brushes[0])
                fill(dc, (0, 0, width, px(1)), brushes[1])
                fill(dc, (0, height - px(1), width, height), brushes[1])
                fill(dc, (0, 0, px(1), height), brushes[1])
                fill(dc, (width - px(1), 0, width, height), brushes[1])
                fill(dc, (px(1), px(1), width - px(1), px(4)), brushes[2])
                fill(dc, (px(1), px(220), width - px(1), height - px(1)), brushes[3])
                gdi.SetBkMode(dc, 1)
                if icon:
                    user.DrawIconEx(dc, (width - px(64)) // 2, px(36), icon, px(64), px(64), 0, None, 3)
                previous_font = gdi.SelectObject(dc, fonts[0])
                sizes = []
                for part in ("Haiz", "Flow"):
                    size = w.SIZE()
                    gdi.GetTextExtentPoint32W(dc, part, len(part), c.byref(size))
                    sizes.append(size.cx)
                wordmark_x = (width - sum(sizes)) // 2
                for part, part_width, shade in zip(("Haiz", "Flow"), sizes, ("#F2EFE9", "#C4915E")):
                    gdi.SetTextColor(dc, color(shade))
                    rect = w.RECT(wordmark_x, px(116), wordmark_x + part_width, px(158))
                    user.DrawTextW(dc, part, -1, c.byref(rect), 4 | 32)
                    wordmark_x += part_width
                gdi.SelectObject(dc, previous_font)
                for text, y, font, shade in ((self.status, 172, fonts[1], "#B8B1A6"),):
                    previous = gdi.SelectObject(dc, font)
                    gdi.SetTextColor(dc, color(shade))
                    rect = w.RECT(px(24), px(y), width - px(24), px(y + 38))
                    user.DrawTextW(dc, text, -1, c.byref(rect), 1 | 4 | 32)
                    gdi.SelectObject(dc, previous)
                left, right, top = px(64), width - px(64), px(248)
                fill(dc, (left, top, right, top + px(3)), brushes[1])
                segment = px(76)
                phase = ((time.monotonic() - started) / 1.8) % 1
                x = round(left - segment + phase * (right - left + segment)) if animation.value else left
                fill(dc, (max(left, x), top, min(right, x + segment), top + px(3)), brushes[2])
                gdi.BitBlt(screen_dc, 0, 0, width, height, dc, 0, 0, 0x00CC0020)
                gdi.SelectObject(dc, previous_bitmap)
                gdi.DeleteObject(bitmap)
                gdi.DeleteDC(dc)
                user.EndPaint(hwnd, c.byref(paint))
                return 0
            if message == 0x0014:
                return 1  # the back buffer paints the complete surface
            if message == 0x0113:
                if self._stop.is_set():
                    user.DestroyWindow(hwnd)
                else:
                    user.InvalidateRect(hwnd, None, False)
                return 0
            if message == 0x0010:
                user.DestroyWindow(hwnd)
                return 0
            if message == 0x0002:
                user.KillTimer(hwnd, 1)
                user.PostQuitMessage(0)
                return 0
            return user.DefWindowProcW(hwnd, message, wp, lp)

        instance = kernel.GetModuleHandleW(None)
        name = f"HaizFlowStartup-{id(self)}"
        window_class = WindowClass(0, procedure, 0, 0, instance, None, None, brushes[0], None, name)
        try:
            if not user.RegisterClassW(c.byref(window_class)):
                raise OSError("Could not register startup window")
            self._hwnd = user.CreateWindowExW(0x80, name, "HaizFlow — " + self.status, 0x80000000,
                (user.GetSystemMetrics(0) - width) // 2, (user.GetSystemMetrics(1) - height) // 2,
                width, height, None, None, instance, None)
            if not self._hwnd:
                raise OSError("Could not create startup window")
            user.SetTimer(self._hwnd, 1, 33, None)
            if not self._stop.is_set():
                user.ShowWindow(self._hwnd, 4)  # no activation or always-on-top stealing
                user.UpdateWindow(self._hwnd)
            self._ready.set()
            message = w.MSG()
            while user.GetMessageW(c.byref(message), None, 0, 0) > 0:
                user.TranslateMessage(c.byref(message))
                user.DispatchMessageW(c.byref(message))
        finally:
            user.UnregisterClassW(name, instance)
            if icon:
                user.DestroyIcon(icon)
            for handle in fonts + brushes:
                gdi.DeleteObject(handle)


def settings_language(path: Path) -> str:
    try:
        return "en" if json.loads(path.read_text(encoding="utf-8")).get("language") == "en" else "vi"
    except (OSError, ValueError, AttributeError):
        return "vi"


_active: StartupSplash | None = None


def start(*, settings_path: Path, icon_path: Path | None = None):
    global _active
    _active = StartupSplash(language=settings_language(settings_path), icon_path=icon_path).show()
    if _active._hwnd:
        os.environ["HAIZFLOW_STARTUP_SPLASH"] = "1"
    return _active


def finish():
    global _active
    if _active is not None:
        _active.close()
        _active = None
        os.environ.pop("HAIZFLOW_STARTUP_SPLASH", None)


def opening_interface():
    if _active is not None:
        _active.opening_interface()

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

        class Vertex(c.Structure):
            _fields_ = [("x", w.LONG), ("y", w.LONG), ("red", w.USHORT),
                        ("green", w.USHORT), ("blue", w.USHORT), ("alpha", w.USHORT)]

        class GradientRectangle(c.Structure):
            _fields_ = [("upper_left", w.ULONG), ("lower_right", w.ULONG)]

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
            (gdi.StretchBlt, [w.HDC, c.c_int, c.c_int, c.c_int, c.c_int,
                             w.HDC, c.c_int, c.c_int, c.c_int, c.c_int, w.DWORD], w.BOOL),
            (gdi.SetStretchBltMode, [w.HDC, c.c_int], c.c_int),
            (gdi.CreateRoundRectRgn, [c.c_int] * 6, w.HANDLE),
            (gdi.SelectClipRgn, [w.HDC, w.HANDLE], c.c_int),
        ]
        for function, arguments, result in signatures:
            function.argtypes, function.restype = arguments, result
        gradient_fill = c.windll.msimg32.GradientFill
        gradient_fill.argtypes = [w.HDC, c.POINTER(Vertex), w.ULONG,
                                  c.POINTER(GradientRectangle), w.ULONG, w.ULONG]
        gradient_fill.restype = w.BOOL
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
        width, height = px(600), px(338)
        color = lambda rgb: int(rgb[1:3], 16) | int(rgb[3:5], 16) << 8 | int(rgb[5:7], 16) << 16
        brushes = [gdi.CreateSolidBrush(color(value)) for value in ("#100C09", "#37251B")]
        font_family = "Segoe UI Variable" if (Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/SegUIVar.ttf").is_file() else "Segoe UI"
        fonts = [gdi.CreateFontW(-px(size), 0, 0, 0, weight, 0, 0, 0, 1, 0, 0, 5, 0,
                                font_family) for size, weight in ((40, 600), (16, 400))]
        artwork_path = self.icon_path.with_name("startup-splash.bmp") if self.icon_path else None
        background_bitmap = user.LoadImageW(None, str(artwork_path), 0, 0, 0, 0x2010) if artwork_path and artwork_path.is_file() else None
        background_dc = gdi.CreateCompatibleDC(None) if background_bitmap else None
        previous_background = gdi.SelectObject(background_dc, background_bitmap) if background_dc else None
        icon = user.LoadImageW(None, str(self.icon_path), 1, px(98), px(98), 0x10) if self.icon_path and not background_bitmap else None
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
                if background_dc:
                    gdi.SetStretchBltMode(dc, 4)  # HALFTONE; the bitmap is prepared at 2x DPI
                    gdi.StretchBlt(dc, 0, 0, width, height, background_dc, 0, 0, 1200, 676, 0x00CC0020)
                gdi.SetBkMode(dc, 1)
                if icon:
                    left = (width - px(98)) // 2
                    clip = gdi.CreateRoundRectRgn(left, px(71), left + px(98), px(169), px(38), px(38))
                    gdi.SelectClipRgn(dc, clip)
                    user.DrawIconEx(dc, left, px(71), icon, px(98), px(98), 0, None, 3)
                    gdi.SelectClipRgn(dc, None)
                    gdi.DeleteObject(clip)
                previous_font = gdi.SelectObject(dc, fonts[0])
                sizes = []
                for part in ("Haiz", "Flow"):
                    size = w.SIZE()
                    gdi.GetTextExtentPoint32W(dc, part, len(part), c.byref(size))
                    sizes.append(size.cx)
                wordmark_x = (width - sum(sizes)) // 2
                for part, part_width, shade in zip(("Haiz", "Flow"), sizes, ("#F6F4EF", "#FFB65D")):
                    gdi.SetTextColor(dc, color(shade))
                    rect = w.RECT(wordmark_x, px(174), wordmark_x + part_width, px(223))
                    user.DrawTextW(dc, part, -1, c.byref(rect), 4 | 32)
                    wordmark_x += part_width
                gdi.SelectObject(dc, previous_font)
                for text, y, font, shade in ((self.status, 221, fonts[1], "#DED2C4"),):
                    previous = gdi.SelectObject(dc, font)
                    gdi.SetTextColor(dc, color(shade))
                    rect = w.RECT(px(24), px(y), width - px(24), px(y + 38))
                    user.DrawTextW(dc, text, -1, c.byref(rect), 1 | 4 | 32)
                    gdi.SelectObject(dc, previous)
                left, right, top, bottom = px(168), px(432), px(260.5), px(265.5)
                if not background_dc:
                    fill(dc, (left, top, right, bottom), brushes[1])
                segment = px(112)
                phase = ((time.monotonic() - started) / 2.2) % 1
                x = round(left - segment + phase * (right - left + segment)) if animation.value else (left + right - segment) // 2
                clip = gdi.CreateRoundRectRgn(left, top, right + 1, bottom + 1, px(5), px(5))
                gdi.SelectClipRgn(dc, clip)
                vertices = (Vertex * 2)(Vertex(x, top, 0xFFFF, 0x6C6C, 0x2626, 0),
                                        Vertex(x + segment, bottom, 0xFFFF, 0xE0E0, 0xA0A0, 0))
                gradient = GradientRectangle(0, 1)
                gradient_fill(dc, vertices, 2, c.byref(gradient), 1, 0)
                gdi.SelectClipRgn(dc, None)
                gdi.DeleteObject(clip)
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
            if background_dc:
                gdi.SelectObject(background_dc, previous_background)
                gdi.DeleteObject(background_bitmap)
                gdi.DeleteDC(background_dc)
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

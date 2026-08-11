"""Open web links in the Chrome profile the user is already using on Windows."""

from __future__ import annotations

import ctypes
import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from urllib.parse import urlsplit

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


LOGGER = logging.getLogger(__name__)
_CHROME_OPTION_PATTERN = re.compile(
    r'"--(?P<wrapped_name>user-data-dir|profile-directory)=(?P<wrapped_value>[^\"]*)"'
    r"|--(?P<name>user-data-dir|profile-directory)(?:=|\s+)"
    r'(?:"(?P<quoted>[^\"]+)"|(?P<bare>\S+))',
    re.IGNORECASE,
)
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_VT_LPWSTR = 31


class _Guid(ctypes.Structure):
    _fields_ = (
        ("data1", ctypes.c_ulong),
        ("data2", ctypes.c_ushort),
        ("data3", ctypes.c_ushort),
        ("data4", ctypes.c_ubyte * 8),
    )


class _PropertyKey(ctypes.Structure):
    _fields_ = (("format_id", _Guid), ("property_id", ctypes.c_ulong))


class _PropertyValueUnion(ctypes.Union):
    _fields_ = (("wide_string", ctypes.c_wchar_p), ("unsigned_value", ctypes.c_ulonglong))


class _PropertyValue(ctypes.Structure):
    _anonymous_ = ("value",)
    _fields_ = (
        ("value_type", ctypes.c_ushort),
        ("reserved1", ctypes.c_ushort),
        ("reserved2", ctypes.c_ushort),
        ("reserved3", ctypes.c_ushort),
        ("value", _PropertyValueUnion),
    )


_PROPERTY_STORE_INTERFACE_ID = _Guid(
    0x886D8EEB,
    0x8CF2,
    0x4446,
    (ctypes.c_ubyte * 8)(0x8D, 0x02, 0xCD, 0xBA, 0x1D, 0xBD, 0xCF, 0x99),
)
_APP_MODEL_FORMAT_ID = _Guid(
    0x9F4C2855,
    0x9F79,
    0x4B39,
    (ctypes.c_ubyte * 8)(0xA8, 0xD0, 0xE1, 0xD4, 0x2D, 0xE1, 0xD5, 0xF3),
)
_APP_MODEL_RELAUNCH_COMMAND = _PropertyKey(_APP_MODEL_FORMAT_ID, 2)


@dataclass(frozen=True)
class ChromeLaunch:
    executable: str
    user_data_dir: str = ""
    profile_directory: str = ""


def active_chrome_profile() -> dict[str, str]:
    """Return the most recently active visible Chrome profile without reading browser data."""
    launch = _active_chrome_launch() if os.name == "nt" else None
    if launch is None:
        return {}
    return {
        "executable": launch.executable,
        "user_data_dir": launch.user_data_dir,
        "profile_directory": launch.profile_directory,
    }


def open_external_url(value: str, preferred_chrome_profile: dict[str, str] | None = None) -> bool:
    """Open an HTTP(S) URL in an existing Chrome profile when one is available."""
    url = str(value or "").strip()
    parsed = urlsplit(url)
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
        try:
            chrome = _validated_chrome_launch(preferred_chrome_profile)
            if chrome is None:
                chrome = _active_chrome_launch() if os.name == "nt" else None
        except (OSError, ValueError, ctypes.ArgumentError):
            chrome = None
            LOGGER.warning("Could not resolve the active Chrome profile", exc_info=True)
        if chrome is not None:
            command = [chrome.executable]
            if chrome.user_data_dir:
                command.append(f"--user-data-dir={chrome.user_data_dir}")
            if chrome.profile_directory:
                command.append(f"--profile-directory={chrome.profile_directory}")
            command.extend(("--new-tab", url))
            try:
                subprocess.Popen(command, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                return True
            except OSError:
                LOGGER.warning("Could not open link in the active Chrome profile", exc_info=True)
    try:
        if QDesktopServices.openUrl(QUrl(url)):
            return True
    except RuntimeError:
        LOGGER.warning("Qt could not open the external link", exc_info=True)
    return _shell_open_url(url) if os.name == "nt" else False


def _shell_open_url(url: str) -> bool:
    """Last-resort Windows shell open when Qt has no URL handler."""
    try:
        shell_execute = ctypes.windll.shell32.ShellExecuteW
        shell_execute.argtypes = [
            ctypes.c_void_p,
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_int,
        ]
        shell_execute.restype = ctypes.c_void_p
        result = shell_execute(None, "open", url, None, None, 1)
        return int(result or 0) > 32
    except (AttributeError, OSError, TypeError, ValueError):
        LOGGER.warning("Windows could not open the external link", exc_info=True)
        return False


def _validated_chrome_launch(profile: dict[str, str] | None) -> ChromeLaunch | None:
    if not isinstance(profile, dict):
        return None
    executable = os.path.abspath(str(profile.get("executable") or ""))
    if not executable or os.path.basename(executable).casefold() != "chrome.exe" or not os.path.isfile(executable):
        return None
    return ChromeLaunch(
        executable=executable,
        user_data_dir=str(profile.get("user_data_dir") or ""),
        profile_directory=str(profile.get("profile_directory") or ""),
    )


def _active_chrome_launch() -> ChromeLaunch | None:
    chrome_windows = _visible_chrome_windows()
    if not chrome_windows:
        return None

    # Chrome places the exact profile directory in each top-level window's
    # Windows relaunch metadata. This remains accurate when one browser
    # process owns windows from several Chrome profiles.
    for window_handle, process_id in chrome_windows:
        executable = _process_executable_path(process_id)
        relaunch_command = _window_relaunch_command(window_handle)
        if executable and relaunch_command:
            return _launch_from_command_line(executable, relaunch_command)

    # Older Chrome builds may not expose relaunch metadata. Retain the process
    # command-line fallback, but do not let it override per-window metadata.
    records = _chrome_process_records()
    by_process_id = {
        int(record.get("ProcessId") or 0): record
        for record in records
        if isinstance(record, dict) and record.get("ProcessId")
    }
    for _window_handle, process_id in chrome_windows:
        record = by_process_id.get(process_id)
        if record is None:
            continue
        command_line = str(record.get("CommandLine") or "")
        if "--type=" in command_line.lower():
            continue
        executable = str(record.get("ExecutablePath") or "")
        if executable and os.path.isfile(executable):
            return _launch_from_command_line(executable, command_line)
    return None


def _launch_from_command_line(executable: str, command_line: str) -> ChromeLaunch:
    options = {}
    for match in _CHROME_OPTION_PATTERN.finditer(command_line):
        name = match.group("wrapped_name") or match.group("name") or ""
        value = match.group("wrapped_value")
        if value is None:
            value = match.group("quoted") or match.group("bare") or ""
        options[name.lower()] = value
    return ChromeLaunch(
        executable=executable,
        user_data_dir=options.get("user-data-dir", ""),
        profile_directory=options.get("profile-directory", ""),
    )


def _chrome_process_records() -> list[dict]:
    powershell = shutil.which("powershell.exe") or "powershell.exe"
    script = (
        "$ErrorActionPreference = 'Stop'; "
        "Get-CimInstance Win32_Process -Filter \"Name = 'chrome.exe'\" | "
        "Select-Object ProcessId, ExecutablePath, CommandLine | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            encoding="utf-8",
            errors="replace",
            timeout=2.0,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        decoded = json.loads(result.stdout)
        return decoded if isinstance(decoded, list) else [decoded]
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return []


def _visible_chrome_windows() -> list[tuple[int, int]]:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    windows: list[tuple[int, int]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def enumerate_window(window_handle, _parameter):
        if not user32.IsWindowVisible(window_handle) or not user32.GetWindowTextLengthW(window_handle):
            return True
        process_id = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(window_handle, ctypes.byref(process_id))
        if process_id.value and _process_executable_name(kernel32, process_id.value) == "chrome.exe":
            windows.append((int(window_handle), process_id.value))
        return True

    user32.EnumWindows(enumerate_window, 0)
    return windows


def _window_relaunch_command(window_handle: int) -> str:
    shell32 = ctypes.windll.shell32
    ole32 = ctypes.windll.ole32
    property_store = ctypes.c_void_p()
    shell32.SHGetPropertyStoreForWindow.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(_Guid),
        ctypes.POINTER(ctypes.c_void_p),
    )
    shell32.SHGetPropertyStoreForWindow.restype = ctypes.c_long
    result = shell32.SHGetPropertyStoreForWindow(
        ctypes.c_void_p(window_handle),
        ctypes.byref(_PROPERTY_STORE_INTERFACE_ID),
        ctypes.byref(property_store),
    )
    if result < 0 or not property_store.value:
        return ""
    value = _PropertyValue()
    try:
        virtual_table = ctypes.cast(
            property_store,
            ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)),
        ).contents
        get_value = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_void_p,
            ctypes.POINTER(_PropertyKey),
            ctypes.POINTER(_PropertyValue),
        )(virtual_table[5])
        result = get_value(
            property_store,
            ctypes.byref(_APP_MODEL_RELAUNCH_COMMAND),
            ctypes.byref(value),
        )
        if result >= 0 and value.value_type == _VT_LPWSTR and value.wide_string:
            return value.wide_string
        return ""
    finally:
        ole32.PropVariantClear(ctypes.byref(value))
        release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(virtual_table[2])
        release(property_store)


def _process_executable_path(process_id: int) -> str:
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, process_id)
    if not handle:
        return ""
    try:
        size = ctypes.c_ulong(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


def _process_executable_name(kernel32, process_id: int) -> str:
    del kernel32
    return os.path.basename(_process_executable_path(process_id)).lower()

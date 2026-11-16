"""Windows Common Item Dialog, with the real host HWND and Shell known folders.

Only the clean-profile picker process imports this module. No hidden Qt owner,
portable home folder, system preference changes, or Explorer registry writes.
"""
import ctypes
import re
import uuid
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path


class GUID(ctypes.Structure):
    _fields_ = [("data1", wintypes.DWORD), ("data2", wintypes.WORD),
                ("data3", wintypes.WORD), ("data4", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


_ITEM_IID = "43826d1e-e718-42ee-bc55-a1e261c37bfe"
_FOLDERS = (
    "374de290-123f-4565-9164-39c4925e467b",  # Downloads
    "b4bfcc3a-db2c-424c-b029-7fe99a87c641",  # Desktop
    "fdd39ad0-238f-46af-adb4-6c85480369c7",  # Documents (including OneDrive relocation)
    "18989b1d-99b5-455b-841c-ab7c74e4ddfc",  # Videos
    "33e28130-4e1e-4676-835a-98395c3bc3bb",  # Pictures
)


def name_filters(value):
    rows = []
    for text in str(value or "").split(";;"):
        match = re.fullmatch(r"\s*(.*?)\s*\(([^()]*)\)\s*", text)
        if match:
            patterns = ";".join(match[2].split())
            if patterns:
                rows.append((text.strip(), match[1].strip(), patterns))
    return rows


def dialog_options(kind, qt_options=0):
    options = 0x40 | 0x8 | 0x800  # FORCEFILESYSTEM, NOCHANGEDIR, PATHMUSTEXIST
    if kind == "folder":
        options |= 0x20  # PICKFOLDERS
    elif kind in {"open", "multiple"}:
        options |= 0x1000  # FILEMUSTEXIST
    elif kind == "save":
        if not qt_options & 4:  # QFileDialog.DontConfirmOverwrite
            options |= 0x2  # OVERWRITEPROMPT
    else:
        raise ValueError("Unsupported native picker operation")
    if kind == "multiple":
        options |= 0x200
    return options


def _call(pointer, index, *arguments):
    """arguments are (ctype, value) pairs; COM vtables include IUnknown slots."""
    table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    method = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p, *(kind for kind, _ in arguments))(table[index])
    return method(pointer, *(value for _, value in arguments))


def _check(status, operation):
    if status < 0:
        raise OSError(f"Windows {operation} failed (HRESULT 0x{status & 0xffffffff:08X})")


def _release(pointer):
    if pointer:
        _call(pointer, 2)


@contextmanager
def _per_monitor_dpi():
    """Render at monitor DPI, not a blurry Windows-scaled 96-DPI bitmap.

    The stdlib-only picker no longer gets Qt's DPI initialization. Set the
    process default before COM creates any HWND; a frozen EXE manifest may
    already own that default, so also scope the actual UI thread explicitly.
    """
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
    user.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    context = ctypes.c_void_p(-4)  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
    if not user.SetProcessDpiAwarenessContext(context):
        status = ctypes.get_last_error()
        if status != 5:  # ERROR_ACCESS_DENIED: the manifest already set a default.
            raise ctypes.WinError(status)
    previous = user.SetThreadDpiAwarenessContext(context)
    if not previous:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield
    finally:
        user.SetThreadDpiAwarenessContext(previous)


def show(request):
    dialog_options(request["kind"], int(request.get("options") or 0))
    with _per_monitor_dpi():
        return _show_dialog(request)


def _show_dialog(request):
    kind = request["kind"]
    options = dialog_options(kind, int(request.get("options") or 0))
    ole = ctypes.WinDLL("ole32", use_last_error=True)
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p, wintypes.DWORD,
                                    ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    shell.SHCreateItemFromParsingName.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p,
        ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
    shell.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE,
                                          ctypes.POINTER(ctypes.c_void_p)]
    _check(ole.CoInitializeEx(None, 2 | 4), "COM initialization")
    dialog = ctypes.c_void_p()
    item_iid = GUID.parse(_ITEM_IID)

    def shell_item(path):
        item = ctypes.c_void_p()
        status = shell.SHCreateItemFromParsingName(str(path), None, ctypes.byref(item_iid), ctypes.byref(item))
        return item if status >= 0 else None

    def item_path(item):
        result = ctypes.c_void_p()
        _check(_call(item, 5, (wintypes.DWORD, 0x80058000),
                     (ctypes.POINTER(ctypes.c_void_p), ctypes.byref(result))), "selected path")
        try:
            return ctypes.wstring_at(result)
        finally:
            ole.CoTaskMemFree(result)

    try:
        save = kind == "save"
        clsid = GUID.parse("c0b4e2f3-ba21-4773-8dba-335ec946eb8b" if save else "dc1c5a9c-e88a-4dde-a5a1-60f82a20aef7")
        iid = GUID.parse("84bccd23-5fde-4cdb-aea4-af64b83d78ab" if save else "d57c7288-d4ad-4768-be02-9d969532d960")
        _check(ole.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(dialog)),
               "file dialog creation")
        _check(_call(dialog, 9, (wintypes.DWORD, options)), "dialog options")
        _check(_call(dialog, 17, (wintypes.LPCWSTR, str(request.get("caption") or "HaizFlow"))), "dialog title")
        known_paths = []
        for value in _FOLDERS:
            location = ctypes.c_void_p()
            if shell.SHGetKnownFolderPath(ctypes.byref(GUID.parse(value)), 0, None, ctypes.byref(location)) < 0:
                continue
            try:
                path = ctypes.wstring_at(location)
            finally:
                ole.CoTaskMemFree(location)
            known_paths.append(path)
        # Keep Windows' own navigation pane and Quick Access intact. AddPlace
        # creates an application group ("Python" in development), not normal
        # pinned folders, and can scroll familiar locations out of view.
        directory = Path(str(request.get("directory") or ""))
        if str(request.get("directory") or "") and not directory.is_dir():
            if save:
                _check(_call(dialog, 15, (wintypes.LPCWSTR, directory.name)), "default file name")
            directory = directory.parent
        if (not request.get("directory") or not directory.is_dir()) and known_paths:
            directory = Path(known_paths[0])
        item = shell_item(directory)
        if item:
            try:
                _check(_call(dialog, 12, (ctypes.c_void_p, item)), "initial folder")
            finally:
                _release(item)
        filters = name_filters(request.get("name_filter")) if kind != "folder" else []
        if filters:
            class Filter(ctypes.Structure):
                _fields_ = [("label", wintypes.LPCWSTR), ("patterns", wintypes.LPCWSTR)]
            specs = (Filter * len(filters))(*(Filter(label, patterns) for _, label, patterns in filters))
            _check(_call(dialog, 4, (wintypes.UINT, len(filters)), (ctypes.POINTER(Filter), specs)), "file filters")
            selected = next((i + 1 for i, row in enumerate(filters) if row[0] == request.get("selected_filter")), 1)
            _check(_call(dialog, 5, (wintypes.UINT, selected)), "selected filter")
            extension = re.match(r"\*\.([a-zA-Z0-9]+)(?:;|$)", filters[selected - 1][2])
            if save and extension:
                _check(_call(dialog, 22, (wintypes.LPCWSTR, extension[1])), "file extension")
        owner = int(request.get("owner") or 0)
        status = _call(dialog, 3, (wintypes.HWND, owner))
        if status & 0xffffffff == 0x800704C7:  # ERROR_CANCELLED, including the X button
            return {"paths": [], "selected_filter": "", "error": ""}
        _check(status, "file selection")
        paths = []
        if kind == "multiple":
            items, count = ctypes.c_void_p(), wintypes.DWORD()
            _check(_call(dialog, 27, (ctypes.POINTER(ctypes.c_void_p), ctypes.byref(items))), "selected files")
            try:
                _check(_call(items, 7, (ctypes.POINTER(wintypes.DWORD), ctypes.byref(count))), "selected file count")
                for index in range(count.value):
                    item = ctypes.c_void_p()
                    _check(_call(items, 8, (wintypes.DWORD, index),
                                 (ctypes.POINTER(ctypes.c_void_p), ctypes.byref(item))), "selected item")
                    try:
                        paths.append(item_path(item))
                    finally:
                        _release(item)
            finally:
                _release(items)
        else:
            item = ctypes.c_void_p()
            _check(_call(dialog, 20, (ctypes.POINTER(ctypes.c_void_p), ctypes.byref(item))), "selected item")
            try:
                paths.append(item_path(item))
            finally:
                _release(item)
        selected_filter = ""
        if filters:
            selected = wintypes.UINT()
            _check(_call(dialog, 6, (ctypes.POINTER(wintypes.UINT), ctypes.byref(selected))), "chosen file filter")
            if 1 <= selected.value <= len(filters):
                selected_filter = filters[selected.value - 1][0]
        return {"paths": paths, "selected_filter": selected_filter, "error": ""}
    finally:
        _release(dialog)
        ole.CoUninitialize()

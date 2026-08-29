"""Localized wrappers for native Qt dialogs.

QML owns visible application copy; this module keeps native file and message
dialogs aligned with the persisted UI language.
"""

import os
import re
from contextlib import contextmanager
from pathlib import Path

from PySide6.QtWidgets import QFileDialog as QtFileDialog, QMessageBox as QtMessageBox

from haizflow.config import NATIVE_WINDOWS_USERPROFILE
from haizflow.core.paths import app_data_dir

_UI_LANGUAGE = "en"


@contextmanager
def _native_explorer_profile():
    """Expose Windows' actual profile only while its native picker is open."""
    profile = NATIVE_WINDOWS_USERPROFILE
    if not profile or not Path(profile).is_dir():
        yield
        return
    previous = {key: os.environ.get(key) for key in ("USERPROFILE", "HOMEDRIVE", "HOMEPATH")}
    drive, tail = os.path.splitdrive(profile)
    os.environ["USERPROFILE"] = profile
    os.environ["HOMEDRIVE"] = drive
    os.environ["HOMEPATH"] = tail or "\\"
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _set_ui_language(language: str) -> None:
    global _UI_LANGUAGE
    _UI_LANGUAGE = "vi" if language == "vi" else "en"


def _ui_text(value) -> str:
    text = str(value)
    if _UI_LANGUAGE != "vi":
        return text

    translations = {
        "Replace video": "Thay video",
        "Invalid video": "Video không hợp lệ",
        "Unsupported file": "Tệp không được hỗ trợ",
        "Project name": "Tên dự án",
        "Project storage location": "Vị trí lưu dự án",
        "Processing device": "Thiết bị xử lý",
        "Settings": "Cài đặt",
        "Import video": "Nhập video",
        "Channel import": "Nhập video từ kênh",
        "Some videos were skipped": "Một số video đã bị bỏ qua",
        "Batch delete incomplete": "Chưa xóa hết dự án hàng loạt",
        "No supported videos": "Không có video được hỗ trợ",
        "Batch queue": "Hàng đợi xử lý",
        "Batch settings": "Thiết lập hàng loạt",
        "Stop batch": "Dừng hàng đợi",
        "Missing video": "Thiếu video",
        "Cannot start project": "Không thể bắt đầu dự án",
        "Cannot create project": "Không thể tạo dự án",
        "Pause video": "Tạm dừng video",
        "Restart video": "Chạy lại video",
        "Translation review": "Duyệt bản dịch",
        "No video selected": "Chưa chọn video",
        "Remove video": "Xóa video",
        "Delete failed": "Xóa không thành công",
        "Already removed": "Đã xóa",
        "Project folder": "Thư mục dự án",
        "Delete project": "Xóa dự án",
        "GPU mode requires AC power for stable processing. Connect the charger and try again.": "Chế độ GPU cần cắm sạc để xử lý ổn định. Hãy cắm sạc rồi thử lại.",
        "Open input video": "Mở video nguồn",
        "Open output": "Mở video đầu ra",
        "Open export folder": "Mở thư mục video xuất",
        "Export diagnostics": "Xuất dữ liệu chẩn đoán",
        "Choose input video": "Chọn video nguồn",
        "Choose project storage location": "Chọn vị trí lưu dự án",
        "Choose videos for batch processing": "Chọn video để xử lý hàng loạt",
        "Choose a folder of videos for batch processing": "Chọn thư mục video để xử lý hàng loạt",
        "Choose cookies.txt": "Chọn cookies.txt",
        "Video files (*.mp4 *.mov *.mkv);;All files (*.*)": "Tệp video (*.mp4 *.mov *.mkv);;Tất cả tệp (*.*)",
        "Netscape cookie files (*.txt);;All files (*.*)": "Tệp cookie Netscape (*.txt);;Tất cả tệp (*.*)",
        "ZIP archives (*.zip)": "Tệp ZIP (*.zip)",
        "Pause or finish this video before replacing it.": "Hãy tạm dừng hoặc hoàn tất video này trước khi thay thế.",
        "Choose an MP4, MOV, or MKV video file.": "Hãy chọn tệp video MP4, MOV hoặc MKV.",
        "Enter a project name.": "Hãy nhập tên dự án.",
        "Choose a location for this project.": "Hãy chọn vị trí lưu dự án này.",
        "Wait for the current processing task to finish before changing device.": "Hãy chờ tác vụ hiện tại hoàn tất trước khi đổi thiết bị xử lý.",
        "Wait for the current processing task to finish before resetting the device setting.": "Hãy chờ tác vụ hiện tại hoàn tất trước khi khôi phục thiết bị xử lý mặc định.",
        "Wait for the processing device to finish switching before restarting.": "Hãy chờ thiết bị xử lý chuyển xong trước khi chạy lại.",
        "The dropped file is unavailable.": "Tệp được kéo thả không khả dụng.",
        "Choose MP4, MOV, or MKV video files.": "Hãy chọn các tệp video MP4, MOV hoặc MKV.",
        "Add at least one video to the queue.": "Hãy thêm ít nhất một video vào hàng đợi.",
        "These videos are already waiting or processing.": "Các video này đã có trong hàng đợi hoặc đang được xử lý.",
        "Add at least one video before applying settings.": "Hãy thêm ít nhất một video trước khi áp dụng thiết lập.",
        "Stop the active video and cancel the remaining queue?": "Dừng video đang chạy và hủy các video còn lại trong hàng đợi?",
        "Please choose an input video.": "Hãy chọn video nguồn.",
        "Pause this video? You can resume it later from Projects.": "Tạm dừng video này? Bạn có thể tiếp tục lại từ Dự án.",
        "Apply the current dubbing setup and restart this project?": "Áp dụng thiết lập lồng tiếng hiện tại và chạy lại dự án này?",
        "Select a video in this batch first.": "Hãy chọn một video trong dự án hàng loạt trước.",
        "Video data was already removed.": "Dữ liệu video đã được xóa.",
        "This project's folder is not available yet.": "Thư mục của dự án này chưa khả dụng.",
        "Select a project first.": "Hãy chọn một dự án trước.",
        "Choose an input video before opening the preview editor.": "Hãy chọn video nguồn trước khi mở trình chỉnh khung phụ đề.",
        "Add at least one video before editing subtitles.": "Hãy thêm ít nhất một video trước khi chỉnh phụ đề.",
        "Input video is not available yet.": "Video nguồn chưa khả dụng.",
        "Final video is not available yet.": "Video đầu ra chưa khả dụng.",
        "The export folder is not available yet.": "Thư mục video xuất chưa khả dụng.",
        "The destination project no longer exists.": "Dự án đích không còn tồn tại.",
        "Open or create a batch project before importing a channel.": "Hãy mở hoặc tạo một dự án hàng loạt trước khi nhập video từ kênh.",
        "Channel import is still stopping. Try deleting the project again in a moment.": "Tiến trình nhập từ kênh vẫn đang dừng. Hãy thử xóa lại dự án sau giây lát.",
    }
    if text in translations:
        return translations[text]

    replacements = (
        ("Cannot create the project at this location: ", "Không thể tạo dự án tại vị trí này: "),
        ("Cannot save settings: ", "Không thể lưu cài đặt: "),
        ("Cannot restore defaults: ", "Không thể khôi phục cài đặt mặc định: "),
        ("Cannot export diagnostics: ", "Không thể xuất dữ liệu chẩn đoán: "),
        (
            "A redacted diagnostics archive was created. It excludes project media, project names, and project logs.",
            "Đã tạo gói chẩn đoán được ẩn thông tin nhạy cảm. Gói này không chứa video, tên dự án hoặc nhật ký dự án.",
        ),
        ("GPU mode requires at least ", "Chế độ GPU cần ít nhất "),
        ("CPU mode requires approximately ", "Chế độ CPU cần khoảng "),
        ("CUDA-compatible NVIDIA GPU was not detected.", "Không phát hiện GPU NVIDIA tương thích CUDA."),
        ("Automatic mode will use the CPU because a compatible GPU is unavailable.", "Chế độ tự động sẽ dùng CPU vì không có GPU tương thích."),
        ("This computer does not meet the minimum CPU or GPU memory requirement.", "Máy không đáp ứng yêu cầu bộ nhớ tối thiểu của CPU hoặc GPU."),
    )
    for source, translated in replacements:
        if text.startswith(source):
            return translated + text[len(source):]
        if text == source:
            return translated

    skipped = re.match(r"^(\d+) unsupported or unreadable item\(s\):(.*)$", text, re.DOTALL)
    if skipped:
        return f"{skipped.group(1)} mục không được hỗ trợ hoặc không thể đọc:{skipped.group(2)}"
    return text


def _existing_dialog_directory(directory: str) -> str:
    """Return an existing, HaizFlow-owned fallback for native file dialogs.

    Passing an empty location makes the Windows native picker ask for the
    user's Desktop.  HaizFlow redirects USERPROFILE to its portable runtime
    so third-party caches cannot write to C:, therefore that Desktop must not
    be an implicit dependency of a media picker.
    """
    if directory:
        candidate = Path(directory).expanduser()
        if candidate.is_dir():
            return str(candidate.resolve())
    fallback = app_data_dir()
    fallback.mkdir(parents=True, exist_ok=True)
    return str(fallback.resolve())


def native_media_dialog_directory() -> str:
    """Return the real Windows Downloads folder for read-only media browsing.

    HaizFlow redirects its process profile so models and third-party caches
    stay under the installer-selected runtime.  That must not hide the user's
    regular Explorer folders when they are *selecting* an existing source.
    """
    profile = Path(NATIVE_WINDOWS_USERPROFILE).expanduser()
    if profile.is_dir():
        for name in ("Downloads", "Videos", "Desktop", "Documents"):
            candidate = profile / name
            if candidate.is_dir():
                return str(candidate.resolve())
        return str(profile.resolve())
    return ""


def _native_windows_folder_dialog(caption: str, directory: str) -> tuple[bool, str]:
    """Open Windows' modern Explorer folder picker.

    Qt's static directory helper can fall back to the legacy tree-only folder
    browser on some Windows/Qt combinations.  IFileOpenDialog with
    FOS_PICKFOLDERS keeps the normal Explorer navigation pane and known user
    locations.  The boolean indicates whether the native implementation was
    available; cancellation is represented by an empty path.
    """
    if os.name != "nt":
        return False, ""

    import ctypes
    import uuid
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_uint32),
            ("Data2", ctypes.c_uint16),
            ("Data3", ctypes.c_uint16),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    def guid(value: str) -> GUID:
        parsed = uuid.UUID(value)
        return GUID(
            parsed.time_low,
            parsed.time_mid,
            parsed.time_hi_version,
            (ctypes.c_ubyte * 8)(*parsed.bytes[8:]),
        )

    def com_method(instance, index: int, result_type, *argument_types):
        vtable = ctypes.cast(instance, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(result_type, ctypes.c_void_p, *argument_types)(vtable[index])

    ole32 = ctypes.OleDLL("ole32")
    shell32 = ctypes.OleDLL("shell32")
    clsid_file_open_dialog = guid("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")
    iid_file_open_dialog = guid("D57C7288-D4AD-4768-BE02-9D969532D960")
    iid_shell_item = guid("43826D1E-E718-42EE-BC55-A1E261C37BFE")
    dialog = ctypes.c_void_p()
    initialized = False

    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    ole32.CoInitializeEx.restype = ctypes.c_long
    initialize_result = ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
    if initialize_result in (0, 1):
        initialized = True
    elif initialize_result != ctypes.c_long(0x80010106).value:  # RPC_E_CHANGED_MODE
        return False, ""

    try:
        ole32.CoCreateInstance.argtypes = [
            ctypes.POINTER(GUID), ctypes.c_void_p, ctypes.c_uint32,
            ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p),
        ]
        ole32.CoCreateInstance.restype = ctypes.c_long
        result = ole32.CoCreateInstance(
            ctypes.byref(clsid_file_open_dialog), None, 0x1,
            ctypes.byref(iid_file_open_dialog), ctypes.byref(dialog),
        )
        if result < 0 or not dialog.value:
            return False, ""

        release_dialog = com_method(dialog, 2, ctypes.c_ulong)
        get_options = com_method(dialog, 10, ctypes.c_long, ctypes.POINTER(ctypes.c_uint32))
        set_options = com_method(dialog, 9, ctypes.c_long, ctypes.c_uint32)
        set_folder = com_method(dialog, 12, ctypes.c_long, ctypes.c_void_p)
        set_title = com_method(dialog, 17, ctypes.c_long, ctypes.c_wchar_p)
        show = com_method(dialog, 3, ctypes.c_long, wintypes.HWND)
        get_result = com_method(dialog, 20, ctypes.c_long, ctypes.POINTER(ctypes.c_void_p))

        try:
            options = ctypes.c_uint32()
            if get_options(dialog, ctypes.byref(options)) >= 0:
                # PICKFOLDERS | FORCEFILESYSTEM | PATHMUSTEXIST | NOCHANGEDIR
                set_options(dialog, options.value | 0x20 | 0x40 | 0x800 | 0x8)
            set_title(dialog, str(caption or ""))

            initial_shell_item = ctypes.c_void_p()
            initial_path = Path(directory).expanduser() if directory else None
            if initial_path and initial_path.is_dir():
                shell32.SHCreateItemFromParsingName.argtypes = [
                    ctypes.c_wchar_p, ctypes.c_void_p,
                    ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p),
                ]
                shell32.SHCreateItemFromParsingName.restype = ctypes.c_long
                if shell32.SHCreateItemFromParsingName(
                    str(initial_path.resolve()), None, ctypes.byref(iid_shell_item),
                    ctypes.byref(initial_shell_item),
                ) >= 0:
                    try:
                        set_folder(dialog, initial_shell_item)
                    finally:
                        com_method(initial_shell_item, 2, ctypes.c_ulong)(initial_shell_item)

            show_result = show(dialog, None)
            if show_result == ctypes.c_long(0x800704C7).value:  # ERROR_CANCELLED
                return True, ""
            if show_result < 0:
                return False, ""

            selected_item = ctypes.c_void_p()
            if get_result(dialog, ctypes.byref(selected_item)) < 0 or not selected_item.value:
                return True, ""
            try:
                display_name = ctypes.c_void_p()
                get_display_name = com_method(
                    selected_item, 5, ctypes.c_long,
                    ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p),
                )
                if get_display_name(selected_item, 0x80058000, ctypes.byref(display_name)) < 0:
                    return False, ""
                try:
                    return True, ctypes.wstring_at(display_name)
                finally:
                    ole32.CoTaskMemFree(display_name)
            finally:
                com_method(selected_item, 2, ctypes.c_ulong)(selected_item)
        finally:
            release_dialog(dialog)
    except Exception:
        # Folder selection must remain available even if a Windows shell
        # extension or COM initialization fails on a particular machine.
        return False, ""
    finally:
        if initialized:
            ole32.CoUninitialize()


class QMessageBox(QtMessageBox):
    """Localize messages and route non-interactive alerts into the QML shell."""

    _alert_handler = None
    _question_handler = None

    @classmethod
    def set_alert_handler(cls, handler) -> None:
        cls._alert_handler = handler

    @classmethod
    def set_question_handler(cls, handler) -> None:
        cls._question_handler = handler

    @classmethod
    def _show_alert(cls, severity, parent, title, text, *args):
        localized_title = _ui_text(title)
        localized_text = _ui_text(text)
        if parent is None and cls._alert_handler is not None:
            cls._alert_handler(localized_title, localized_text, severity)
            return QtMessageBox.StandardButton.Ok
        method = getattr(QtMessageBox, severity)
        return method(parent, localized_title, localized_text, *args)

    @staticmethod
    def information(parent, title, text, *args):
        return QMessageBox._show_alert("information", parent, title, text, *args)

    @staticmethod
    def warning(parent, title, text, *args):
        return QMessageBox._show_alert("warning", parent, title, text, *args)

    @staticmethod
    def critical(parent, title, text, *args):
        return QMessageBox._show_alert("critical", parent, title, text, *args)

    @staticmethod
    def question(parent, title, text, *args):
        if parent is None and QMessageBox._question_handler is not None:
            return QMessageBox._question_handler(_ui_text(title), _ui_text(text), *args)
        return QtMessageBox.question(parent, _ui_text(title), _ui_text(text), *args)


class QFileDialog(QtFileDialog):
    """Use localized captions for native file dialogs while retaining Qt's API."""

    @staticmethod
    def getOpenFileName(parent=None, caption="", directory="", filter="", *args):
        with _native_explorer_profile():
            return QtFileDialog.getOpenFileName(parent, _ui_text(caption), _existing_dialog_directory(directory), _ui_text(filter), *args)

    @staticmethod
    def getOpenFileNames(parent=None, caption="", directory="", filter="", *args):
        with _native_explorer_profile():
            return QtFileDialog.getOpenFileNames(parent, _ui_text(caption), _existing_dialog_directory(directory), _ui_text(filter), *args)

    @staticmethod
    def getSaveFileName(parent=None, caption="", directory="", filter="", *args):
        return QtFileDialog.getSaveFileName(
            parent, _ui_text(caption), directory, _ui_text(filter), *args
        )

    @staticmethod
    def getExistingDirectory(parent=None, caption="", directory="", options=QtFileDialog.Option.ShowDirsOnly):
        with _native_explorer_profile():
            localized_caption = _ui_text(caption)
            initial_directory = _existing_dialog_directory(directory)
            handled, selected = _native_windows_folder_dialog(localized_caption, initial_directory)
            if handled:
                return selected
            return QtFileDialog.getExistingDirectory(parent, localized_caption, initial_directory, options)

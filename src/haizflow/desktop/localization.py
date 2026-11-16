"""Localized wrappers for native Qt dialogs.

QML owns visible application copy; this module keeps native file and message
dialogs aligned with the persisted UI language.
"""

import os
import re
from pathlib import Path

from PySide6.QtWidgets import QFileDialog as QtFileDialog, QMessageBox as QtMessageBox

from haizflow.config import NATIVE_WINDOWS_USERPROFILE
from haizflow.core.paths import app_data_dir

_UI_LANGUAGE = "en"


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
        "Cannot open the file picker. Please try again.": "Không thể mở bộ chọn tệp. Hãy thử lại.",
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
        "Translate again": "Dịch lại",
        "Translating again will remove the current voice. You will need to create the voice again.": (
            "Dịch lại sẽ làm mất giọng đọc hiện tại, cần phải tạo giọng đọc mới"
        ),
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
    profile_path = NATIVE_WINDOWS_USERPROFILE
    if os.name == "nt":
        from haizflow.desktop.native_file_picker import shell_environment
        try:
            profile_path = shell_environment()["USERPROFILE"]
        except OSError:
            # The picker will report its own launch error; do not create or
            # advertise a replacement portable Downloads folder.
            return ""
    profile = Path(profile_path).expanduser()
    if profile.is_dir():
        for name in ("Downloads", "Videos", "Desktop", "Documents"):
            candidate = profile / name
            if candidate.is_dir():
                return str(candidate.resolve())
        return str(profile.resolve())
    return ""


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


def _windows_picker(kind, caption, directory, name_filter="", args=(), parent=None):
    if os.name != "nt":
        return None
    from haizflow.desktop.native_file_picker import pick
    try:
        return pick(kind, _ui_text(caption), directory, _ui_text(name_filter), args, parent)
    except (OSError, RuntimeError, ValueError):
        import logging
        logging.getLogger(__name__).exception("Native Windows picker failed")
        QMessageBox.warning(None, "HaizFlow", "Cannot open the file picker. Please try again.")
        return [], ""


class QFileDialog(QtFileDialog):
    """One standard native dialog path for batch, manual and every other page."""

    @staticmethod
    def getOpenFileName(parent=None, caption="", directory="", filter="", *args):
        selected = _windows_picker("open", caption, directory, filter, args, parent)
        if selected is not None:
            paths, selected_filter = selected
            return (paths[0] if paths else ""), selected_filter
        return QtFileDialog.getOpenFileName(parent, _ui_text(caption), _existing_dialog_directory(directory), _ui_text(filter), *args)

    @staticmethod
    def getOpenFileNames(parent=None, caption="", directory="", filter="", *args):
        selected = _windows_picker("multiple", caption, directory, filter, args, parent)
        if selected is not None:
            return selected
        return QtFileDialog.getOpenFileNames(parent, _ui_text(caption), _existing_dialog_directory(directory), _ui_text(filter), *args)

    @staticmethod
    def getSaveFileName(parent=None, caption="", directory="", filter="", *args):
        selected = _windows_picker("save", caption, directory, filter, args, parent)
        if selected is not None:
            paths, selected_filter = selected
            return (paths[0] if paths else ""), selected_filter
        return QtFileDialog.getSaveFileName(parent, _ui_text(caption), directory, _ui_text(filter), *args)

    @staticmethod
    def getExistingDirectory(parent=None, caption="", directory="", options=QtFileDialog.Option.ShowDirsOnly):
        selected = _windows_picker("folder", caption, directory, args=("", options), parent=parent)
        if selected is not None:
            paths, _selected_filter = selected
            return paths[0] if paths else ""
        return QtFileDialog.getExistingDirectory(parent, _ui_text(caption), _existing_dialog_directory(directory), options)

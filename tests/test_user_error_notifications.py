"""User-safe summaries and explicit diagnostics, without running tasks/models."""
import json
import os
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from haizflow.desktop.qml_controller import HaizFlowController

QML = Path(__file__).parents[1] / "src/haizflow/desktop/qml"
_APP = None


class Host(QObject):
    technicalErrorLogRequested = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.calls = []
        self.work_running = True

    @Slot(str, str)
    @Slot(str, str, str)
    def showErrorDetails(self, title, detail, log=""):
        self.calls.append((title, detail, log))


def visual(item):
    yield item
    for child in item.childItems():
        yield from visual(child)


@pytest.fixture
def scene():
    global _APP
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _APP = QGuiApplication.instance() or QGuiApplication([])
    app = _APP
    for name in ("SegUIVar.ttf", "segoeui.ttf", "SegoeIcons.ttf"):
        font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))
    engine, host = QQmlEngine(), Host()
    engine.rootContext().setContextProperty("testHost", host)
    warnings = []
    engine.warnings.connect(lambda values: warnings.extend(value.toString() for value in values))
    windows = []

    def create(body, width=580, height=500):
        component = QQmlComponent(engine)
        component.setData((f'import QtQuick\nimport QtQuick.Controls.Basic\nimport "{QML.as_uri()}"\n'
            f'ApplicationWindow {{ width: {width}; height: {height}; visible: true; color: Theme.window; {body} }}'
            ).encode(), QUrl())
        assert component.isReady(), [error.toString() for error in component.errors()]
        window = component.create()
        assert window
        windows.append((window, component))
        QTest.qWait(60)
        return window

    yield create, host, warnings
    for window, _ in windows:
        window.close()
        window.deleteLater()
    app.processEvents()
    assert not warnings, warnings
    engine.deleteLater()
    app.processEvents()


@pytest.mark.parametrize("raw,expected", [
    ("RuntimeError: CUDA out of memory", "bộ nhớ"),
    ("RuntimeError: CUDA is unavailable", "GPU không khả dụng"),
    ("RuntimeError: No CUDA GPUs are available", "GPU không khả dụng"),
    ("HTTP 429 provider rate_limit", "giới hạn"),
    ("HTTPError: 503 Service unavailable", "Máy chủ"),
    ("OmniVoice synthesis exceeded processing timeout", "chưa phản hồi"),
    ("Traceback\n File \"C:/private/user.py\", line 42\nKeyError: 'impersonate'", "Chi tiết"),
    ("'impersonate'", "Chi tiết"),
])
def test_short_summary_never_renders_raw_diagnostics(scene, raw, expected):
    create, _, _ = scene
    window = create(f'Text {{ objectName: "summary"; text: ErrorPresentation.summary({json.dumps(raw)}) }}')
    text = window.findChild(QQuickItem, "summary").property("text")
    assert expected in text and len(text) < 140
    assert "Traceback" not in text and "C:/private" not in text and "impersonate" not in text


@pytest.mark.parametrize("tone", ["success", "info", "information"])
def test_export_path_never_turns_success_or_information_into_an_error(scene, tone):
    create, _, _ = scene
    path = "E:/hongnguyenky/lo2.mp4"
    window = create('ToastStack { objectName: "toasts"; width: 390 }')
    stack = window.findChild(QQuickItem, "toasts")
    stack.show("Xuất video thành công", path, tone, 1600, "")
    QTest.qWait(30)
    toast = next(item for item in visual(window.contentItem()) if item.objectName() == "userErrorToast")
    assert not toast.property("issue")
    message = next(item for item in visual(toast) if item.objectName() == "toastMessage")
    assert message.property("text") == path
    confirm = next(item for item in visual(toast) if item.objectName() == "toastConfirmButton")
    assert not confirm.isVisible()
    QTest.qWait(1650)
    assert not any(item.objectName() == "userErrorToast" for item in visual(window.contentItem()))


def test_success_details_do_not_write_fake_error_to_log(scene, caplog):
    import logging

    _, host, _ = scene
    snapshots = []
    host.technicalErrorLogRequested.connect(lambda title, text: snapshots.append(text))
    caplog.set_level(logging.INFO, logger="haizflow.user_errors")
    HaizFlowController.showAlertDetails(host, "Xuất video thành công", "E:/hongnguyenky/lo2.mp4", "success", "")
    assert snapshots and "[INFO]" in snapshots[0] and "[ERROR]" not in snapshots[0]
    assert caplog.records[-1].levelno == logging.INFO


@pytest.mark.parametrize("path", ["E:/hongnguyenky/lo2.mp4", "E:/exports/RuntimeError.mp4", ""])
def test_status_strip_does_not_turn_empty_ready_or_export_path_into_error(scene, path):
    create, _, _ = scene
    window = create(f'Text {{ objectName: "status"; text: ErrorPresentation.status({json.dumps(path)}, false) }}')
    assert window.findChild(QQuickItem, "status").property("text") == path


def test_notice_details_keeps_raw_snapshot_and_ack_only_dismisses_ui(scene):
    create, host, _ = scene
    raw = "Traceback\\nRuntimeError: local model failed"
    window = create(
        'ToastStack { id: popup; objectName: "cornerNotices"; width: 390; '
        'anchors.top: parent.top; anchors.right: parent.right; anchors.margins: 20;'
        'onDetailsRequested: (title, detail, tone, log) => testHost.showErrorDetails(title, detail, log) }'
        'UserErrorNotice { id: source; objectName: "notice"; '
        f'details: {json.dumps(raw)}; logText: "Complete worker log";'
        'notificationHandler: function(title, detail, log) { popup.show(title, detail, "critical", 0, log); }}',
        640, 500)
    notice = window.findChild(QQuickItem, "notice")
    def find(name):
        return next(item for item in visual(window.contentItem()) if item.objectName() == name)
    popup = find("userErrorToast")
    point = popup.mapToScene(popup.boundingRect().topLeft())
    assert abs(point.x() + popup.width() - (window.width() - 20)) <= 1 and abs(point.y() - 20) <= 1
    summary, title = find("toastMessage"), find("toastTitle")
    assert "Traceback" not in summary.property("text")
    assert abs(title.mapToScene(title.boundingRect().topLeft()).x()
               - summary.mapToScene(summary.boundingRect().topLeft()).x()) <= 1
    details, confirm = find("toastDetailsButton"), find("toastConfirmButton")
    assert abs(details.mapToScene(details.boundingRect().center()).y()
               - confirm.mapToScene(confirm.boundingRect().center()).y()) <= 1
    gap = (details.mapToScene(details.boundingRect().topLeft()).y()
           - summary.mapToScene(summary.boundingRect().bottomLeft()).y())
    assert gap >= 12
    details.clicked.emit()
    assert host.calls[0][1:] == (raw, "Complete worker log")
    assert host.work_running
    notice.setProperty("details", "HTTPError: 503 Service unavailable")
    QTest.qWait(60)
    assert find("userErrorToast").isVisible()
    target = QML.parents[3] / "build/user-error-notice.png"
    target.parent.mkdir(exist_ok=True)
    assert window.grabWindow().save(str(target))
    find("toastConfirmButton").clicked.emit()
    QTest.qWait(30)
    assert not any(item.objectName() == "userErrorToast" for item in visual(window.contentItem()))
    notice.setProperty("details", "Traceback: next error")
    QTest.qWait(30)
    find("toastCloseButton").clicked.emit()
    assert host.work_running


def test_alert_has_three_actions_and_hides_traceback(scene):
    create, _, _ = scene
    window = create('AppAlertDialog { objectName: "alert"; Component.onCompleted: '
                    'showAlert("Không xuất được video", "Traceback: ffmpeg failed", "critical") }')
    assert "Traceback" not in window.findChild(QQuickItem, "appAlertSummary").property("text")
    assert window.findChild(QQuickItem, "appAlertDetails").isVisible()
    assert window.findChild(QQuickItem, "appAlertConfirm").isVisible()
    QTest.keyClick(window, Qt.Key_Escape)
    QTest.qWait(200)
    assert not window.findChild(QObject, "alert").property("visible")


def test_backend_diagnostics_capture_origin_without_selected_project_lookup():
    host = Host()
    captured = []
    host.technicalErrorLogRequested.connect(lambda title, text: captured.append((title, text)))
    HaizFlowController.showErrorDetails(host, "Project A", "RuntimeError: worker stopped", "A engine log")
    assert captured[0][0] == "Project A"
    assert "RuntimeError: worker stopped" in captured[0][1] and "A engine log" in captured[0][1]


def test_error_surfaces_use_the_shared_notice():
    for name in ("ManualStageInspector", "VoiceCloneDialog", "BatchDetailsDialog",
                 "UrlImportDialog", "ChannelDownloadPage", "ChannelVideoRow", "VideoExportJobsDialog",
                 "BackgroundMusicLinkDialog", "SettingsMcpGroup", "ResourcePackRow"):
        assert "UserErrorNotice {" in (QML / (name + ".qml")).read_text("utf-8"), name

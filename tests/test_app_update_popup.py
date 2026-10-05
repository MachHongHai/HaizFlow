import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QMetaObject, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtTest import QTest

QML = Path(__file__).resolve().parents[1] / "src/haizflow/desktop/qml"


def test_native_update_popup_requires_confirmation_and_supports_cancel():
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(b'''import QtQuick
import QtQuick.Controls.Basic
import "."
ApplicationWindow {
    width: 800; height: 600; visible: true
    QtObject {
        id: updateState; objectName: "updateState"
        property string appUpdateState: "available"
        property bool appUpdateBlocked: false
        property bool hasAppUpdate: true
        property string latestAppVersion: "99.0.0"
        property string currentAppVersion: "0.1.0"
        property string appUpdateError: ""
        property int appUpdateDownloadProgress: 0
        property string confirmed: ""
        function confirmAppUpdate(version, state) { confirmed = version + ":" + state; return true; }
    }
    AppUpdatePopup { controller: updateState; Component.onCompleted: open() }
}''', QUrl.fromLocalFile(str(QML / "UpdateTest.qml")))
    assert component.isReady(), [error.toString() for error in component.errors()]
    window = component.create()
    state = window.findChild(QObject, "updateState")
    try:
        app.processEvents()
        details = window.findChild(QObject, "appUpdateDetailsLink")
        assert details is not None and details.property("visible")
        assert details.property("text") == "haizflow.pages.dev"
        assert details.property("destination").toString() == "https://haizflow.pages.dev/"
        for checking_state in ("idle", "checking", "error", "no_release", "available"):
            state.setProperty("appUpdateState", checking_state)
            app.processEvents()
            assert details.property("visible")
        button = window.findChild(QObject, "appUpdateInstallButton")
        assert button.property("enabled")
        assert QMetaObject.invokeMethod(button, "clicked", Qt.DirectConnection)
        app.processEvents()
        dialog = window.findChild(QObject, "appUpdateConfirmationDialog")
        assert dialog is not None and dialog.property("visible")
        assert dialog.property("title") == "Tải bản cập nhật?"
        assert state.property("confirmed") == ""
        QTest.keyClick(window, Qt.Key_Escape)
        QTest.qWait(250)
        assert state.property("confirmed") == ""

        assert QMetaObject.invokeMethod(button, "clicked", Qt.DirectConnection)
        app.processEvents()
        dialog = window.findChild(QObject, "appUpdateConfirmationDialog")
        confirm = next(item for item in dialog.findChildren(QObject)
                       if item.property("text") == "Tải cập nhật")
        assert QMetaObject.invokeMethod(confirm, "clicked", Qt.DirectConnection)
        QTest.qWait(250)
        assert state.property("confirmed") == "99.0.0:available"

        state.setProperty("appUpdateState", "ready")
        assert QMetaObject.invokeMethod(button, "clicked", Qt.DirectConnection)
        app.processEvents()
        dialog = window.findChild(QObject, "appUpdateConfirmationDialog")
        assert dialog.property("title") == "Khởi động lại để cập nhật?"
        assert "Lưu các thay đổi" in dialog.property("message")
        state.setProperty("appUpdateBlocked", True)
        assert not button.property("enabled")
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()

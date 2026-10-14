"""Closing the actual shell confirmation never strands a deferred action."""
import subprocess
import sys
from pathlib import Path


def check_confirmation():
    from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QMetaObject, QObject, Qt, QTimer, QUrl, Signal, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtTest import QTest
    from hflow.desktop.qml_controller import HFlowController
    from hflow.desktop.localization import QMessageBox

    app = QGuiApplication.instance() or QGuiApplication([])
    class Backend(QObject):
        appConfirmationRequested = Signal(str, str)
        def __init__(self):
            super().__init__()
            self._confirmation_loop = None
            self._confirmation_accepted = False
            self.responses = []
            self.results = []
        @Slot(bool)
        def respondToAppConfirmation(self, accepted):
            self.responses.append(accepted)
            HFlowController.respondToAppConfirmation(self, accepted)
        @Slot()
        def request(self):
            self.results.append(HFlowController._show_app_question(self, "Translate again", "Remove current voice?"))

    backend = Backend()
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("TestController", backend)
    directory = Path(__file__).parents[1] / "src/hflow/desktop/qml"
    source = (directory / "Main.qml").read_text(encoding="utf-8")
    confirmation = source[source.index("    ConfirmDialog {\n        id: appConfirmationDialog"):].split("\n    Connections {", 1)[0]
    component = QQmlComponent(engine)
    component.setData((f'''import QtQuick
import QtQuick.Controls.Basic
import "{directory.as_uri()}"
ApplicationWindow {{ width: 800; height: 600; visible: true
    DeferredActionButton {{ objectName: "requestButton"; width: 200; height: 42; readyText: "Dịch";
        onExecute: context => TestController.request()
    }}
''' + confirmation.replace("AppController", "TestController") + "\n}").encode(), QUrl())
    assert component.isReady(), [error.toString() for error in component.errors()]
    window = component.create()
    dialog = window.findChild(QObject, "appConfirmationDialog")
    button = window.findChild(QObject, "requestButton")
    def open_dialog(title, message):
        dialog.setProperty("title", title)
        dialog.setProperty("message", message)
        QMetaObject.invokeMethod(dialog, "open", Qt.DirectConnection)
    backend.appConfirmationRequested.connect(open_dialog)
    try:
        for action in ("x", "reject", "escape", "confirm", "x"):
            responses = len(backend.responses)
            def dismiss():
                if action == "x":
                    close = dialog.findChild(QObject, "appDialogCloseButton")
                    assert close is not None
                    QMetaObject.invokeMethod(close, "clicked", Qt.DirectConnection)
                elif action == "escape":
                    QTest.keyClick(window, Qt.Key_Escape)
                elif action == "confirm":
                    QMetaObject.invokeMethod(dialog, "confirmed", Qt.DirectConnection)
                    QMetaObject.invokeMethod(dialog, "accept", Qt.DirectConnection)
                else:
                    QMetaObject.invokeMethod(dialog, "reject", Qt.DirectConnection)
            # Ensure there is a hard timeout rather than hanging the test process.
            watchdog = QTimer()
            watchdog.setSingleShot(True)
            watchdog.timeout.connect(lambda: backend.respondToAppConfirmation(False))
            watchdog.start(2000)
            QTimer.singleShot(260, dismiss)
            QMetaObject.invokeMethod(button, "clicked", Qt.DirectConnection)
            assert button.property("preparing") and len(backend.results) < 5
            QTest.qWait(550)
            assert watchdog.isActive(), "Confirmation dismissal did not release the waiting action"
            watchdog.stop()
            assert not button.property("preparing") and button.property("enabled")
            assert backend._confirmation_loop is None
            assert len(backend.responses) == responses + 1
            expected = QMessageBox.StandardButton.Yes if action == "confirm" else QMessageBox.StandardButton.Cancel
            assert backend.results[-1] == expected
        # A response emitted synchronously before exec() is also a completed answer.
        backend.appConfirmationRequested.disconnect(open_dialog)
        backend.appConfirmationRequested.connect(lambda *_: backend.respondToAppConfirmation(False))
        assert HFlowController._show_app_question(backend, "Early", "Cancel") == QMessageBox.StandardButton.Cancel
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        assert not backend.findChildren(QEventLoop)
        backend.appConfirmationRequested.disconnect()
        backend.appConfirmationRequested.connect(lambda *_: QTimer.singleShot(20, app.aboutToQuit.emit))
        assert HFlowController._show_app_question(backend, "Shutdown", "Cancel") == QMessageBox.StandardButton.Cancel
        assert backend._confirmation_loop is None
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def test_confirmation_x_escape_cancel_and_accept_release_deferred_action_once():
    result = subprocess.run([sys.executable, str(Path(__file__).resolve())], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


if __name__ == "__main__":
    check_confirmation()

"""Runtime UI tests with synthetic input, never opening a physical microphone."""

from pathlib import Path

from PySide6.QtCore import QObject, QMetaObject, QUrl, Signal, Slot, Property
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from shiboken6 import getCppPointer, wrapInstance

QML = Path(__file__).resolve().parents[1] / "src/haizflow/desktop/qml"


class DraftSettingsState(QObject):
    settingsChanged = Signal()
    settingsLanguage = Property(str, lambda self: self.values["settingsLanguage"], notify=settingsChanged)
    processingDevice = Property(str, lambda self: self.values["processingDevice"], notify=settingsChanged)
    keepModelsWarm = Property(bool, lambda self: self.values["keepModelsWarm"], notify=settingsChanged)
    isProcessing = Property(bool, lambda self: False, constant=True)
    processingDeviceSummary = Property(str, lambda self: "CPU", constant=True)
    performanceProfileDetail = Property(str, lambda self: "CPU", constant=True)
    appUpdateState = Property(str, lambda self: "idle", constant=True)
    currentAppVersion = Property(str, lambda self: "0.1.0", constant=True)
    latestAppVersion = Property(str, lambda self: "", constant=True)

    def __init__(self):
        super().__init__()
        self.calls = []
        self.values = {"settingsLanguage": "vi", "processingDevice": "cpu", "keepModelsWarm": False}

    def value(self, key):
        return self.values[key]

    @Slot(str, str, bool, result=bool)
    def applyGeneralSettings(self, language, device, warm):
        self.calls.append((language, device, warm))
        self.values.update(settingsLanguage=language, processingDevice=device, keepModelsWarm=warm)
        self.settingsChanged.emit()
        return True


def test_settings_do_not_commit_on_timer_or_page_exit():
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    state = DraftSettingsState()
    engine.rootContext().setContextProperty("TestController", state)
    component = QQmlComponent(engine)
    source = (QML / "SettingsPage.qml").read_text(encoding="utf-8").replace("AppController", "TestController")
    component.setData(source.encode(), QUrl.fromLocalFile(str(QML / "SettingsPage.qml")))
    assert component.isReady(), "\n".join(e.toString() for e in component.errors())
    page = component.create()
    window = QQuickWindow()
    item = wrapInstance(getCppPointer(page)[0], QQuickItem)
    item.setParentItem(window.contentItem())
    item.setWidth(1000)
    item.setHeight(700)
    window.show()
    try:
        page.setProperty("draftLanguage", "en")
        page.setProperty("draftKeepWarm", True)
        page.setProperty("localEditsPending", True)
        QTest.qWait(400)
        assert state.calls == []
        assert state.value("settingsLanguage") == "vi"
        page.setProperty("visible", False)
        app.processEvents()
        assert state.calls == []
        page.setProperty("visible", True)
        assert page.property("draftLanguage") == "vi"
        page.setProperty("draftLanguage", "en")
        page.setProperty("draftKeepWarm", True)
        page.setProperty("localEditsPending", True)
        button = page.findChild(QObject, "applyGeneralSettingsButton")
        assert button.property("enabled")
        assert page.property("localEditsPending")
        assert page.property("draftDirty")
        QMetaObject.invokeMethod(button, "clicked")
        app.processEvents()
        assert state.calls == [("en", "cpu", True)]
        assert not button.property("enabled")
    finally:
        window.close()
        page.deleteLater()
        app.processEvents()


def test_recording_controls_are_distinct_and_stay_inside_dialog():
    app = QGuiApplication.instance() or QGuiApplication([])
    for font in ("segoeui.ttf", "SegUIVar.ttf", "segmdl2.ttf", "SegoeIcons.ttf"):
        file = Path("C:/Windows/Fonts") / font
        if file.is_file():
            QFontDatabase.addApplicationFont(str(file))
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import QtQuick.Controls.Basic
import "."
ApplicationWindow {
    width: 1120; height: 720; visible: true
    property alias dialog: clone
    QtObject {
        id: fake
        objectName: "fakeRecorder"
        signal selectedVideoChanged()
        property string selectedVideoId: "synthetic"
        property string ttsProvider: "omnivoice"
        property string voiceCloneReferencePath: ""
        property bool capturing: false
        property int starts: 0
        property int stops: 0
        function voiceCloneReferenceAnalysis(_path, _count) { return {durationMs: 5000, peaks: [0.4, 0.5]}; }
        function voiceCloneInputDevices() { return [{id: "", label: "Test microphone", selected: true}]; }
        function selectVoiceCloneInputDevice(_id) { return true; }
        function startVoiceCloneRecording() { starts++; capturing = true; return true; }
        function voiceCloneRecordingState() { return {active: capturing, durationMs: 3000, peaks: [0.5], hasSignal: true, levelDb: -20}; }
        function finishVoiceCloneRecording() { stops++; capturing = false; return false; }
        function cancelVoiceCloneRecording() { capturing = false; }
    }
    property alias fake: fake
    VoiceCloneDialog { id: clone; objectName: "recordingDialog"; controller: fake }
    Component.onCompleted: clone.openForSelectedVideo()
}
''', QUrl.fromLocalFile(str(QML / "RecordingTestHarness.qml")))
    assert component.isReady(), "\n".join(e.toString() for e in component.errors())
    window = component.create()
    assert window
    try:
        QTest.qWait(250)
        dialog = window.findChild(QObject, "recordingDialog")
        fake = window.findChild(QObject, "fakeRecorder")
        record = dialog.findChild(QObject, "voiceCloneRecordButton")
        playback = dialog.findChild(QObject, "voiceClonePlaybackButton")
        assert record is not None and playback is not None
        assert not playback.property("visible")
        QMetaObject.invokeMethod(record, "clicked")
        app.processEvents()
        assert fake.property("starts") == 1
        assert dialog.property("recording")
        assert record.property("text") == "Dừng ghi"
        QMetaObject.invokeMethod(record, "clicked")
        app.processEvents()
        assert fake.property("stops") == 1
        assert not dialog.property("recording")
        assert record.property("text") == "Bắt đầu ghi"
        # A failed capture can display its message without growing beyond the window.
        assert dialog.property("height") <= 688
        output = Path(__file__).resolve().parents[1] / "build/ui-checks"
        output.mkdir(parents=True, exist_ok=True)
        quick_window = wrapInstance(getCppPointer(window)[0], QQuickWindow)
        QTest.qWait(150)
        assert quick_window.grabWindow().save(str(output / "voice-recording.png"))
        dialog.setProperty("recordingError", "")
        dialog.setProperty("samplePath", "synthetic-sample.wav")
        app.processEvents()
        apply = dialog.findChild(QObject, "voiceCloneApplyButton")
        assert playback.property("visible")
        assert apply.property("visible")
        assert record.property("text") == "Ghi lại"
        apply_item = wrapInstance(getCppPointer(apply)[0], QQuickItem)
        position = apply_item.mapToScene(apply_item.boundingRect().bottomRight())
        assert position.y() < window.height() - 16
        QTest.qWait(100)
        assert quick_window.grabWindow().save(str(output / "voice-recording-review.png"))
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()

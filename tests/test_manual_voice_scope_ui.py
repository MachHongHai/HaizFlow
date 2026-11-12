"""Real dialog layout/confirmation with a no-network, no-model controller."""
from pathlib import Path

import pytest
from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

QML = Path(__file__).parents[1] / "src/haizflow/desktop/qml"
APP = None


class Host(QObject):
    selectedVideoChanged = Signal()
    selectedVideoId = Property(str, lambda _: "scope-video", constant=True)
    manualVoiceLanguage = Property(str, lambda _: "vi", constant=True)
    audioPreviewSource = Property(str, lambda _: "", constant=True)
    audioPreviewState = Property(str, lambda _: "idle", constant=True)
    ttsProvider = Property(str, lambda _: "edge", constant=True)
    ttsVoice = Property(str, lambda _: "vi-VN-HoaiMyNeural", constant=True)
    ttsProviderOptions = Property("QVariantList", lambda _: [{"provider": "edge", "label": "Edge TTS"}], constant=True)
    manualSubtitleModel = Property("QVariantMap", lambda _: {"segments": [
        {"segment_id": f"cue-{i}", "text": f"Cảm ơn mẹ, con đã hiểu rồi. Câu {i + 1}.",
         "start": i * 3.5, "end": i * 3.5 + 2.75}
        for i in range(25)]}, constant=True)

    @Slot(str, result="QVariantMap")
    def manualVoiceConfiguration(self, segment_id):
        return {"segmentId": segment_id, "hasPublishedVoice": True}

    @Slot(str, result="QVariantList")
    def manualVoiceOptionsForProvider(self, _provider):
        return [{"voice": "vi-VN-HoaiMyNeural", "label": "Hoài My", "available": True}]

    @Slot(str, str, "QVariantList", result=bool)
    def validateTtsProviderForLanguage(self, *_args):
        return True


@pytest.mark.parametrize("width,height", [(1440, 900), (760, 720)])
@pytest.mark.parametrize("voice_scope", ["selection", "segment"])
def test_scope_dialog_footer_and_confirmation(width, height, voice_scope):
    global APP
    APP = QGuiApplication.instance() or QGuiApplication([])
    for name in ("segoeui.ttf", "SegoeIcons.ttf"):
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + name)
    engine, host = QQmlEngine(), Host()
    engine.rootContext().setContextProperty("scopeHost", host)
    warnings = []
    engine.warnings.connect(lambda values: warnings.extend(value.toString() for value in values))
    window_component = QQmlComponent(engine)
    window_component.setData((f'import QtQuick\nimport QtQuick.Controls.Basic\nimport "{QML.as_uri()}"\n'
        f'ApplicationWindow {{ width: {width}; height: {height}; visible: true; color: Theme.window }}'
        ).encode(), QUrl())
    window = window_component.create()
    component = QQmlComponent(engine)
    source = (QML / "ManualVoiceDialog.qml").read_text("utf-8").replace("AppController", "scopeHost")
    component.setData(source.encode(), QUrl.fromLocalFile(str(QML / "ScopedDialogTest.qml")))
    assert component.isReady(), [error.toString() for error in component.errors()]
    dialog = component.createWithInitialProperties({"parent": window.contentItem()})
    assert dialog
    confirmations = []
    dialog.confirmed.connect(lambda *args: confirmations.append(args))
    try:
        dialog.openForVoice(True, {"globalProvider": "edge", "globalVoice": "vi-VN-HoaiMyNeural",
            "speakerMode": "single", "segmentId": "cue-4"})
        QTest.qWait(180)
        scope = dialog.findChild(QQuickItem, "manualVoiceScopePicker")
        scope.setProperty("scope", voice_scope)
        scope.setProperty("selectedIds", ["cue-0", "cue-2"])
        if voice_scope == "segment":
            assert scope.findChild(QQuickItem, "manualVoiceCurrentCueText").property("text").endswith("Câu 5.")
            assert scope.findChild(QQuickItem, "manualVoiceCurrentCueTime").property("text") == "05  00:14.000 — 00:16.750"
        QTest.qWait(80)
        button = dialog.findChild(QQuickItem, "manualVoiceGenerateButton")
        footer = dialog.findChild(QQuickItem, "appDialogFooter")
        assert button.isVisible() and button.isEnabled()
        assert abs(footer.height() - dialog.property("footerHeight")) <= 1
        assert footer.mapToScene(footer.boundingRect().bottomRight()).y() <= height
        assert button.mapToScene(button.boundingRect().bottomRight()).y() <= height
        assert window.grabWindow().save(str(QML.parents[3] / "build" / f"manual-voice-{voice_scope}-{width}.png"))
        button.clicked.emit()
        QTest.qWait(160)
        assert len(confirmations) == 1
        assert confirmations[0][2] == voice_scope
        assert confirmations[0][3] == "cue-4"
        ids = confirmations[0][5]
        if hasattr(ids, "toVariant"):
            ids = ids.toVariant()
        assert list(ids) == (["cue-4"] if voice_scope == "segment" else ["cue-0", "cue-2"])
        assert not warnings, warnings
    finally:
        dialog.close()
        dialog.deleteLater()
        window.close()
        window.deleteLater()
        APP.processEvents()
        engine.deleteLater()
        APP.processEvents()


@pytest.mark.parametrize("current_index,expected_id", [(17, "cue-17"), (-1, "")])
def test_inspector_voice_target_uses_playhead_not_stale_subtitle(current_index, expected_id):
    global APP
    APP = QGuiApplication.instance() or QGuiApplication([])
    engine, host = QQmlEngine(), Host()
    engine.rootContext().setContextProperty("AppController", host)
    inspector = (QML / "ManualStageInspector.qml").read_text("utf-8")
    function = inspector.split("    function openVoiceDialog()", 1)[1].split(
        "    function openBackgroundMusicLinkDialog()", 1)[0]
    component = QQmlComponent(engine)
    component.setData(('import QtQml\nQtObject { id: root\n'
        f'property int currentSubtitleIndex: {current_index}\n'
        'property var subtitleSegments: AppController.manualSubtitleModel.segments\n'
        'property var selectedSubtitle: subtitleSegments[0]\n'
        'property var captured: []\n'
        'property QtObject voiceDialogLoader: QtObject {\n'
        'function invoke(method, args) { root.captured = args; } }\n'
        'function openVoiceDialog()' + function + '\n}').encode(), QUrl())
    probe = component.create()
    assert probe, [error.toString() for error in component.errors()]
    try:
        probe.openVoiceDialog()
        captured = probe.property("captured").toVariant()
        assert captured[1]["segmentId"] == expected_id
    finally:
        probe.deleteLater()
        engine.deleteLater()
        APP.processEvents()

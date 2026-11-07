"""Native Qt controls: official labels, local edits, supported choices and narrow layouts."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


@pytest.mark.parametrize("width", [360, 640])
def test_project_reasoning_controls_render_and_edit_independently(width):
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(width)], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def exercise(width):
    from PySide6.QtCore import Property, QByteArray, QObject, QTranslator, QUrl
    from PySide6.QtGui import QFontDatabase, QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlExpression
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QSignalSpy, QTest

    from haizflow.desktop.translation_api_controller import TranslationApiController
    from haizflow.services import translation_connections as connections

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication([])
    app.setApplicationName("Reasoning controls test")
    for name in ("SegUIVar.ttf", "segoeui.ttf", "SegoeIcons.ttf"):
        path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))

    class Host(QObject):
        def __init__(self):
            super().__init__()
            self.api = TranslationApiController(self)

        @Property(QObject, constant=True)
        def translationApi(self):
            return self.api

    with tempfile.TemporaryDirectory(prefix="reasoning-native-") as directory:
        connections._PATH = Path(directory) / "private.json"
        secrets = {}
        connections.secure_credentials.write_secret = lambda target, key, **kwargs: secrets.__setitem__(target, key)
        first = "api:" + connections.add("openai", "Project A", "fake-key") + ":gpt-6.1-sol"
        second = "api:" + connections.add("deepseek", "Project B", "another-fake-key") + ":deepseek-flash"
        r1_model = ("api:" + connections.add("openrouter", "Project R1", "fake-router-key")
                    + ":deepseek/deepseek-r1-0528")
        host, engine = Host(), QQmlEngine()
        engine.rootContext().setContextProperty("AppController", host)
        warnings = []
        engine.warnings.connect(lambda values: warnings.extend(value.toString() for value in values))
        qml = Path(__file__).parents[1] / "src/haizflow/desktop/qml"
        component = QQmlComponent(engine)
        component.setData(QByteArray('''
            import QtQuick
            import QtQuick.Controls.Basic
            import QtQuick.Layouts
            import "."
            ApplicationWindow {
                id: window
                visible: true
                color: Theme.window
                property string firstModel
                property string secondModel
                property string r1Model
                property string firstEffort: ""
                property string secondEffort: ""
                property string geminiEffort: ""
                property bool geminiHasGuidance: false
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 20
                    spacing: Theme.space16
                    SettingsGroup {
                        Layout.fillWidth: true
                        title: "OpenAI · GPT-6.1 Sol"
                        TranslationReasoningControl {
                            objectName: "firstReasoning"
                            Layout.fillWidth: true
                            selectedModel: window.firstModel
                            reasoningEffort: window.firstEffort
                            onEdited: function(value) { window.firstEffort = value; }
                        }
                    }
                    SettingsGroup {
                        Layout.fillWidth: true
                        title: "DeepSeek · Flash"
                        TranslationReasoningControl {
                            objectName: "secondReasoning"
                            Layout.fillWidth: true
                            selectedModel: window.secondModel
                            reasoningEffort: window.secondEffort
                            onEdited: function(value) { window.secondEffort = value; }
                        }
                    }
                    SettingsGroup {
                        Layout.fillWidth: true
                        title: "Gemini · Flash-Lite"
                        TranslationReasoningControl {
                            objectName: "geminiReasoning"
                            Layout.fillWidth: true
                            selectedModel: "gemini-3.5-flash-lite"
                            reasoningEffort: window.geminiEffort
                            hasGuidance: window.geminiHasGuidance
                            onEdited: function(value) { window.geminiEffort = value; }
                        }
                    }
                    SettingsGroup {
                        Layout.fillWidth: true
                        title: "OpenRouter · DeepSeek R1"
                        TranslationReasoningControl {
                            objectName: "r1Reasoning"
                            Layout.fillWidth: true
                            selectedModel: window.r1Model
                        }
                    }
                    Item { Layout.fillHeight: true }
                }
            }
        '''.encode()), QUrl.fromLocalFile(str(qml / "ReasoningTest.qml")))
        assert component.isReady(), [error.toString() for error in component.errors()]
        window = component.createWithInitialProperties({
            "firstModel": first, "secondModel": second, "r1Model": r1_model})
        window.setWidth(width)
        window.setHeight(600)
        QTest.qWait(100)
        one = window.findChild(QQuickItem, "firstReasoning")
        two = window.findChild(QQuickItem, "secondReasoning")
        combo = one.findChild(QQuickItem, "translationReasoningEffortCombo")
        assert combo.property("currentText") == "Thấp"
        assert combo.property("currentValue") == "low"
        values, _ = QQmlExpression(engine.rootContext(), one, "values.join(',')").evaluate()
        assert values == "low,medium,high,xhigh,max"
        labels, _ = QQmlExpression(engine.rootContext(), one, "options.map(row => row.label).join(',')").evaluate()
        assert labels == "Thấp,Trung bình,Cao,Rất cao,Tối đa"
        gemini = window.findChild(QQuickItem, "geminiReasoning")
        assert gemini.property("effortLabel") == "Mức"
        gemini_combo = gemini.findChild(QQuickItem, "translationReasoningEffortCombo")
        assert gemini_combo.property("currentText") == "Tối thiểu"
        assert gemini_combo.property("currentValue") == "minimal"
        # Changing style/guidance must neither raise the displayed default nor
        # rebuild the dropdown; selecting the default must be explicit too.
        gemini_model_changes = QSignalSpy(gemini_combo.modelChanged)
        window.setProperty("geminiHasGuidance", True)
        QTest.qWait(25)
        assert gemini_combo.property("currentValue") == "minimal"
        gemini_combo.activated.emit(0)
        QTest.qWait(25)
        assert window.property("geminiEffort") == "minimal"
        gemini_combo.setProperty("currentIndex", 2)
        gemini_combo.activated.emit(2)
        QTest.qWait(25)
        assert window.property("geminiEffort") == "medium"
        window.setProperty("geminiHasGuidance", False)
        QTest.qWait(25)
        assert gemini_combo.property("currentValue") == "medium"
        window.setProperty("geminiHasGuidance", True)
        QTest.qWait(25)
        assert gemini_combo.property("currentValue") == "medium"
        assert gemini_model_changes.count() == 0
        r1 = window.findChild(QQuickItem, "r1Reasoning")
        assert r1.isVisible()
        status = r1.findChild(QQuickItem, "translationReasoningMandatoryState")
        assert status.isVisible() and status.property("text") == "Bật"
        assert not r1.findChild(QQuickItem, "translationReasoningEffortCombo").isVisible()
        assert not r1.findChild(QQuickItem, "translationThinkingTypeCombo").isVisible()
        assert combo.x() + combo.width() <= one.width() + 1
        model_changes = QSignalSpy(combo.modelChanged)
        combo.setProperty("currentIndex", 2)
        combo.activated.emit(2)
        QTest.qWait(25)
        assert window.property("firstEffort") == "high" and window.property("secondEffort") == ""
        thinking = two.findChild(QQuickItem, "translationThinkingTypeCombo")
        assert combo.property("currentText") == "Cao" and combo.property("currentValue") == "high"
        assert model_changes.count() == 0  # A selection never destroys/rebuilds the dropdown model.
        assert thinking.property("currentText") == "Tắt"
        assert thinking.property("currentValue") == "disabled"
        thinking.setProperty("currentIndex", 1)
        thinking.activated.emit(1)
        QTest.qWait(25)
        assert window.property("secondEffort") == "low"
        deepseek_effort = two.findChild(QQuickItem, "translationReasoningEffortCombo")
        assert deepseek_effort.isVisible()
        values, _ = QQmlExpression(engine.rootContext(), two, "values.join(',')").evaluate()
        assert values == "low,high,max"
        deepseek_effort.setProperty("currentIndex", 2)
        deepseek_effort.activated.emit(2)
        QTest.qWait(25)
        assert window.property("secondEffort") == "max" and window.property("firstEffort") == "high"
        assert deepseek_effort.property("currentText") == "Tối đa"
        assert deepseek_effort.property("currentValue") == "max"
        window.setProperty("firstModel", r1_model.split(":")[0] + ":" + r1_model.split(":")[1]
                           + ":dots-studio/dots-3-note-preview:free")
        QTest.qWait(25)
        assert one.property("effortLabel") == "Suy luận"
        assert combo.property("currentText") == "Tắt" and combo.property("currentValue") == "disabled"
        assert combo.x() + combo.width() <= one.width() + 1
        optional_snapshot = Path(__file__).parents[1] / "build" / f"translation-reasoning-optional-{width}.png"
        assert window.grabWindow().save(str(optional_snapshot))
        combo.setProperty("currentIndex", 1)
        combo.activated.emit(1)
        QTest.qWait(25)
        assert window.property("firstEffort") == "enabled" and window.property("secondEffort") == "max"
        combo.setProperty("currentIndex", 0)
        combo.activated.emit(0)
        QTest.qWait(25)
        assert window.property("firstEffort") == "disabled" and combo.property("currentText") == "Tắt"
        window.setProperty("firstModel", first)
        window.setProperty("firstEffort", "high")
        QTest.qWait(25)
        one.setEnabled(False)
        assert not combo.isEnabled()
        one.setEnabled(True)
        snapshot = Path(__file__).parents[1] / "build" / f"translation-reasoning-{width}.png"
        snapshot.parent.mkdir(exist_ok=True)
        assert window.grabWindow().save(str(snapshot))
        translator = QTranslator()
        assert translator.load(str(qml.parent / "translations" / "haizflow_en.qm"))
        assert app.installTranslator(translator)
        engine.retranslate()
        QTest.qWait(25)
        assert one.property("effortLabel") == "Level"
        assert combo.property("currentText") == "High" and combo.property("currentValue") == "high", (
            combo.property("currentText"), combo.property("currentValue"), window.property("firstEffort"))
        assert status.property("text") == "Enabled"
        assert thinking.property("currentText") == "Enabled"
        assert window.property("firstEffort") == "high" and window.property("secondEffort") == "max"
        app.removeTranslator(translator)
        engine.retranslate()
        QTest.qWait(25)
        assert one.property("effortLabel") == "Mức"
        assert combo.property("currentText") == "Cao" and combo.property("currentValue") == "high"
        assert thinking.property("currentText") == "Bật"
        assert deepseek_effort.property("currentText") == "Tối đa"
        assert window.property("firstEffort") == "high" and window.property("secondEffort") == "max"
        assert not warnings, warnings
        window.close()


if __name__ == "__main__":
    exercise(int(sys.argv[1]))

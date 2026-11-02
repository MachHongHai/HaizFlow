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
    from PySide6.QtCore import Property, QByteArray, QObject, QUrl
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
        assert combo.property("currentText") == "Low"
        assert combo.property("currentValue") == "low"
        values, _ = QQmlExpression(engine.rootContext(), one, "values.join(',')").evaluate()
        assert values == "low,medium,high,xhigh,max"
        labels, _ = QQmlExpression(engine.rootContext(), one, "options.map(row => row.label).join(',')").evaluate()
        assert labels == "Low,Medium,High,Xhigh,Max"
        gemini = window.findChild(QQuickItem, "geminiReasoning")
        assert gemini.property("effortLabel") == "Mức"
        gemini_combo = gemini.findChild(QQuickItem, "translationReasoningEffortCombo")
        assert gemini_combo.property("currentText") == "Minimal"
        assert gemini_combo.property("currentValue") == "minimal"
        r1 = window.findChild(QQuickItem, "r1Reasoning")
        assert r1.isVisible()
        status = r1.findChild(QQuickItem, "translationReasoningMandatoryState")
        assert status.isVisible() and status.property("text") == "Enabled"
        assert not r1.findChild(QQuickItem, "translationReasoningEffortCombo").isVisible()
        assert not r1.findChild(QQuickItem, "translationThinkingTypeCombo").isVisible()
        assert combo.x() + combo.width() <= one.width() + 1
        model_changes = QSignalSpy(combo.modelChanged)
        combo.setProperty("currentIndex", 2)
        combo.activated.emit(2)
        QTest.qWait(25)
        assert window.property("firstEffort") == "high" and window.property("secondEffort") == ""
        thinking = two.findChild(QQuickItem, "translationThinkingTypeCombo")
        assert combo.property("currentText") == "High" and combo.property("currentValue") == "high"
        assert model_changes.count() == 0  # A selection never destroys/rebuilds the dropdown model.
        assert thinking.property("currentText") == "Disabled"
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
        assert deepseek_effort.property("currentText") == "Max"
        assert deepseek_effort.property("currentValue") == "max"
        one.setEnabled(False)
        assert not combo.isEnabled()
        one.setEnabled(True)
        snapshot = Path(__file__).parents[1] / "build" / f"translation-reasoning-{width}.png"
        snapshot.parent.mkdir(exist_ok=True)
        assert window.grabWindow().save(str(snapshot))
        assert not warnings, warnings
        window.close()


if __name__ == "__main__":
    exercise(int(sys.argv[1]))

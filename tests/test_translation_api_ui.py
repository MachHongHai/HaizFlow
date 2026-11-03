"""Real Qt rendering with private credentials, fake model lists and no paid requests."""
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.mark.parametrize("width,large", [(1000, False), (640, True)])
def test_credentials_only_settings_and_provider_scoped_project_models(width, large):
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(width), str(int(large))],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=35)
    assert result.returncode == 0, result.stdout + result.stderr


def exercise(width, large):
    from PySide6.QtCore import Property, QByteArray, QObject, Qt, QUrl, Signal, Slot
    from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlExpression
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    from haizflow.desktop.translation_api_controller import TranslationApiController
    from haizflow.services import translation_catalog_cache, translation_privacy
    from haizflow.services import translation_connections as connections
    from haizflow.services import translation_model_catalog as catalog

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication([])
    for name in ("SegUIVar.ttf", "segoeui.ttf", "SegoeIcons.ttf", "msyh.ttc"):
        font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont("Segoe UI", 14 if large else 11))

    class Host(QObject):
        apiKeySettingsRequested = Signal(str)
        apiKeyGuideRequested = Signal(str)
        geminiSetupRequested = Signal()
        _show_app_alert = Mock()

        def __init__(self):
            super().__init__()
            self.api = TranslationApiController(self)
            self.settings_requests = []

        @Slot(str)
        def requestApiKeySettings(self, provider):
            self.settings_requests.append(provider)

        @Slot(str, str, str, str, result=bool)
        def showProjectSessionAlertOnce(self, *_args):
            return True

        @Property(QObject, constant=True)
        def translationApi(self):
            return self.api

        @Property(str, constant=True)
        def zernioCredentialResult(self):
            return ""

        @Property(bool, constant=True)
        def zernioCredentialBusy(self):
            return False

        @Property("QVariantList", constant=True)
        def geminiApiKeys(self):
            return []

        @Property("QVariantList", constant=True)
        def zernioApiKeys(self):
            return []

    with tempfile.TemporaryDirectory(prefix="translation-ui-") as directory:
        connections._PATH = Path(directory) / "profiles.json"
        translation_catalog_cache._PATH = Path(directory) / "public-models.json"
        translation_privacy._PATH = Path(directory) / "consent.json"
        secrets = {}
        connections.secure_credentials.read_secret = lambda target: secrets.get(target, "")
        connections.secure_credentials.write_secret = lambda target, value, **_kwargs: secrets.__setitem__(
            target, value)
        connections.secure_credentials.delete_secret = lambda target: secrets.pop(target, None)
        host, engine = Host(), QQmlEngine()
        engine.rootContext().setContextProperty("AppController", host)
        messages = []
        engine.warnings.connect(lambda values: messages.extend(value.toString() for value in values))
        qml = Path(__file__).parents[1] / "src/haizflow/desktop/qml"
        component = QQmlComponent(engine)
        component.setData(QByteArray(b'''
            import QtQuick
            import QtQuick.Controls.Basic
            import "."
            ApplicationWindow {
                id: testWindow
                visible: true
                color: Theme.window
                property string selectedModel: "q4"
                ApiKeysPage { objectName: "apiPage"; anchors.fill: parent; anchors.margins: 24; provider: "openai" }
                TranslationModelCombo {
                    objectName: "apiModelCombo"
                    visible: false
                    selectedModel: testWindow.selectedModel
                    onEdited: function(value) { testWindow.selectedModel = value; }
                }
            }
        '''), QUrl.fromLocalFile(str(qml / "TranslationApiTest.qml")))
        assert component.isReady(), [error.toString() for error in component.errors()]
        window = component.create()
        window.setWidth(width)
        window.setHeight(850)
        QTest.qWait(100)
        page = window.findChild(QQuickItem, "apiPage")
        fields = {name: window.findChild(QQuickItem, "translationApi" + name + "Input")
                  for name in ("Name", "Secret", "Endpoint")}
        save = window.findChild(QQuickItem, "saveTranslationApiButton")
        assert fields["Name"].width() > 250 and not fields["Endpoint"].isVisible()
        assert window.findChild(QObject, "translationApiModelPicker") is None
        assert window.findChild(QObject, "translationApiModelInput") is None
        assert window.findChild(QObject, "loadTranslationApiModelsButton") is None
        echo, _ = QQmlExpression(engine.rootContext(), fields["Secret"], "Number(echoMode)").evaluate()
        assert echo == 2 and not save.isEnabled()
        for provider in ("deepseek", "openai", "custom", "openai", "deepseek", "openai"):
            fields["Secret"].setProperty("text", "must-not-follow-provider")
            page.setProperty("provider", provider)
            QTest.qWait(10)
            assert fields["Secret"].property("text") == ""
        identifiers = {}
        for provider in ("openai", "custom", "deepseek"):
            page.setProperty("provider", provider)
            QTest.qWait(20)
            fields["Name"].setProperty("text", provider + " key")
            fields["Secret"].setProperty("text", provider + "-private-key")
            if provider == "custom":
                fields["Endpoint"].setProperty("text", "https://example.com/v1")
            assert save.isEnabled()
            if provider == "openai":
                snapshot = Path(__file__).parents[1] / "build" / "translation-api-credentials-preview.png"
                snapshot.parent.mkdir(exist_ok=True)
                assert window.grabWindow().save(str(snapshot))
            save.clicked.emit()
            QTest.qWait(30)
            row = host.api.profiles[-1]
            assert row["provider"] == provider and row["model"] == ""
            identifiers[provider] = row["id"]
            assert fields["Secret"].property("text") == ""
        assert not host._show_app_alert.called
        combo = window.findChild(QQuickItem, "apiModelCombo")
        page.setVisible(False)
        combo.setVisible(True)
        combo.setX(width - 340 if large else 40)
        combo.setY(40)
        combo.setWidth(300 if large else 500)
        project_button = window.findChild(QQuickItem, "projectTranslationModelButton")
        project_button.clicked.emit()
        QTest.qWait(20)
        popup = window.findChild(QObject, "projectTranslationModelPopup")
        assert popup.property("visible")
        project_button.clicked.emit()
        QTest.qWait(20)
        assert not popup.property("visible")
        project_button.clicked.emit()
        QTest.qWait(20)

        def evaluate(expression):
            qml_expression = QQmlExpression(engine.rootContext(), combo, expression)
            result, _ = qml_expression.evaluate()
            assert not qml_expression.hasError(), qml_expression.error().toString()
            return result.toVariant() if hasattr(result, "toVariant") else result

        for provider in ("openai", "deepseek", "openai", "deepseek", "openai"):
            evaluate(f'openProvider("{provider}")')
            assert combo.property("activeConnection") == identifiers[provider]
            models = evaluate("modelOptions")
            assert models and all(row["value"].startswith("gpt-" if provider == "openai" else "deepseek-")
                                  for row in models)
        evaluate('openProvider("gemini")')
        QTest.qWait(20)
        assert popup.property("height") < (280 if large else 230)
        before = window.property("selectedModel")
        evaluate("choose(2)")  # The unavailable Gemini model stays unavailable.
        assert window.property("selectedModel") == before and popup.property("visible")
        snapshot = Path(__file__).parents[1] / "build" / (
            "translation-gemini-menu-narrow.png" if large else "translation-gemini-menu.png")
        assert window.grabWindow().save(str(snapshot))
        assert window.findChild(QQuickItem, "projectTranslationQuotaButton") is None
        window.findChild(QQuickItem, "projectTranslationBackButton").clicked.emit()
        assert combo.property("activeProvider") == ""
        evaluate('openProvider("openai")')
        for name in ("Back", "LoadModels", "ManageKey"):
            button = window.findChild(QQuickItem, "projectTranslation" + name + "Button")
            icon = button.findChild(QQuickItem, "buttonLeadingIcon")
            assert button.property("glyph") and icon.isVisible() and icon.height() > 0
            assert button.width() <= 30 and button.height() <= 30
        assert window.findChild(QQuickItem, "projectTranslationModelSearch") is None
        QTest.qWait(20)
        snapshot = Path(__file__).parents[1] / "build" / (
            "translation-project-models-narrow-preview.png" if large else "translation-project-models-preview.png")
        assert window.grabWindow().save(str(snapshot))
        evaluate('choose(modelOptions.findIndex(row => row.value === "gpt-6-luna"))')
        choice = "api:" + identifiers["openai"] + ":gpt-6-luna"
        assert window.property("selectedModel") == choice
        assert connections.get_connection(identifiers["openai"])["model"] == ""
        project_button.clicked.emit()
        QTest.qWait(20)
        evaluate('openProvider("openai")')
        entered, release = threading.Event(), threading.Event()

        def delayed(*_args, **_kwargs):
            entered.set()
            release.wait(2)
            return [{"value": "gpt-6.1-terra", "label": "Old OpenAI response"}], "ready"

        catalog.fetch_models = delayed
        window.findChild(QQuickItem, "projectTranslationLoadModelsButton").clicked.emit()
        assert entered.wait(1)
        evaluate('openProvider("deepseek")')
        release.set()
        QTest.qWait(80)
        assert all(row["value"].startswith("deepseek-") for row in evaluate("modelOptions"))
        assert window.property("selectedModel") == choice and host.api.catalogState == "idle"
        evaluate('openProvider("custom")')
        window.findChild(QQuickItem, "projectTranslationManualModelButton").clicked.emit()
        QTest.qWait(40)
        manual = window.findChild(QQuickItem, "projectTranslationManualModelInput")
        manual.setProperty("text", "vendor/Chosen:free")
        window.findChild(QQuickItem, "projectTranslationFormatCombo").setProperty("currentIndex", 2)
        window.findChild(QQuickItem, "projectTranslationApplyManualModelButton").clicked.emit()
        QTest.qWait(40)
        custom_choice = "api:" + identifiers["custom"] + ":vendor/Chosen:free#prompt"
        assert window.property("selectedModel") == custom_choice
        assert connections.resolve(custom_choice)["format"] == "prompt"
        assert connections.get_connection(identifiers["custom"])["format"] == "json_object"
        project_button.clicked.emit()
        QTest.qWait(20)
        evaluate('openProvider("openrouter")')
        window.findChild(QQuickItem, "projectTranslationSetupButton").clicked.emit()
        QTest.qWait(40)
        assert host.settings_requests == ["openrouter"] and window.property("selectedModel") == custom_choice
        assert len(connections.list_connections()) == 3
        assert host.api.addCredential("openrouter", "Router", "fake-router-key", "")
        QTest.qWait(20)
        project_button.clicked.emit()
        QTest.qWait(20)
        evaluate('openProvider("openrouter")')
        initial_models = evaluate("modelOptions")
        assert len(initial_models) > 30  # Bundled list is selectable without a network request.
        assert any(row.get("pricing_kind") == "free" for row in initial_models)
        assert any(row.get("pricing_kind") == "paid" for row in initial_models)
        free_count = sum(row.get("pricing_kind") == "free" for row in initial_models)
        assert all(row.get("pricing_kind") == "free" for row in initial_models[:free_count])
        free_names = [row["label"].casefold() for row in initial_models[:free_count]]
        assert free_names == sorted(free_names)
        router_id = next(row["id"] for row in connections.list_connections() if row["provider"] == "openrouter")
        private_choice = "api:" + router_id + ":nvidia/nemotron-3.5-super-vl:free"
        for dismiss in ("cancel", "close", "escape", "accept"):
            previous_choice = window.property("selectedModel")
            evaluate(f'commit("{private_choice}")')
            QTest.qWait(180)
            consent = window.findChild(QObject, "translationDataConsentDialog")
            assert consent is not None and consent.property("visible")
            assert window.property("selectedModel") == previous_choice
            if dismiss == "accept":
                snapshot = Path(__file__).parents[1] / "build" / f"translation-data-consent-{width}.png"
                assert window.grabWindow().save(str(snapshot))
                window.findChild(QQuickItem, "translationDataConsentAllow").clicked.emit()
            elif dismiss == "cancel":
                window.findChild(QQuickItem, "translationDataConsentCancel").clicked.emit()
            elif dismiss == "escape":
                QTest.keyClick(window, Qt.Key_Escape)
            else:
                consent.findChild(QQuickItem, "appDialogCloseButton").clicked.emit()
            QTest.qWait(180)
            assert window.property("selectedModel") == (private_choice if dismiss == "accept" else previous_choice)
            assert translation_privacy.allowed(connections.resolve(private_choice)) == (dismiss == "accept")
        window.setProperty("selectedModel", custom_choice)
        project_button.clicked.emit()
        QTest.qWait(20)
        evaluate('openProvider("openrouter")')
        last_choice = "api:" + router_id + ":" + initial_models[-1]["value"]
        window.setProperty("selectedModel", last_choice)
        evaluate('openProvider("openrouter")')
        model_list = window.findChild(QQuickItem, "projectTranslationModelList")
        assert model_list.property("currentIndex") == len(initial_models) - 1
        assert model_list.property("highlightMoveDuration") == 0
        assert model_list.property("contentY") > model_list.property("originY") + 100
        QTest.qWait(20)
        initial_position = model_list.property("contentY")
        QTest.qWait(400)
        assert abs(model_list.property("contentY") - initial_position) < 1, "Opening must not animate a slow scroll"
        assert window.property("selectedModel") == last_choice
        scroll = QQmlExpression(engine.rootContext(), model_list, 'positionViewAtBeginning()')
        scroll.evaluate()
        assert not scroll.hasError(), scroll.error().toString()
        QTest.qWait(20)
        assert abs(model_list.property("contentY") - model_list.property("originY")) < 1
        project_button.clicked.emit()
        QTest.qWait(20)
        project_button.clicked.emit()
        QTest.qWait(20)
        evaluate('openProvider("openrouter")')
        assert model_list.property("contentY") > model_list.property("originY") + 100
        QTest.qWait(20)
        reopened_position = model_list.property("contentY")
        QTest.qWait(400)
        assert abs(model_list.property("contentY") - reopened_position) < 1
        assert window.property("selectedModel") == last_choice
        window.setProperty("selectedModel", custom_choice)
        refresh = Mock(return_value=([
            {"value": "vendor/paid", "label": "A Paid model", "pricing_kind": "paid"},
            {"value": "vendor/unknown", "label": "B Unknown model", "pricing_kind": "unknown"},
            {"value": "vendor/free", "label": "Z Free model", "pricing_kind": "free"},
        ], "ready"))
        catalog.fetch_models = refresh
        window.findChild(QQuickItem, "projectTranslationLoadModelsButton").clicked.emit()
        for _ in range(60):
            QTest.qWait(10)
            if host.api.catalogState != "loading":
                break
        assert host.api.catalogState == "ready" and refresh.call_count == 1
        assert [row["value"] for row in evaluate("modelOptions")] == ["vendor/free", "vendor/paid", "vendor/unknown"]
        project_button.clicked.emit()  # Close; the request UI resets, cached models must remain.
        QTest.qWait(20)
        project_button.clicked.emit()
        QTest.qWait(20)
        evaluate('openProvider("openrouter")')
        QTest.qWait(30)
        assert {row["value"] for row in evaluate("modelOptions")} == {"vendor/free", "vendor/paid", "vendor/unknown"}
        assert evaluate("modelOptions")[0]["value"] == "vendor/free"
        assert refresh.call_count == 1
        def visual_items(item):
            yield item
            for child in item.childItems():
                yield from visual_items(child)

        pricing_labels = [item for item in visual_items(window.contentItem())
                          if item.objectName() == "openRouterModelPricingLabel" and item.isVisible()]
        actual_labels = {item.property("text") for item in pricing_labels}
        assert actual_labels == {"Miễn phí", "Tính phí", "Chưa rõ phí"}, actual_labels
        assert all(item.width() > 0 and item.height() > 0 for item in pricing_labels)
        paid_choice = "api:" + router_id + ":vendor/paid"
        window.setProperty("selectedModel", paid_choice)
        QTest.qWait(30)
        right_edges = [item.mapToItem(window.contentItem(), item.width(), 0).x() for item in pricing_labels]
        assert max(right_edges) - min(right_edges) < 1, "Selected checkmark must not shift the pricing column"
        snapshot = Path(__file__).parents[1] / "build" / (
            "translation-router-cache-narrow.png" if large else "translation-router-cache.png")
        assert window.grabWindow().save(str(snapshot))
        search = window.findChild(QQuickItem, "openRouterModelSearch")
        assert search.isVisible()
        for query, expected in (("FREE MODEL", "vendor/free"), ("vendor/paid", "vendor/paid")):
            search.setProperty("text", query)
            QTest.qWait(20)
            assert [row["value"] for row in evaluate("visibleOptions")] == [expected]
        search.setProperty("text", "missing-model")
        QTest.qWait(20)
        assert evaluate("visibleOptions") == [] and refresh.call_count == 1
        evaluate('openProvider("openai")')
        assert not search.isVisible()
        assert all(row["value"].startswith("gpt-") for row in evaluate("visibleOptions"))
        evaluate('openProvider("openrouter")')
        assert search.property("text") == "" and len(evaluate("visibleOptions")) == 3
        assert refresh.call_count == 1
        search.setProperty("text", "vendor/paid")
        QTest.qWait(20)
        search.accepted.emit()
        QTest.qWait(20)
        router_id = next(row["id"] for row in connections.list_connections() if row["provider"] == "openrouter")
        assert window.property("selectedModel") == "api:" + router_id + ":vendor/paid"
        assert connections.get_connection(router_id)["model"] == ""
        manual_choice = "api:" + router_id + ":0/unlisted:free"
        window.setProperty("selectedModel", manual_choice)
        project_button.clicked.emit()
        QTest.qWait(20)
        evaluate('openProvider("openrouter")')
        assert evaluate("modelOptions")[0]["value"] == "vendor/free"
        assert window.property("selectedModel") == manual_choice  # Sorting never changes the selection.
        assert not any(row["value"] == "0/unlisted:free" for row in evaluate("modelOptions"))
        for retired in ("deepseek/deepseek-r1:free", "deepseek/deepseek-r1-0528:free"):
            retired_choice = "api:" + router_id + ":" + retired
            window.setProperty("selectedModel", retired_choice)
            QTest.qWait(20)
            assert not any(row["value"] == retired for row in evaluate("modelOptions"))
            assert window.property("selectedModel") == retired_choice  # No silent switch to another model.
        assert refresh.call_count == 1  # Nor fetches pricing or models again.
        assert all(not any(error in message for error in ("Binding loop", "TypeError", "ReferenceError"))
                   for message in messages), messages
        window.close()


if __name__ == "__main__":
    exercise(int(sys.argv[1]), bool(int(sys.argv[2])))

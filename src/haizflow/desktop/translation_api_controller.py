"""Small credential UI facade; model-list verification never runs on the GUI thread."""
from __future__ import annotations

import threading
from copy import deepcopy

from PySide6.QtCore import Property, QObject, Signal, Slot

from haizflow.services import translation_connections as connections


class TranslationApiController(QObject):
    changed = Signal()
    _checked = Signal(str, str)
    catalogChanged = Signal()
    _catalogLoaded = Signal(int, object, str)

    def __init__(self, host):
        super().__init__(host)
        self.host = host
        self._busy_id = ""
        self._results = {}
        self._checked.connect(self._finish_check)
        self._catalog_generation = 0
        self._catalog_cancel = threading.Event()
        self._catalog_options = []
        self._catalog_state = "idle"
        self._catalog_connection = ""
        self._catalog_provider = ""
        from haizflow.services import translation_catalog_cache

        self._openrouter_options = translation_catalog_cache.load()
        self._reasoning_cache = {}
        self.changed.connect(self._invalidate_ui_caches)
        self.catalogChanged.connect(self._reasoning_cache.clear)
        self._catalogLoaded.connect(self._finish_catalog)

    def _invalidate_ui_caches(self):
        self._reasoning_cache.clear()
        self.catalogChanged.emit()

    @Property("QVariantList", notify=catalogChanged)
    def catalogOptions(self):
        return self._catalog_options

    @Property(str, notify=catalogChanged)
    def catalogState(self):
        return self._catalog_state

    @Property(str, notify=catalogChanged)
    def catalogConnection(self):
        return self._catalog_connection

    @Property(int, notify=catalogChanged)
    def reasoningRevision(self):
        return self._catalog_generation

    @Slot(str, str, bool, result="QVariantMap")
    @Slot(str, str, bool, int, result="QVariantMap")
    def reasoningConfiguration(self, choice, selected, has_guidance, _revision=0):
        from haizflow.services.translation_api_policy import project_configuration

        key = (choice, selected, has_guidance)
        if key not in self._reasoning_cache:
            if len(self._reasoning_cache) >= 128:
                self._reasoning_cache.clear()
            self._reasoning_cache[key] = project_configuration(choice, selected, has_guidance=has_guidance)
        return self._reasoning_cache[key]

    @Slot(str, result="QVariantList")
    def connectionModels(self, identifier):
        from haizflow.services.translation_model_catalog import presets

        try:
            profile = connections.get_connection(identifier)
        except ValueError:
            return []
        options = (deepcopy(self._openrouter_options) if profile["provider"] == "openrouter"
                   else presets(profile["provider"]))
        if (profile["provider"] != "openrouter" and profile["model"]
                and not any(row["value"] == profile["model"] for row in options)):
            options.insert(0, {"value": profile["model"], "label": profile["model"]})
        return options

    @Slot(str, str, result=str)
    @Slot(str, str, str, result=str)
    def modelChoice(self, identifier, model, output_format=""):
        try:
            original = connections.get_connection(identifier)
            suffix = "#" + output_format if output_format and original["provider"] == "custom" else ""
            choice = "api:" + identifier + ":" + model + suffix
            profile = connections.resolve(choice)
        except ValueError:
            return ""
        return "api:" + identifier if (original["model"], original["format"]) == (
            profile["model"], profile["format"]) else choice

    @Slot(str, result=str)
    def choiceLabel(self, choice):
        from haizflow.services.translation_model_catalog import PRESETS

        try:
            profile = connections.resolve(choice)
        except ValueError:
            return self.tr("Kết nối dịch không còn trên máy")
        provider = profile["provider"]
        label = self.tr("API tùy chỉnh") if provider == "custom" else connections.PROVIDERS[provider]["label"]
        model = dict(PRESETS.get(provider, ())).get(profile["model"], profile["model"])
        return f"{label} · {model}"

    @Slot(str)
    def loadConnectionModels(self, identifier):
        try:
            profile, key = connections.get_connection(identifier, with_key=True)
        except (ValueError, OSError):
            self.resetModels()
            self._catalog_connection = identifier
            self._catalog_state = "auth"
            self.catalogChanged.emit()
            return
        self.loadModels(profile["provider"], key, profile["base_url"])
        self._catalog_connection = identifier
        self.catalogChanged.emit()

    @Slot(str, result="QVariantList")
    def presetModels(self, provider):
        from haizflow.services.translation_model_catalog import presets

        options = presets(provider)
        if options:
            options[0]["label"] += " · " + self.tr("Tiết kiệm")
        return options

    @Slot()
    def resetModels(self):
        self._catalog_cancel.set()
        self._catalog_generation += 1
        self._catalog_cancel = threading.Event()
        self._catalog_options = []
        self._catalog_state = "idle"
        self._catalog_connection = ""
        self._catalog_provider = ""
        self.catalogChanged.emit()

    @Slot(str, str, str)
    def loadModels(self, provider, key, base_url):
        self.resetModels()
        self._catalog_provider = provider
        generation, cancelled = self._catalog_generation, self._catalog_cancel
        self._catalog_state = "loading"
        self.catalogChanged.emit()

        def work():
            from haizflow.services.translation_model_catalog import fetch_models

            try:
                options, state = fetch_models(provider, key, base_url, cancelled=cancelled)
            except Exception:
                options, state = [], "error"  # Never expose provider responses or credentials.
            if cancelled.is_set():
                return
            if provider == "openrouter" and state in {"ready", "partial"}:
                from haizflow.services import translation_catalog_cache

                options = translation_catalog_cache.store(options, state, cancelled=cancelled)
            if cancelled.is_set():
                return
            try:
                self._catalogLoaded.emit(generation, options, state)
            except RuntimeError:
                pass

        threading.Thread(target=work, name="HaizFlow model catalogue", daemon=True).start()

    @Slot(int, object, str)
    def _finish_catalog(self, generation, options, state):
        if generation != self._catalog_generation:
            return
        self._catalog_options = options
        if self._catalog_provider == "openrouter" and state in {"ready", "partial"}:
            self._openrouter_options = deepcopy(options)
        self._catalog_state = state
        self._reasoning_cache.clear()
        self.catalogChanged.emit()

    @Property("QVariantList", notify=changed)
    def profiles(self):
        return [{**row, "check_result": self._results.get(row["id"], ""),
                 "checking": self._busy_id == row["id"]} for row in connections.list_connections()]

    @Property("QVariantList", notify=changed)
    def modelOptions(self):
        rows, options = connections.list_connections(), []
        for provider, info in connections.PROVIDERS.items():
            provider_label = self.tr("API tùy chỉnh") if provider == "custom" else info["label"]
            matches = [row for row in rows if row["provider"] == provider]
            for row in matches:
                options.append({"label": f"{provider_label} · {row['model']} · {row['label']}",
                                "value": "api:" + row["id"]})
            if not matches:
                options.append({"label": provider_label + " · " + self.tr("Thêm API key"),
                                "value": "setup:" + provider})
        return options

    @Property(bool, notify=changed)
    def busy(self):
        return bool(self._busy_id)

    @Slot(str, str, str, str, str, str, result=bool)
    def add(self, provider, label, key, model, base_url, output_format):
        try:
            connections.add(provider, label, key, model, base_url, output_format)
        except (OSError, ValueError):
            self.host._show_app_alert(self.tr("Kết nối dịch"),
                self.tr("Không lưu được kết nối. Kiểm tra tên, API key và Base URL; "
                        "dùng HTTPS cho API từ xa."),
                "warning")
            return False
        self.changed.emit()
        return True

    @Slot(str, str, str, str, result=bool)
    def addCredential(self, provider, label, key, base_url):
        return self.add(provider, label, key, "", base_url, "json_object")

    @Slot(str, result=bool)
    def remove(self, identifier):
        if self._busy_id == identifier:
            return False
        try:
            removed = connections.remove(identifier)
        except (OSError, ValueError):
            self.host._show_app_alert(self.tr("Kết nối dịch"),
                                      self.tr("Không xóa được kết nối trên máy."), "warning")
            return False
        self._results.pop(identifier, None)
        self.changed.emit()
        return removed

    @Slot(str, result=bool)
    def verify(self, identifier):
        if self._busy_id:
            return False
        try:
            connections.get_connection(identifier)
        except ValueError:
            return False
        self._busy_id = identifier
        self._results[identifier] = "checking"
        self.changed.emit()

        def work():
            from haizflow.services.api_translation import check_connection

            try:
                result = check_connection("api:" + identifier, model_required=False)
            except (OSError, ValueError):
                result = "unavailable"
            try:
                self._checked.emit(identifier, result)
            except RuntimeError:
                pass

        threading.Thread(target=work, name="HaizFlow translation API check", daemon=True).start()
        return True

    @Slot(str, str)
    def _finish_check(self, identifier, result):
        if identifier != self._busy_id:
            return
        self._results[identifier] = result
        self._busy_id = ""
        self.changed.emit()

    @Slot(str)
    def guide(self, provider):
        from haizflow.desktop.external_links import open_external_url

        if provider in connections.PROVIDERS and connections.PROVIDERS[provider]["guide"]:
            open_external_url(connections.PROVIDERS[provider]["guide"])

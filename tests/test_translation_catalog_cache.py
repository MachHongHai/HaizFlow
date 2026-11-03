"""Public catalogue cache: immediate offline models, explicit refresh and safe fallback."""
import json
import threading
from unittest.mock import Mock

import pytest

from haizflow.services import translation_catalog_cache as cache
from haizflow.services import translation_model_catalog as catalog


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_PATH", tmp_path / "last.json")
    monkeypatch.setattr(cache, "_BUNDLED", tmp_path / "bundled.json")
    cache._BUNDLED.write_text(json.dumps({"version": 2, "options": [
        {"value": "vendor/seed", "label": "Seed", "pricing_kind": "free"}]}), "utf-8")


def test_bundled_catalogue_is_filtered_and_has_pricing_without_any_request(monkeypatch):
    monkeypatch.setattr(cache, "_PATH", cache._PATH.parent / "absent-catalogue-test.json")
    rows = cache.load()
    assert len(rows) > 30
    assert all(row.get("pricing_kind") in {"free", "paid", "unknown"} for row in rows)
    assert any(row["pricing_kind"] == "free" for row in rows)
    assert any(row["pricing_kind"] == "paid" for row in rows)
    assert cache.reasoning_for("deepseek/deepseek-r1-0528")["mandatory"] is True
    free = [row for row in rows if row["pricing_kind"] == "free"]
    assert len(free) >= 7 and all(row.get("output_format") for row in free)
    assert cache.format_for("google/gemma-4-31b-it:free") == "json_object"
    assert cache.format_for("liquid/lfm-2.5-2.6b:free") == "json_schema"
    assert not any(row["value"] == "deepseek/deepseek-r1:free" for row in rows)


def test_success_survives_restart_and_returns_independent_copies(isolated):
    cache.store([{"value": "vendor/fresh", "label": "Fresh", "pricing_kind": "paid",
                  "output_format": "json_object", "api_key": "PRIVATE"}], "ready")
    assert "PRIVATE" not in cache._PATH.read_text("utf-8")
    rows = cache.load()
    rows[0]["label"] = "Edited"
    cache._read_version.cache_clear()
    assert cache.load() == [{"value": "vendor/fresh", "label": "Fresh", "pricing_kind": "paid",
                             "output_format": "json_object"}]


def test_error_cancel_partial_and_full_refresh_preserve_the_right_models(isolated):
    assert cache.store([], "error")[0]["value"] == "vendor/seed"
    cancelled = threading.Event()
    cancelled.set()
    assert cache.store([{ "value": "vendor/cancelled"}], "ready", cancelled=cancelled)[0]["value"] == "vendor/seed"
    cache.store([{"value": "vendor/extra", "label": "Extra"}], "partial")
    assert {row["value"] for row in cache.load()} == {"vendor/seed", "vendor/extra"}
    cache.store([{"value": "vendor/replacement", "label": "Replacement"}], "ready")
    assert [row["value"] for row in cache.load()] == ["vendor/replacement"]


def test_broken_or_oversized_cache_falls_back_without_crashing(isolated):
    for body in ("broken json", "x" * (512 * 1024 + 1), json.dumps({"version": 2, "options": [
            {"value": "vendor/valid", "pricing_kind": ["bad"]}]})):
        cache._PATH.write_text(body, "utf-8")
        assert cache.load()


def test_legacy_public_cache_falls_back_to_new_seed_without_modifying_file(isolated):
    body = json.dumps({"version": 1, "options": [{"value": "vendor/old", "label": "Old"}]})
    cache._PATH.write_text(body, "utf-8")
    assert cache.load()[0]["value"] == "vendor/seed"
    assert cache._PATH.read_text("utf-8") == body


def test_retired_free_models_are_removed_from_existing_cache_and_partial_refresh(isolated):
    retired = [{"value": model, "label": model, "pricing_kind": "free"} for model in (
        "deepseek/deepseek-r1:free", "deepseek/deepseek-r1-0528:free")]
    cache._PATH.write_text(json.dumps({"version": 2, "options": [
        {"value": "vendor/active", "label": "Active"}, *retired]}), "utf-8")
    assert [row["value"] for row in cache.load()] == ["vendor/active"]
    cache.store(retired, "partial")
    assert [row["value"] for row in cache.load()] == ["vendor/active"]


def test_manual_model_can_use_shipped_format_when_missing_from_last_refresh(isolated):
    cache._BUNDLED.write_text(json.dumps({"version": 2, "options": [
        {"value": "vendor/seed", "output_format": "json_object"}]}), "utf-8")
    cache.store([{"value": "vendor/other", "output_format": "json_schema"}], "ready")
    assert cache.format_for("vendor/seed") == "json_object"
    assert cache.format_for("vendor/other") == "json_schema"
    assert cache.format_for("unknown/new:free") is None


def test_old_public_cache_is_enriched_with_new_protocol_hints_without_network(isolated):
    cache._BUNDLED.write_text(json.dumps({"version": 2, "options": [{"value": "vendor/model",
        "output_format": "json_schema", "context_length": 8192, "max_completion_tokens": 2048,
        "prompt_format": "user_only"}]}), "utf-8")
    cache.store([{"value": "vendor/model", "label": "Existing cached model"}], "ready")
    assert cache.protocol_for("vendor/model") == {"output_format": "json_schema", "context_length": 8192,
                                                 "max_completion_tokens": 2048, "prompt_format": "user_only"}
    cache.store([{"value": "vendor/model", "max_completion_tokens": 4096}], "ready")
    assert cache.protocol_for("vendor/model")["max_completion_tokens"] == 4096


def test_optional_reasoning_toggle_survives_cache_restart_and_legacy_missing_hints(isolated):
    row = {"value": "vendor/model", "reasoning_capabilities": {
        "values": ["disabled", "enabled"], "default": "disabled", "toggle": True}}
    cache._BUNDLED.write_text(json.dumps({"version": 2, "options": [row]}), "utf-8")
    cache.store([{"value": "vendor/model"}], "ready")
    assert cache.reasoning_for("vendor/model")["parameter"] == "reasoning.enabled"
    cache.store([row], "ready")
    cache._read_version.cache_clear()
    assert cache.reasoning_for("vendor/model") == {
        "parameter": "reasoning.enabled", **row["reasoning_capabilities"]}


def test_controller_uses_cached_openrouter_only_and_keeps_it_during_refresh(isolated, tmp_path, monkeypatch):
    from PySide6.QtCore import QObject
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest

    from haizflow.desktop.translation_api_controller import TranslationApiController
    from haizflow.services import translation_connections as connections

    app = QGuiApplication.instance() or QGuiApplication([])
    monkeypatch.setattr(connections, "_PATH", tmp_path / "profiles.json")
    monkeypatch.setattr(connections.secure_credentials, "write_secret", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(connections.secure_credentials, "read_secret", lambda *_args: "private")
    router = connections.add("openrouter", "Router", "private")
    other = connections.add("openai", "Other", "private")
    host = QObject()
    controller = TranslationApiController(host)
    send = Mock()
    monkeypatch.setattr(catalog, "fetch_models", send)
    assert controller.connectionModels(router)[0]["value"] == "vendor/seed"
    assert all(row["value"].startswith("gpt-") for row in controller.connectionModels(other))
    controller.resetModels()
    assert controller.connectionModels(router)[0]["value"] == "vendor/seed"
    send.assert_not_called()
    release = threading.Event()

    def fetch(*_args, **_kwargs):
        release.wait(2)
        return [{"value": "vendor/new", "label": "New", "pricing_kind": "paid"}], "ready"

    monkeypatch.setattr(catalog, "fetch_models", fetch)
    controller.loadConnectionModels(router)
    assert controller.catalogState == "loading"
    assert controller.connectionModels(router)[0]["value"] == "vendor/seed"
    release.set()
    for _ in range(50):
        QTest.qWait(10)
        if controller.catalogState != "loading":
            break
    assert controller.catalogState == "ready"
    controller.resetModels()
    assert controller.connectionModels(router)[0]["value"] == "vendor/new"
    restarted = TranslationApiController(host)
    assert restarted.connectionModels(router)[0]["value"] == "vendor/new"
    assert connections.get_connection(router)["model"] == ""  # Opening/refreshing never changes selection.
    legacy = connections.add("openrouter", "Legacy R1", "private", "deepseek/deepseek-r1:free")
    assert not any(row["value"] == "deepseek/deepseek-r1:free" for row in restarted.connectionModels(legacy))
    assert connections.get_connection(legacy)["model"] == "deepseek/deepseek-r1:free"
    app.processEvents()

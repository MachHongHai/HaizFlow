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
    assert {row["value"] for row in free} == {
        "dots-studio/dots-3-note-preview:free", "google/gemma-4-31b-it:free",
        "baidu/ernie-5.5-flash-preview:free", "inclusionai/ling-3.2-flash:free", "liquid/lfm-3-1.7b:free",
        "nvidia/nemotron-3.5-super-vl:free", "recursive/flint-v1.0:free", "particle-ai/particle-1:free",
    }
    assert cache.format_for("google/gemma-4-31b-it:free") == "json_object"
    assert cache.format_for("liquid/lfm-3-1.7b:free") == "json_schema"
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


def test_unstable_free_routes_are_removed_from_disk_cache_and_refresh(isolated):
    unstable = [{"value": model, "pricing_kind": "free"} for model in catalog._UNAVAILABLE_OPENROUTER_MODELS]
    cache._PATH.write_text(json.dumps({"version": 2, "options": [
        {"value": "vendor/active", "pricing_kind": "paid"}, *unstable]}), "utf-8")
    assert [row["value"] for row in cache.load()] == ["vendor/active"]
    assert [row["value"] for row in cache.store(unstable, "partial")] == ["vendor/active"]


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


def test_live_capabilities_replace_stale_reasoning_and_prompt_hints(isolated, monkeypatch):
    from haizflow.services import translation_reasoning_catalog as reasoning
    from haizflow.services.translation_api_policy import capabilities, request_options

    model = "openai/gpt-6.1-sol"  # A known fallback must not override explicit current metadata.
    monkeypatch.setattr(reasoning, "_PATH", cache._PATH.parent / "reasoning.json")
    stale = {"value": model, "prompt_format": "user_only", "reasoning_supported": True,
             "reasoning_capabilities": {"mandatory": True, "values": ["high"]}}
    cache._BUNDLED.write_text(json.dumps({"version": 2, "options": [stale]}), "utf-8")
    reasoning.remember([stale])
    cache.store([{"value": model, "parameters": ["max_tokens", "response_format"],
                  "reasoning_supported": False, "prompt_format": "system_user", "output_format": "json_object"}], "ready")
    hints = cache.protocol_for(model)
    assert hints["reasoning_supported"] is False and "reasoning_capabilities" not in hints
    assert hints["prompt_format"] == "system_user" and hints["output_format"] == "json_object"
    assert capabilities("openrouter", model) == {}
    assert request_options("openrouter", model) == {}
    with pytest.raises(ValueError):
        request_options("openrouter", model, "high")


def test_only_complete_live_cache_is_fresh_and_error_cannot_destroy_it(isolated, monkeypatch):
    monkeypatch.setattr(cache.time, "time", lambda: 100000)
    assert cache.needs_refresh()  # A shipped fallback, however recent, is not live data.
    cache.store([{"value": "vendor/live"}], "ready")
    assert not cache.needs_refresh()
    body = cache._PATH.read_text("utf-8")
    cache.store([], "error")
    assert cache._PATH.read_text("utf-8") == body and not cache.needs_refresh()
    monkeypatch.setattr(cache.time, "time", lambda: 100000 + cache.MAX_AGE)
    assert cache.needs_refresh()
    cache.store([{"value": "vendor/partial"}], "partial")
    assert cache.needs_refresh()
    assert {row["value"] for row in cache.load()} == {"vendor/live", "vendor/partial"}


def test_old_policy_cache_revalidates_even_if_recent_and_keeps_offline_rows(isolated):
    import time

    body = json.dumps({"version": 2, "fetched_at": time.time(), "options": [{"value": "vendor/old"}]})
    cache._PATH.write_text(body, "utf-8")
    assert cache.needs_refresh()
    assert cache.load()[0]["value"] == "vendor/old"
    assert cache._PATH.read_text("utf-8") == body


@pytest.mark.parametrize("stamp", [None, "12345", -1, 10**20])
def test_invalid_or_future_timestamp_does_not_disable_refresh(isolated, stamp):
    cache._PATH.write_text(json.dumps({"version": 2, "protocol_revision": cache._PROTOCOL_REVISION, "fetched_at": stamp,
                                      "options": [{"value": "vendor/cached"}]}), "utf-8")
    assert cache.needs_refresh()


def test_endpoint_checks_reuse_metadata_until_file_changes(isolated, monkeypatch):
    from pathlib import Path

    cache.store([{"value": "vendor/chat", "endpoints": ["/api/v1/chat/completions"]}], "ready")
    cache._metadata_version.cache_clear()
    original = Path.read_text
    reads = []
    def read(path, *args, **kwargs):
        reads.append(path)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", read)
    for _ in range(8):
        assert cache.chat_supported("vendor/chat") and not cache.needs_refresh()
    assert reads.count(cache._PATH) <= 2  # Metadata and cleaned catalogue, not every chunk or popup.
    cache.store([{"value": "vendor/new", "endpoints": ["/api/v1/chat/completions"]}], "ready")
    assert cache.chat_supported("vendor/new")


def test_incompatible_endpoints_are_hidden_from_old_cache_and_partial_merge(isolated):
    rows = [{"value": "vendor/batch:batch"}, {"value": "vendor/old", "endpoints": ["/api/v1/batches"]},
            {"value": "vendor/chat", "endpoints": ["/api/v1/chat/completions", "PRIVATE"]}]
    cache._PATH.write_text(json.dumps({"version": 2, "options": rows}), "utf-8")
    assert not cache.chat_supported("vendor/old")
    assert not cache.chat_supported("vendor/batch:batch")
    assert cache.chat_supported("vendor/chat")
    assert [row["value"] for row in cache.load()] == ["vendor/chat"]
    cache.store(rows, "partial")
    assert cache.protocol_for("vendor/chat")["endpoints"] == ["/api/v1/chat/completions"]
    assert "PRIVATE" not in cache._PATH.read_text("utf-8")


@pytest.fixture
def auto_controller(isolated, tmp_path, monkeypatch):
    from PySide6.QtCore import QObject
    from PySide6.QtGui import QGuiApplication

    from haizflow.desktop.translation_api_controller import TranslationApiController
    from haizflow.services import translation_connections as connections

    app = QGuiApplication.instance() or QGuiApplication([])
    monkeypatch.setattr(connections, "_PATH", tmp_path / "profiles.json")
    monkeypatch.setattr(connections.secure_credentials, "write_secret", lambda *_args, **_kwargs: None)
    # Public automatic refresh must not even retrieve the user's stored API key.
    monkeypatch.setattr(connections.secure_credentials, "read_secret", Mock(side_effect=AssertionError("No keys")))
    router = connections.add("openrouter", "Router", "private")
    other = connections.add("openai", "Other", "private")
    host = QObject()
    return app, host, TranslationApiController(host), router, other


def drain_until(predicate):
    from PySide6.QtTest import QTest
    for _ in range(100):
        QTest.qWait(10)
        if predicate():
            return
    assert predicate()


def test_auto_refresh_is_public_async_deduplicated_and_survives_popup_close(auto_controller, monkeypatch):
    app, host, controller, router, other = auto_controller
    entered, release = threading.Event(), threading.Event()
    def fetch(provider, key, **kwargs):
        assert provider == "openrouter" and key == ""
        entered.set()
        release.wait(2)
        return [{"value": "vendor/live", "pricing_kind": "free"}], "ready"
    request = Mock(side_effect=fetch)
    monkeypatch.setattr(catalog, "fetch_models", request)
    controller.ensureConnectionModels(other)
    request.assert_not_called()
    controller.ensureConnectionModels(router)
    assert entered.wait(1) and controller.routerRefreshing
    controller.ensureConnectionModels(router)
    assert request.call_count == 1
    assert controller.connectionModels(router)[0]["value"] == "vendor/seed"
    controller.resetModels()  # Closing a popup must not cancel the shared public cache.
    release.set()
    drain_until(lambda: not controller.routerRefreshing)
    assert controller.connectionModels(router)[0]["value"] == "vendor/live"
    assert controller.catalogState == "idle" and not cache.needs_refresh()
    assert controller.profiles[0]["model"] == ""
    controller.ensureConnectionModels(router)
    assert request.call_count == 1


def test_auto_refresh_failure_preserves_cache_and_backs_off(auto_controller, monkeypatch):
    app, host, controller, router, other = auto_controller
    clock = [500.0]
    monkeypatch.setattr("haizflow.desktop.translation_api_controller.time.monotonic", lambda: clock[0])
    request = Mock(return_value=([], "error"))
    monkeypatch.setattr(catalog, "fetch_models", request)
    controller.ensureConnectionModels(router)
    drain_until(lambda: not controller.routerRefreshing)
    assert controller.connectionModels(router)[0]["value"] == "vendor/seed"
    controller.ensureConnectionModels(router)
    assert request.call_count == 1
    clock[0] += 301
    controller.ensureConnectionModels(router)
    drain_until(lambda: not controller.routerRefreshing)
    assert request.call_count == 2


def test_auto_refresh_does_not_invalidate_unrelated_manual_discovery(auto_controller, monkeypatch):
    app, host, controller, router, other = auto_controller
    entered, release = threading.Event(), threading.Event()
    def fetch(provider, *_args, **_kwargs):
        if provider == "openrouter":
            entered.set()
            release.wait(2)
            return [{"value": "vendor/router"}], "ready"
        return [{"value": "gpt-test"}], "ready"
    monkeypatch.setattr(catalog, "fetch_models", fetch)
    controller.ensureConnectionModels(router)
    assert entered.wait(1)
    controller.loadModels("openai", "synthetic", "")
    drain_until(lambda: controller.catalogState != "loading")
    release.set()
    drain_until(lambda: not controller.routerRefreshing)
    assert controller.catalogState == "ready"
    assert controller.catalogOptions == [{"value": "gpt-test"}]
    assert controller.connectionModels(router)[0]["value"] == "vendor/router"


def test_manual_refresh_wins_over_late_public_refresh(auto_controller, monkeypatch):
    app, host, controller, router, other = auto_controller
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    def fetch(provider, key, *_args, **kwargs):
        if not key:
            entered.set()
            release.wait(2)
            finished.set()
            return [{"value": "vendor/old"}], "ready"
        return [{"value": "vendor/manual"}], "ready"
    monkeypatch.setattr(catalog, "fetch_models", fetch)
    controller.ensureConnectionModels(router)
    assert entered.wait(1)
    controller.loadModels("openrouter", "synthetic", "")  # Explicit reload bypasses backoff.
    drain_until(lambda: controller.catalogState != "loading")
    release.set()
    assert finished.wait(1)
    app.processEvents()
    assert [row["value"] for row in controller.catalogOptions] == ["vendor/manual"]
    assert [row["value"] for row in cache.load()] == ["vendor/manual"]


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

"""Global Settings credentials, legacy projects and exact per-key verification."""
import json
from unittest.mock import Mock

import pytest

from haizflow.core.translation_models import valid_translation_model
from haizflow.services import api_translation
from haizflow.services import translation_connections as connections


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(connections, "_PATH", tmp_path / "connections.json")
    secrets = {}
    monkeypatch.setattr(connections.secure_credentials, "read_secret", lambda target: secrets.get(target, ""))
    monkeypatch.setattr(connections.secure_credentials, "write_secret",
                        lambda target, value, **kwargs: secrets.__setitem__(target, value))
    monkeypatch.setattr(connections.secure_credentials, "delete_secret", lambda target: secrets.pop(target, None))
    return secrets


@pytest.mark.parametrize("provider", connections.PROVIDERS)
def test_global_key_switch_preserves_exact_model_for_new_and_old_projects(store, provider):
    first = connections.add(provider, "First", "key-first", "Vendor/Original:free", "https://first.invalid/v1")
    second = connections.add(provider, "Second", "key-second", "AnotherModel", "http://localhost:11434/v1")
    choices = [f"api:{provider}:Vendor/Original:free", f"api:{first}:Vendor/Original:free", f"api:{first}"]
    assert all(connections.resolve(choice, with_key=True)[1] == "key-first" for choice in choices)
    connections.select(second)
    for choice in choices:
        assert valid_translation_model(choice) == choice
        profile, key = connections.resolve(choice, with_key=True)
        assert key == "key-second" and profile["id"] == second
        assert profile["model"] == "Vendor/Original:free"
        if provider == "custom":
            assert profile["base_url"] == "http://localhost:11434/v1"
    rows = connections.list_connections()
    assert [row["id"] for row in rows if row["active"]] == [second]
    assert "key-first" not in connections._PATH.read_text("utf-8")
    assert "key-second" not in json.dumps(rows)


@pytest.mark.parametrize("provider", connections.PROVIDERS)
def test_remove_active_never_silently_falls_back_and_legacy_choice_survives(store, provider):
    first = connections.add(provider, "First", "key-first", "Original", "https://first.invalid/v1")
    second = connections.add(provider, "Second", "key-second", "Different", "https://second.invalid/v1")
    assert connections.remove(first)
    for choice in (f"api:{provider}:Original", f"api:{first}:Original", f"api:{first}"):
        with pytest.raises(ValueError, match="Chưa chọn API"):
            connections.resolve(choice, with_key=True)
    connections.select(second)
    for choice in (f"api:{first}:Original", f"api:{first}"):
        profile, key = connections.resolve(choice, with_key=True)
        assert profile["model"] == "Original" and key == "key-second"
    connections.add(provider, "Third", "key-third", "Other", "https://third.invalid/v1")
    assert connections.active_connection(provider)["id"] == second


def test_all_providers_have_independent_defaults_and_new_provider_selects_first(store):
    for provider in connections.PROVIDERS:
        first = connections.add(provider, provider, "first", base_url="http://localhost:11434/v1")
        connections.add(provider, "Backup", "second", base_url="http://localhost:11435/v1")
        assert connections.active_connection(provider)["id"] == first
    assert sum(row["active"] for row in connections.list_connections()) == 4


def test_legacy_index_migrates_deterministically_and_persists_explicit_selection(store):
    first = connections.add("openai", "First", "first")
    second = connections.add("openai", "Second", "second")
    payload = json.loads(connections._PATH.read_text("utf-8"))
    connections._PATH.write_text(json.dumps({"version": 1, "connections": payload["connections"]}), "utf-8")
    assert connections.active_connection("openai")["id"] == first
    connections.select(second)
    assert json.loads(connections._PATH.read_text("utf-8"))["active"]["openai"] == second
    assert connections.active_connection("openai")["id"] == second


def test_selection_is_atomic_and_missing_secret_does_not_change_default(store, monkeypatch):
    first = connections.add("openai", "First", "first")
    second = connections.add("openai", "Second", "second")
    store.pop(connections._target(second))
    with pytest.raises(ValueError):
        connections.select(second)
    assert connections.active_connection("openai")["id"] == first
    store[connections._target(second)] = "second"
    before = connections._PATH.read_bytes()
    monkeypatch.setattr(connections.os, "replace", Mock(side_effect=OSError("disk full")))
    with pytest.raises(OSError):
        connections.select(second)
    assert connections._PATH.read_bytes() == before


def test_inference_snapshots_key_once_but_verification_checks_exact_row(store, monkeypatch):
    first = connections.add("openrouter", "First", "first")
    second = connections.add("openrouter", "Second", "second")
    connections.select(second)
    monkeypatch.setattr("haizflow.services.translation_model_guard.prepare", lambda *args, **kwargs: None)
    run = Mock(return_value=["Xin chào"])
    monkeypatch.setattr(api_translation.gemini_translation, "translate_texts", run)
    api_translation.translate_texts(["Hello"], model=f"api:{first}:Vendor/Chosen:free")
    assert run.call_args.kwargs["_key"] == "second"
    request = Mock(return_value={"data": {"label": "First"}})
    monkeypatch.setattr(api_translation, "_json_request", request)
    assert api_translation.check_connection(f"api:{first}", model_required=False) == "verified"
    assert request.call_args.args[1] == "first"


def test_official_key_switch_keeps_cache_but_custom_endpoint_switch_invalidates(store):
    for provider in ("openai", "custom"):
        connections.add(provider, "First", "first", base_url="https://first.invalid/v1")
        second = connections.add(provider, "Second", "second", base_url="https://second.invalid/v1")
        choice = f"api:{provider}:Vendor/Chosen"
        before = connections.signature_parts(choice)
        connections.select(second)
        assert (before == connections.signature_parts(choice)) == (provider == "openai")


def test_deleted_default_stays_deselected_when_adding_replacement(store):
    first = connections.add("openai", "First", "first")
    connections.remove(first)
    replacement = connections.add("openai", "Replacement", "second")
    with pytest.raises(ValueError, match="Chưa chọn API"):
        connections.active_connection("openai")
    connections.select(replacement)
    assert connections.active_connection("openai")["id"] == replacement


def test_missing_active_secret_never_uses_backup(store):
    active = connections.add("openai", "Active", "first")
    connections.add("openai", "Backup", "second")
    store.pop(connections._target(active))
    with pytest.raises(ValueError, match="Không tìm thấy API key"):
        connections.resolve("api:openai:ExactModel", with_key=True)


@pytest.mark.parametrize("bad", [None, [], {"model": 123, "format": "prompt"},
                                  {"model": "Original", "format": []}])
def test_invalid_legacy_metadata_is_reported_without_selecting_another_model(store, bad):
    identifier = connections.add("openai", "First", "first", "Original")
    backup = connections.add("openai", "Backup", "second", "Different")
    connections.remove(identifier)
    connections.select(backup)
    payload = json.loads(connections._PATH.read_text("utf-8"))
    payload["legacy_models"][identifier] = bad
    connections._PATH.write_text(json.dumps(payload), "utf-8")
    with pytest.raises(ValueError, match="Chưa chọn model"):
        connections.resolve(f"api:{identifier}")

"""Data-sharing consent is explicit, scoped, local and fail-closed."""
import json
from unittest.mock import Mock

import pytest

from haizflow.services import translation_privacy as privacy


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(privacy, "_PATH", tmp_path / "consent.json")


def profile(model="nvidia/nemotron-3.5-super-vl:free", identifier="a" * 32, provider="openrouter"):
    return {"id": identifier, "provider": provider, "model": model, "key": "PRIVATE"}


def test_consent_survives_restart_but_never_follows_another_model_connection_or_provider():
    current = profile()
    assert privacy.required(current) and not privacy.allowed(current)
    privacy.grant(current)
    assert privacy.allowed(current)
    assert not privacy.allowed(profile(identifier="b" * 32))
    assert not privacy.allowed(profile("liquid/lfm-2.5-2.6b:free"))
    assert not privacy.allowed(profile(provider="custom"))
    assert not privacy.required(profile("dots-studio/dots-3-note-preview:free"))
    assert "PRIVATE" not in privacy._PATH.read_text("utf-8")
    privacy.forget(current["id"])
    assert not privacy.allowed(current)


@pytest.mark.parametrize("body", ["broken", "[]", '{"version":2,"grants":[]}',
                                  '{"version":1,"grants":null}', "x" * (256 * 1024 + 1)],
                         ids=["broken", "array", "wrong-version", "null-grants", "oversized"])
def test_broken_or_oversized_consent_never_enables_data_collection(body):
    privacy._PATH.write_text(body, "utf-8")
    assert not privacy.allowed(profile())


@pytest.mark.parametrize("current", [profile(identifier="bad"), profile(provider="custom"),
                                     profile("vendor/unlisted:free")])
def test_only_supported_model_connection_scopes_can_be_granted(current):
    with pytest.raises(ValueError):
        privacy.grant(current)
    assert not privacy._PATH.exists()


def test_failed_save_does_not_create_consent_or_damage_an_existing_grant(monkeypatch):
    privacy.grant(profile())
    previous = privacy._PATH.read_bytes()
    monkeypatch.setattr(privacy, "atomic_json", Mock(side_effect=OSError("disk full")))
    with pytest.raises(OSError):
        privacy.grant(profile("liquid/lfm-2.5-2.6b:free"))
    assert privacy._PATH.read_bytes() == previous
    assert not privacy.allowed(profile("liquid/lfm-2.5-2.6b:free"))


def test_grants_are_bounded():
    privacy._PATH.write_text(json.dumps({"version": 1, "grants": [
        f"{index:032x}:nvidia/nemotron-3.5-super-vl:free" for index in range(1000)]}), "utf-8")
    with pytest.raises(ValueError):
        privacy.grant(profile())

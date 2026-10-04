from unittest.mock import patch

import pytest

from haizflow.services import zernio_keys


@pytest.fixture
def credentials(tmp_path):
    values = {}
    def write(target, secret, **kwargs):
        values[target] = secret
    def delete(target):
        return values.pop(target, None) is not None
    with (patch.object(zernio_keys, "INDEX_PATH", tmp_path / "keys.json"),
          patch.object(zernio_keys.secure_credentials, "read_secret", side_effect=lambda target: values.get(target, "")),
          patch.object(zernio_keys.secure_credentials, "write_secret", side_effect=write),
          patch.object(zernio_keys.secure_credentials, "delete_secret", side_effect=delete)):
        yield values


def test_legacy_key_remains_available_and_secrets_never_enter_metadata(credentials):
    credentials[zernio_keys.CREDENTIAL_TARGET] = "old-secret"
    assert zernio_keys.list_keys() == [{"id": "legacy", "label": "Zernio", "active": True}]
    key_id = zernio_keys.add_named_key("Team", "team-secret")
    assert zernio_keys.active_key() == "team-secret"
    assert len(zernio_keys.list_keys()) == 2
    metadata = zernio_keys.INDEX_PATH.read_text(encoding="utf-8")
    assert "secret" not in metadata
    zernio_keys.select_key("legacy")
    assert zernio_keys.active_key() == "old-secret"
    zernio_keys.select_key(key_id)
    assert zernio_keys.active_id() == key_id


def test_removing_active_key_does_not_silently_choose_another(credentials):
    first = zernio_keys.add_named_key("First", "one")
    second = zernio_keys.add_named_key("Second", "two")
    assert zernio_keys.remove_key(second)
    assert zernio_keys.active_key() == ""
    assert zernio_keys.list_keys() == [{"id": first, "label": "First", "active": False}]


def test_failed_metadata_save_rolls_back_new_secret_and_keeps_active_key(credentials):
    first = zernio_keys.add_named_key("First", "one")
    with patch.object(zernio_keys, "_save", side_effect=OSError("full disk")):
        with pytest.raises(OSError):
            zernio_keys.add_named_key("Second", "two")
    assert zernio_keys.active_id() == first
    assert list(credentials.values()) == ["one"]


def test_delete_storage_failure_restores_secret(credentials):
    key_id = zernio_keys.add_named_key("First", "one")
    with patch.object(zernio_keys, "_save", side_effect=OSError("full disk")):
        with pytest.raises(OSError):
            zernio_keys.remove_key(key_id)
    assert zernio_keys.active_key() == "one"


def test_unknown_or_missing_key_cannot_become_active(credentials):
    key_id = zernio_keys.add_named_key("First", "one")
    credentials.clear()
    with pytest.raises(ValueError):
        zernio_keys.select_key(key_id)
    with pytest.raises(ValueError):
        zernio_keys.select_key("../../not-a-key")


@pytest.mark.parametrize("label", ["", " ", "a" * 65])
def test_invalid_label_is_rejected_without_saving(credentials, label):
    with pytest.raises(ValueError):
        zernio_keys.add_named_key(label, "secret")
    assert not credentials

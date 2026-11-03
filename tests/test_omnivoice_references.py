import hashlib
import json
import math
import wave
from array import array

import pytest

from haizflow.pipeline import omnivoice_references as refs


def bank(tmp_path, language="vi", voice="omnivoice:male"):
    clip = tmp_path / f"{language}.wav"
    with wave.open(str(clip), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(24000)
        stream.writeframes(array("h", (int(3000 * math.sin(i * .05)) for i in range(96000))).tobytes())
    entry = dict(voice=voice, language=language, text="Một câu đầy đủ.", path=clip.name,
                 sha256=hashlib.sha256(clip.read_bytes()).hexdigest(),
                 verification=dict(waveform_valid=True, character_error_rate=0))
    catalog = {"schema_version": 1, "references": {f"{voice}/{language}": entry}}
    (tmp_path / "manifest.json").write_text(json.dumps(catalog), encoding="utf-8")
    return catalog, entry, clip


def save(tmp_path, catalog):
    (tmp_path / "manifest.json").write_text(json.dumps(catalog), encoding="utf-8")


def test_reference_requires_exact_preset_language_and_matched_transcript(tmp_path):
    _, entry, clip = bank(tmp_path)
    assert refs.prepared_reference("omnivoice:male", "vi", root=tmp_path) == (str(clip), entry["text"])
    assert refs.prepared_reference("omnivoice:female", "vi", root=tmp_path) == ("", "")
    assert refs.prepared_reference("omnivoice:male", "ja", root=tmp_path) == ("", "")
    assert refs.prepared_reference("../outside", "vi", root=tmp_path) == ("", "")


def test_reference_rejects_changed_waveform_even_if_manifest_is_cached(tmp_path):
    _, _, clip = bank(tmp_path)
    assert refs.prepared_reference("omnivoice:male", "vi", root=tmp_path)[0]
    content = clip.read_bytes()
    clip.write_bytes(content[:-2] + b"\x01\x01")
    assert refs.prepared_reference("omnivoice:male", "vi", root=tmp_path) == ("", "")


def test_bad_quality_metadata_cannot_select_an_asset(tmp_path):
    catalog, entry, _ = bank(tmp_path)
    for quality in ({}, None, [], {"waveform_valid": True, "character_error_rate": .06},
                    {"waveform_valid": True, "character_error_rate": float("nan")},
                    {"waveform_valid": True, "character_error_rate": -1}):
        entry["verification"] = quality
        save(tmp_path, catalog)
        assert refs.prepared_reference("omnivoice:male", "vi", root=tmp_path) == ("", "")


def test_absolute_or_traversal_path_cannot_escape_bank(tmp_path):
    root = tmp_path / "bank"
    root.mkdir()
    catalog, entry, clip = bank(root)
    outside = tmp_path / "outside.wav"
    outside.write_bytes(clip.read_bytes())
    for path in ("../outside.wav", str(outside)):
        entry["path"] = path
        save(root, catalog)
        assert refs.prepared_reference("omnivoice:male", "vi", root=root) == ("", "")


def test_reference_duration_is_checked_without_models(tmp_path):
    catalog, entry, clip = bank(tmp_path)
    with wave.open(str(clip), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(24000)
        stream.writeframes(bytes(24000 * 2))
    entry["sha256"] = hashlib.sha256(clip.read_bytes()).hexdigest()
    save(tmp_path, catalog)
    assert refs.prepared_reference("omnivoice:male", "vi", root=tmp_path) == ("", "")


def test_warm_cache_identity_tracks_transcript_and_asset_replacement(tmp_path):
    _, _, clip = bank(tmp_path)
    before = refs.reference_identity(str(clip), "Original")
    assert refs.reference_identity(str(clip), "Corrected") != before
    clip.write_bytes(clip.read_bytes() + b"\x00\x00")
    assert refs.reference_identity(str(clip), "Original") != before


def test_corrupt_manifest_is_optional_not_a_synthesis_error(tmp_path):
    for content in ("{", "[]", '{"schema_version":1,"references":[]}'):
        (tmp_path / "manifest.json").write_text(content, encoding="utf-8")
        assert refs.prepared_reference("omnivoice:male", "vi", root=tmp_path) == ("", "")


@pytest.mark.parametrize("language", sorted(refs.REFERENCE_LANGUAGES))
@pytest.mark.parametrize("preset", ["omnivoice:male", "omnivoice:female"])
def test_approved_assets_are_installed_and_selected_for_the_requested_language(preset, language):
    from haizflow.pipeline.omnivoice_tts import _preset_reference

    expected = refs.prepared_reference(preset, language)
    assert expected[0], f"Approved reference missing or corrupt: {preset}/{language}"
    assert _preset_reference(preset, language) == expected
    assert expected[0].endswith(f"{language}.wav")
    assert preset.replace(":", "_") in expected[0]
    assert expected[1]


def test_invalid_prepared_asset_falls_back_to_own_preset_not_another_speaker(monkeypatch):
    from haizflow.pipeline.omnivoice_tts import _preset_reference

    monkeypatch.setattr(refs, "_verified_wav", lambda *args: False)
    for preset in ("omnivoice:male", "omnivoice:female"):
        path, text = _preset_reference(preset, "ko")
        assert path.endswith("en.mp3") and preset.replace(":", "_") in path
        assert "This app" in text


def test_packaging_includes_every_approved_reference():
    import glob
    import tomllib
    from pathlib import Path

    project = Path(__file__).resolve().parents[1]
    configuration = tomllib.loads((project / "pyproject.toml").read_text("utf-8"))
    patterns = configuration["tool"]["setuptools"]["package-data"]["haizflow.desktop"]
    package = project / "src/haizflow/desktop"
    included = {str(Path(path).resolve()) for pattern in patterns
                for path in glob.glob(str(package / pattern), recursive=True)}
    manifest = refs.REFERENCE_ROOT / "manifest.json"
    assert str(manifest.resolve()) in included
    catalog = json.loads(manifest.read_text("utf-8"))["references"]
    assert len(catalog) == 12
    for entry in catalog.values():
        assert str((refs.REFERENCE_ROOT / entry["path"]).resolve()) in included

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_binding(name: str, symbols: list[bytes]):
    entry = SimpleNamespace(dll=name.encode(), struct=SimpleNamespace(Name=8),
                            imports=[SimpleNamespace(name=symbol) for symbol in symbols])
    binding = SimpleNamespace(DIRECTORY_ENTRY_IMPORT=[entry],
                              get_offset_from_rva=lambda value: value, parse_data_directories=lambda **_: None)
    # Special methods must be on the type, not assigned only to an instance.
    return type("Context", (), {"__enter__": lambda self: binding, "__exit__": lambda *args: None})()


def test_import_redirection_keeps_file_size_and_checks_symbols(tmp_path):
    module = load("package-engine-media")
    file = tmp_path / "binding.pyd"
    original = "avcodec-62-0123456789abcdef.dll"
    file.write_bytes(b"header00" + original.encode() + b"\0tail")
    with patch.object(module.pefile, "PE", return_value=fake_binding(original, [b"avcodec_send_packet"])), \
            patch.object(module, "export_symbols", return_value=frozenset({b"avcodec_send_packet"})):
        content, changes = module.patch_imports(file, {"avcodec-62.dll": tmp_path / "avcodec-62.dll"})
    assert len(content) == file.stat().st_size
    assert content[8:].startswith(b"avcodec-62.dll\0")
    assert content.endswith(b"tail")
    assert changes == [{"original": original, "replacement": "avcodec-62.dll"}]


def test_missing_replacement_abi_is_rejected_before_mutation(tmp_path):
    module = load("package-engine-media")
    file = tmp_path / "binding.pyd"
    file.write_bytes(b"unchanged")
    with patch.object(module.pefile, "PE", return_value=fake_binding("avcodec-62-vendor.dll", [])):
        # Non-media names are deliberately left alone, never blindly rewritten.
        assert module.patch_imports(file, {}) == (b"unchanged", [])
    with patch.object(module.pefile, "PE", return_value=fake_binding("avcodec-62-0123.dll", [b"missing"])), \
            patch.object(module, "export_symbols", return_value=frozenset()), \
            pytest.raises(ValueError, match="ABI misses"):
        module.patch_imports(file, {"avcodec-62.dll": tmp_path / "replacement.dll"})
    assert file.read_bytes() == b"unchanged"


def test_engine_packaging_never_targets_a_user_installation(tmp_path):
    module = load("package-engine-media")
    with patch.object(module, "ROOT", tmp_path), pytest.raises(ValueError, match="generated engine"):
        module.package(tmp_path / "HaizFlow-Test", tmp_path / "inputs")


def test_native_input_tampering_is_detected(tmp_path):
    module = load("install-built-ffmpeg")
    inputs = tmp_path / "inputs"
    (inputs / "bin").mkdir(parents=True)
    (inputs / "bin/ffmpeg.exe").write_bytes(b"changed")
    (inputs / "closure.json").write_text(json.dumps(dict(variant="haizflow", version="8.1.2",
        binaries=[dict(file="ffmpeg.exe", sha256="0" * 64, size=7)], sources=[])), encoding="utf-8")
    with pytest.raises(ValueError, match="differs"):
        module.validate(inputs)


def test_source_bundle_requires_generated_output_path(tmp_path):
    module = load("build-third-party-sources")
    with patch.object(module, "ROOT", tmp_path), pytest.raises(ValueError, match="below dist"):
        module.build(tmp_path / "projects/source.zip")

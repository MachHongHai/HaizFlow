from __future__ import annotations

import importlib
import json
import stat
from collections.abc import Mapping
from functools import wraps
from pathlib import Path
from types import ModuleType
from typing import Any


_LIGHTNING_SAVING_MODULES = (
    "lightning.pytorch.core.saving",
    "pytorch_lightning.core.saving",
)
_TRUSTED_LIGHTNING_INSTANTIATORS = frozenset(
    {
        "lightning.pytorch.cli.instantiate_module",
        "pytorch_lightning.cli.instantiate_module",
    }
)
_GUARD_MARKER = "__haizflow_instantiator_guard__"


def validate_checkpoint_weight_maps(model_directory: str | Path) -> tuple[Path, ...]:
    """Reject unsafe shard paths before Accelerate can open a checkpoint.

    CVE-2026-69112 affects Accelerate's handling of caller-controlled
    ``weight_map`` values. HaizFlow only loads verified local model packs, but
    validating every index at the process boundary also protects a damaged or
    incorrectly assembled pack before third-party loading code sees it.
    """
    root = Path(model_directory).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"Model directory is not a directory: {root}")

    checked: list[Path] = []
    for index_path in sorted(root.glob("*.index.json")):
        if index_path.is_symlink() or not stat.S_ISREG(index_path.stat(follow_symlinks=False).st_mode):
            raise ValueError(f"Checkpoint index must be a regular file: {index_path.name}")
        try:
            payload = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Checkpoint index is unreadable: {index_path.name}") from exc
        weight_map = payload.get("weight_map")
        if not isinstance(weight_map, Mapping):
            raise ValueError(f"Checkpoint index has no valid weight_map: {index_path.name}")
        for shard_value in weight_map.values():
            if not isinstance(shard_value, str) or not shard_value.strip():
                raise ValueError(f"Checkpoint index contains an invalid shard name: {index_path.name}")
            shard_name = Path(shard_value)
            if shard_name.is_absolute() or shard_name.name != shard_value:
                raise ValueError(f"Checkpoint shard escapes the model directory: {shard_value!r}")
            shard_path = (root / shard_name).resolve(strict=True)
            if shard_path.parent != root or shard_path.is_symlink():
                raise ValueError(f"Checkpoint shard escapes the model directory: {shard_value!r}")
            if not stat.S_ISREG(shard_path.stat(follow_symlinks=False).st_mode):
                raise ValueError(f"Checkpoint shard must be a regular file: {shard_value!r}")
            checked.append(shard_path)
    return tuple(dict.fromkeys(checked))


def _checkpoint_instantiators(cls: type[Any], checkpoint: Mapping[str, Any], overrides: Mapping[str, Any]):
    """Yield every import path that Lightning could treat as an instantiator."""
    candidates: list[Any] = [overrides]
    hyper_parameters_key = getattr(cls, "CHECKPOINT_HYPER_PARAMS_KEY", "hyper_parameters")
    for key in ("hparams", "module_arguments", hyper_parameters_key):
        value = checkpoint.get(key)
        if isinstance(value, Mapping):
            candidates.append(value)

    for candidate in candidates:
        instantiator = candidate.get("_instantiator")
        if instantiator is not None:
            yield str(instantiator)


def _guard_lightning_saving_module(module: ModuleType) -> bool:
    """Backport Lightning's upstream checkpoint instantiator allowlist."""
    original = getattr(module, "_load_state", None)
    if original is None or getattr(original, _GUARD_MARKER, False):
        return False

    # Lightning versions containing the upstream fix already enforce this
    # allowlist themselves. Do not wrap them a second time.
    if hasattr(module, "_ALLOWED_INSTANTIATORS"):
        return False

    @wraps(original)
    def guarded_load_state(cls, checkpoint, strict=None, **cls_kwargs_new):
        if not isinstance(checkpoint, Mapping):
            raise TypeError("Lightning checkpoint must be a mapping")
        for instantiator in _checkpoint_instantiators(cls, checkpoint, cls_kwargs_new):
            if instantiator not in _TRUSTED_LIGHTNING_INSTANTIATORS:
                raise ValueError(
                    f"The instantiator {instantiator!r} from the checkpoint is not trusted and was blocked "
                    "to prevent arbitrary code execution."
                )
        return original(cls, checkpoint, strict=strict, **cls_kwargs_new)

    setattr(guarded_load_state, _GUARD_MARKER, True)
    module._load_state = guarded_load_state
    return True


def install_lightning_checkpoint_guard() -> tuple[str, ...]:
    """Install the CVE-2026-58659 guard before HaizFlow loads any checkpoint.

    Lightning 2.6.5 is the newest compatible release at the time of writing,
    while its upstream fix has not yet shipped. This function mirrors that
    fix and becomes a no-op automatically once the dependency provides it.
    """
    guarded: list[str] = []
    for module_name in _LIGHTNING_SAVING_MODULES:
        module = importlib.import_module(module_name)
        if _guard_lightning_saving_module(module):
            guarded.append(module_name)
    return tuple(guarded)

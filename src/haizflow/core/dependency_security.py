from __future__ import annotations

import importlib
from collections.abc import Mapping
from functools import wraps
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

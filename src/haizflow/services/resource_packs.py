"""Independent AI resource packs for the small HaizFlow Core application."""

from __future__ import annotations

import hashlib
import configparser
import importlib.metadata
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from pathlib import Path

from haizflow.core.model_integrity import (
    ALIGNMENT_MODELS,
    HYMT2_CPU_FILE,
    verify_alignment_model,
    verify_cpu_model,
    verify_demucs_model,
    verify_gpu_model,
    verify_omnivoice_model,
    verify_omnivoice_sdk,
    verify_subtitle_ocr_models,
    verify_whisper_model,
    verify_whisper_turbo_model,
    verify_whisperx_vad_model,
)
from haizflow.core.paths import (
    engines_dir,
    install_root,
    models_dir,
    resource_packages_dir,
    resource_storage_dir,
    resource_storage_pointer_path,
)
from haizflow.core.storage_policy import MINIMUM_OPERATIONAL_FREE_BYTES
from haizflow.core.resource_archive import ArchivePart, archive_matches, join_archive_parts, parse_archive_parts
from haizflow.services.model_bootstrap import (
    ModelAsset,
    ModelBootstrapCancelled,
    ModelProgress,
    install_model_assets,
    required_assets,
)

PACK_PROTOCOL_VERSION = 1
RESOURCE_STATE_VERSION = 1


def _speaker_asset() -> ModelAsset:
    from haizflow.pipeline.speaker_identity import MODEL_FILE, MODEL_SHA256, MODEL_SIZE, MODEL_URL

    return ModelAsset("speaker-identification", "Nhận diện người nói", MODEL_URL,
                      f"speaker-identification/{MODEL_FILE}", MODEL_SIZE, MODEL_SHA256)


ENGINE_REQUIRED_COMMANDS = {
    "engine-cpu-py313": {
        "smoke_command",
        "rpc_command",
        "hymt2_server",
        "omnivoice_worker",
        "omnivoice_server",
        "demucs",
        "demucs_task",
        "transcribe",
        "runtime_probe",
    },
    "engine-cuda128-py313": {
        "smoke_command",
        "rpc_command",
        "hymt2_server",
        "omnivoice_worker",
        "omnivoice_server",
        "demucs",
        "demucs_task",
        "transcribe",
        "runtime_probe",
    },
    "engine-vision-onnx": {"smoke_command", "rpc_command", "subtitle_ocr"},
}
ENGINE_PROFILE_BY_PACK = {
    "engine-cpu-py313": "cpu",
    "engine-cuda128-py313": "cuda128",
    "engine-vision-onnx": "vision",
}


@dataclass(frozen=True)
class ResourcePackDefinition:
    pack_id: str
    label: str
    group: str
    version: str
    capability: str
    backend: str = ""
    dependencies: tuple[str, ...] = ()
    assets: tuple[ModelAsset, ...] = ()
    download_size: int = 0
    installed_size: int = 0
    engine_modules: tuple[str, ...] = ()
    archive_url: str = ""
    archive_sha256: str = ""
    archive_parts: tuple[ArchivePart, ...] = ()
    offline_archive: str = ""
    protocol_version: int = PACK_PROTOCOL_VERSION
    runtime_contract: int = 0


def _assets_by_component() -> dict[str, tuple[ModelAsset, ...]]:
    combined = {asset.relative_path: asset for asset in (*required_assets("cpu"), *required_assets("gpu"))}
    grouped: dict[str, list[ModelAsset]] = {}
    for asset in combined.values():
        grouped.setdefault(asset.component, []).append(asset)
    return {key: tuple(sorted(values, key=lambda item: item.relative_path)) for key, values in grouped.items()}


def _load_release_pack_metadata() -> dict[str, dict]:
    """Read immutable release metadata without contacting the network.

    Source checkouts intentionally ship empty engine URLs. Release automation
    writes pinned URLs, sizes, and SHA-256 values after each engine archive is
    built, verified and finalized (signing is optional). This prevents guessing a mutable
    latest-release URL.
    """
    from haizflow.core.paths import bundle_root, project_root

    candidates = (
        # PyInstaller's bundle root is _internal, but release finalization
        # ships this inventory-pinned catalog beside HaizFlowCore.exe.
        project_root() / "RESOURCE-PACKS.json",
        bundle_root() / "RESOURCE-PACKS.json",
        bundle_root() / "resource-pack-manifest.json",
        project_root() / "runtime" / "resource-pack-manifest.json",
    )
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or payload.get("schema") != 1 or payload.get("protocol_version") != PACK_PROTOCOL_VERSION:
            continue
        packs = payload.get("packs")
        if isinstance(packs, dict):
            return {str(key): value for key, value in packs.items() if isinstance(value, dict)}
    return {}


def built_in_pack_definitions() -> tuple[ResourcePackDefinition, ...]:
    grouped = _assets_by_component()

    def model_pack(
        pack_id: str,
        label: str,
        group: str,
        capability: str,
        components: tuple[str, ...],
        dependencies: tuple[str, ...],
        *,
        backend: str = "",
    ) -> ResourcePackDefinition:
        assets = tuple(asset for component in components for asset in grouped.get(component, ()))
        return ResourcePackDefinition(
            pack_id,
            label,
            group,
            "1",
            capability,
            backend,
            dependencies,
            assets,
            sum(asset.size for asset in assets),
            sum(asset.size for asset in assets),
        )

    definitions: list[ResourcePackDefinition] = [
        ResourcePackDefinition(
            pack_id="engine-cpu-py313",
            label="Bộ xử lý CPU",
            group="processor",
            version="1",
            capability="engine",
            backend="cpu",
            download_size=1_300_000_000,
            installed_size=2_000_000_000,
            engine_modules=("torch", "ctranslate2", "llama_cpp", "onnxruntime", "whisperx.asr", "whisperx.alignment", "demucs.separate"),
            runtime_contract=3,
        ),
        ResourcePackDefinition(
            pack_id="engine-cuda128-py313",
            label="Bộ xử lý NVIDIA CUDA 12.8",
            group="processor",
            version="1",
            capability="engine",
            backend="gpu",
            download_size=4_500_000_000,
            installed_size=5_500_000_000,
            engine_modules=("torch", "torchaudio", "torchvision", "onnxruntime", "whisperx.asr", "whisperx.alignment", "demucs.separate"),
            runtime_contract=3,
        ),
        ResourcePackDefinition(
            pack_id="engine-vision-onnx",
            label="Bộ xử lý hình ảnh ONNX",
            group="processor",
            version="1",
            capability="engine",
            backend="vision",
            download_size=170_000_000,
            installed_size=260_000_000,
            engine_modules=("onnxruntime", "rapidocr"),
        ),
        ResourcePackDefinition(
            pack_id="engine-speaker-bundled", label="Nhận diện người nói tích hợp",
            group="processor", version="1", capability="engine", backend="cpu",
            engine_modules=("onnxruntime", "numpy"),
        ),
        model_pack(
            "model-whisper-small",
            "Whisper Small",
            "recognition",
            "recognition",
            ("whisper", "whisperx-vad", "alignment"),
            (),
        ),
        model_pack(
            "model-whisper-turbo",
            "Whisper Turbo",
            "recognition",
            "recognition",
            ("whisper-turbo", "whisperx-vad", "alignment"),
            (),
            backend="gpu",
        ),
        model_pack(
            "model-hymt2-cpu", "HY-MT2 CPU", "translation", "translation",
            ("hymt2-cpu",), (), backend="cpu",
        ),
        model_pack(
            "model-hymt2-gpu", "HY-MT2 GPU", "translation", "translation",
            ("hymt2-gpu",), (), backend="gpu",
        ),
        model_pack(
            "model-omnivoice",
            "OmniVoice",
            "voice",
            "voice",
            ("omnivoice", "omnivoice-sdk", "omnivoice-runtime"),
            (),
        ),
        model_pack(
            "model-demucs",
            "Demucs",
            "voice",
            "separation",
            ("demucs",),
            (),
        ),
        model_pack("model-demucs-cpu", "Demucs CPU", "separation", "separation", ("demucs",), ("engine-cpu-py313",)),
        model_pack("model-demucs-gpu", "Demucs GPU NVIDIA", "separation", "separation", ("demucs",), ("engine-cuda128-py313",)),
        model_pack(
            "model-subtitle-ocr",
            "OCR phụ đề",
            "image",
            "ocr",
            ("subtitle-ocr",),
            ("engine-vision-onnx",),
        ),
    ]
    speaker_asset = _speaker_asset()
    definitions.append(ResourcePackDefinition(
        pack_id="model-speaker-identification", label="Nhận diện người nói",
        group="voice", version="1", capability="speaker",
        dependencies=("engine-speaker-bundled",), assets=(speaker_asset,),
        download_size=speaker_asset.size, installed_size=speaker_asset.size,
    ))
    release_metadata = _load_release_pack_metadata()
    resolved: list[ResourcePackDefinition] = []
    for definition in definitions:
        metadata = release_metadata.get(definition.pack_id, {})
        url = str(metadata.get("url") or "")
        digest = str(metadata.get("sha256") or "").lower()
        offline = metadata.get("offline_archive", "")
        if not isinstance(offline, str) or (offline and not re.fullmatch(r"[a-z0-9][a-z0-9._-]*\.zip", offline)):
            resolved.append(definition)
            continue
        try:
            parts = parse_archive_parts(metadata)
        except ValueError:
            # Fail closed for this pack without preventing startup of Core.
            resolved.append(definition)
            continue
        try:
            download_size = int(metadata.get("download_size") or definition.download_size)
            installed_size = int(metadata.get("installed_size") or definition.installed_size)
        except (TypeError, ValueError):
            download_size = definition.download_size
            installed_size = definition.installed_size
        if definition.engine_modules and (url or parts or offline) and re.fullmatch(r"[a-f0-9]{64}", digest):
            definition = replace(
                definition,
                version=str(metadata.get("version") or definition.version),
                archive_url=url,
                archive_sha256=digest,
                archive_parts=parts,
                offline_archive=offline,
                download_size=max(0, download_size),
                installed_size=max(0, installed_size),
            )
        resolved.append(definition)
    return tuple(resolved)


class ResourcePackError(RuntimeError):
    pass


class ResourcePackManager:
    """Thread-safe pack inventory and transactional model installer."""

    def __init__(self, definitions: Iterable[ResourcePackDefinition] | None = None):
        self.definitions = {item.pack_id: item for item in (definitions or built_in_pack_definitions())}
        self._lock = threading.RLock()
        self._active: set[str] = set()
        self._cancel_events: dict[str, threading.Event] = {}

    @staticmethod
    def _offline_root() -> Path:
        """Setup records its companion folder; fallback supports portable copies."""
        from haizflow.update.filesystem import no_links

        root = install_root()
        pointer = root / "offline-resources.ini"
        no_links(pointer)
        if pointer.is_file():
            if pointer.stat().st_size > 8192:
                raise ResourcePackError("Vị trí gói cài đặt không hợp lệ.")
            parser = configparser.ConfigParser(interpolation=None)
            raw = pointer.read_bytes()
            parser.read_string(raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"))
            directory = Path(parser.get("resources", "path"))
        else:
            directory = root / "offline-resources"
        if not directory.is_absolute() or str(directory).startswith("\\\\"):
            raise ResourcePackError("Gói cài đặt phải nằm trên ổ đĩa cục bộ.")
        no_links(directory)
        return directory

    def offline_archive_path(self, pack_id: str) -> Path | None:
        definition = self.definitions[pack_id]
        name = definition.offline_archive
        if not name:
            return None
        try:
            if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*\.zip", name):
                return None
            from haizflow.update.filesystem import no_links

            path = self._offline_root() / name
            no_links(path)
            if path.is_file() and path.stat().st_size == definition.download_size:
                return path
        except (OSError, ValueError, ResourcePackError, configparser.Error):
            pass
        return None

    def archive_available(self, pack_id: str) -> bool:
        definition = self.definitions[pack_id]
        return bool(definition.archive_url or definition.archive_parts or self.offline_archive_path(pack_id))

    @staticmethod
    def cleanup_previous_storage() -> None:
        """Remove a moved resource tree; safe to run after the UI is visible."""
        from haizflow.update.filesystem import no_links, UpdateError

        pointer = resource_storage_pointer_path()
        try:
            payload = json.loads(pointer.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("version") != RESOURCE_STATE_VERSION:
                return
            previous_value = payload.get("cleanup_previous")
            active_value = payload.get("path")
            if not isinstance(previous_value, str) or not previous_value.strip() or not isinstance(active_value, str) or not active_value.strip():
                return
            previous = Path(previous_value)
            active = Path(active_value)
            if (not previous.is_absolute() or not active.is_absolute()
                    or str(previous).startswith("\\\\") or str(active).startswith("\\\\")):
                return
            for root in (previous, active):
                no_links(root)
            previous = previous.resolve()
            active = active.resolve()
            if (previous.parent == previous or active.parent == active
                    or previous == Path.cwd().resolve()
                    or previous == active or previous.is_relative_to(active) or active.is_relative_to(previous)):
                return
            for root in (previous, active):
                for name in ("models", "engines", "packages"):
                    tree = root / name
                    no_links(tree)
                    for path in tree.rglob("*"):
                        no_links(path)
            # Only discard the source if the active copy still contains every
            # resource. A corrupt/missing target or concurrent source change
            # must leave the previous copy available for recovery.
            if ResourcePackManager._tree_fingerprint(previous) != ResourcePackManager._tree_fingerprint(active):
                return
            if json.loads(pointer.read_text(encoding="utf-8")) != payload:
                return
        except (OSError, ValueError, TypeError, json.JSONDecodeError, UpdateError):
            return
        for name in ("models", "engines", "packages"):
            candidate = (previous / name).resolve()
            if candidate.parent != previous:
                continue
            shutil.rmtree(candidate, ignore_errors=True)
        temporary = None
        try:
            if json.loads(pointer.read_text(encoding="utf-8")) != payload:
                return
            payload.pop("cleanup_previous", None)
            fd, temporary_name = tempfile.mkstemp(prefix=".resource-cleanup-", suffix=".json", dir=pointer.parent)
            temporary = Path(temporary_name)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, pointer)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    @property
    def storage_root(self) -> Path:
        return resource_storage_dir()

    def _engine_marker(self, definition: ResourcePackDefinition) -> Path:
        return engines_dir() / definition.pack_id / definition.version / "complete.json"

    def _engine_is_valid(self, definition: ResourcePackDefinition) -> bool:
        marker = self._engine_marker(definition)
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
            engine = json.loads((marker.parent / "engine.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        marker_valid = (
            payload.get("pack_id") == definition.pack_id
            and payload.get("version") == definition.version
            and payload.get("protocol_version") == definition.protocol_version
            and (not definition.archive_sha256 or payload.get("archive_sha256") == definition.archive_sha256)
        )
        engine_valid = (
            engine.get("pack_id") == definition.pack_id
            and engine.get("profile") == ENGINE_PROFILE_BY_PACK.get(definition.pack_id)
            and engine.get("version") == definition.version
            and engine.get("protocol_version") == definition.protocol_version
            and (not definition.runtime_contract or engine.get("runtime_contract") == definition.runtime_contract)
        )
        if not marker_valid or not engine_valid:
            return False
        root = marker.parent.resolve()
        for command_name in ENGINE_REQUIRED_COMMANDS.get(definition.pack_id, {"smoke_command", "rpc_command"}):
            command = engine.get(command_name)
            if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
                return False
            executable = (root / command[0]).resolve()
            if not executable.is_relative_to(root) or not executable.is_file():
                return False
        return True

    @staticmethod
    def _module_available(module: str) -> bool:
        try:
            return importlib.util.find_spec(module) is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            return False

    def _bundled_engine_available(self, definition: ResourcePackDefinition) -> bool:
        if not definition.engine_modules or not all(self._module_available(name) for name in definition.engine_modules):
            return False
        if definition.backend != "gpu":
            return True
        try:
            return "+cu" in importlib.metadata.version("torch").lower()
        except importlib.metadata.PackageNotFoundError:
            return False

    @staticmethod
    def _assets_present(definition: ResourcePackDefinition) -> bool:
        root = models_dir()
        return bool(definition.assets) and all(
            (root / asset.relative_path).is_file()
            and (root / asset.relative_path).stat().st_size == asset.size
            for asset in definition.assets
        )

    def status(self, pack_id: str) -> str:
        definition = self.definitions[pack_id]
        with self._lock:
            if pack_id in self._active:
                return "working"
        if definition.engine_modules:
            if self._engine_is_valid(definition):
                return "installed"
            return "bundled" if self._bundled_engine_available(definition) else "missing"
        if pack_id == "model-speaker-identification":
            from haizflow.pipeline.speaker_identity import bundled_model_root, MODEL_FILE, MODEL_SIZE

            path = bundled_model_root() / MODEL_FILE
            if path.is_file() and path.stat().st_size == MODEL_SIZE:
                return "bundled"
        if pack_id in {"model-demucs-cpu", "model-demucs-gpu"}:
            try:
                receipt = json.loads((models_dir() / "demucs/profiles" / f"{pack_id}.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                receipt = {}
            if receipt != {"pack_id": pack_id, "version": definition.version}:
                return "missing"
        if self._assets_present(definition):
            return "installed"
        if any((models_dir() / f"{asset.relative_path}.part").is_file() for asset in definition.assets):
            return "paused"
        return "missing"

    def installed_bytes(self, pack_id: str) -> int:
        definition = self.definitions[pack_id]
        if definition.engine_modules:
            pack_root = engines_dir() / definition.pack_id
            if pack_root.is_dir():
                return sum(path.stat().st_size for path in pack_root.rglob("*") if path.is_file())
            return definition.installed_size if self._bundled_engine_available(definition) else 0
        root = models_dir()
        return sum(
            (root / asset.relative_path).stat().st_size
            for asset in definition.assets
            if (root / asset.relative_path).is_file()
        )

    def download_bytes(self, pack_id: str) -> int:
        """Return bytes still needed for this install unit."""
        definition = self.definitions[pack_id]
        if definition.engine_modules:
            if self.offline_archive_path(pack_id) is not None:
                return 0
            package = resource_packages_dir() / f"{definition.pack_id}-{definition.version}.zip"
            partial = package.with_name(package.name + ".part")
            try:
                if package.stat().st_size == definition.download_size:
                    return 0
            except FileNotFoundError:
                pass
            if definition.archive_parts:
                remaining = 0
                for index, part in enumerate(definition.archive_parts, 1):
                    path = package.with_name(package.name + f".{index:03d}")
                    try:
                        if path.stat().st_size == part.size:
                            continue
                    except FileNotFoundError:
                        pass
                    partial_part = path.with_name(path.name + ".part")
                    try:
                        resumed = min(part.size, partial_part.stat().st_size)
                    except FileNotFoundError:
                        resumed = 0
                    remaining += part.size - resumed
                return remaining
            try:
                resumed = min(definition.download_size, partial.stat().st_size)
            except FileNotFoundError:
                resumed = 0
            return max(0, definition.download_size - resumed)
        if not definition.assets:
            return definition.download_size
        remaining = 0
        root = models_dir()
        for asset in definition.assets:
            target = root / asset.relative_path
            try:
                if target.stat().st_size == asset.size:
                    continue
            except FileNotFoundError:
                pass
            partial = target.with_name(target.name + ".part")
            try:
                resumed = min(asset.size, partial.stat().st_size)
            except FileNotFoundError:
                resumed = 0
            remaining += max(0, asset.size - resumed)
        return remaining

    @staticmethod
    def _resource_storage_bytes() -> int:
        """Return actual bytes occupied by installed resources and downloads.

        Per-pack sizes can include a shared VAD/model asset more than once.
        The summary shown to users must count real files instead, including a
        retained engine archive that can make a later reinstall faster.
        """
        total = 0
        for root in (models_dir(), engines_dir(), resource_packages_dir()):
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                try:
                    total += path.stat().st_size
                except FileNotFoundError:
                    # A concurrent atomic promotion/removal won this race; the
                    # next background inventory will report the new value.
                    continue
        return total

    def snapshot(self) -> list[dict]:
        storage_root = self.storage_root
        usage_path = storage_root
        while not usage_path.exists() and usage_path.parent != usage_path:
            usage_path = usage_path.parent
        usage = shutil.disk_usage(usage_path)
        result = []
        total_installed_bytes = self._resource_storage_bytes()
        for definition in self.definitions.values():
            status = self.status(definition.pack_id)
            missing_dependencies = [
                dependency
                for dependency in definition.dependencies
                if dependency in self.definitions and self.status(dependency) not in {"installed", "bundled"}
            ]
            result.append(
                {
                    "packId": definition.pack_id,
                    "label": definition.label,
                    "group": definition.group,
                    "version": definition.version,
                    "capability": definition.capability,
                    "backend": definition.backend,
                    "status": status,
                    "downloadSize": self.download_bytes(definition.pack_id),
                    "installedSize": self.installed_bytes(definition.pack_id),
                    "totalInstalledBytes": total_installed_bytes,
                    "location": str(storage_root),
                    "dependencies": list(definition.dependencies),
                    "canInstall": bool(definition.assets or self.archive_available(definition.pack_id))
                    and status in {"missing", "paused", "failed"},
                    "canRemove": status == "installed",
                    "blockedReason": (
                        "Đã cài cùng ứng dụng."
                        if status == "bundled"
                        else "Thiếu bộ xử lý: "
                        + ", ".join(self.definitions[item].label for item in missing_dependencies)
                        if missing_dependencies
                        else ""
                    ),
                    "freeBytes": usage.free,
                }
            )
        return result

    def required_packs(self, capability: str, context: dict | None = None) -> list[str]:
        context = context or {}
        device = "gpu" if str(context.get("device") or "cpu") == "gpu" else "cpu"
        provider = str(context.get("provider") or "omnivoice")
        voice_device = "gpu" if provider.endswith("-gpu") else "cpu"
        voice_packs = [f"engine-{'cuda128-py313' if voice_device == 'gpu' else 'cpu-py313'}", "model-omnivoice"]
        if context.get("voice_clone") and not any(
            self.status(pack) in {"installed", "bundled"} for pack in ("model-whisper-small", "model-whisper-turbo")
        ):
            voice_packs.append("model-whisper-small")
        speaker_packs = ["engine-speaker-bundled", "model-speaker-identification"]
        if context.get("speaker_mode") == "multiple":
            voice_packs.extend(speaker_packs)
        recognition_model = str(context.get("model") or "small").lower()
        recognition_device = ("cpu" if recognition_model == "small-cpu" else
                              "gpu" if recognition_model in {"small-gpu", "turbo", "large-v3-turbo"} else device)
        if context.get("reference_asr"):
            recognition_device = device
        engine_pack = f"engine-{'cuda128-py313' if recognition_device == 'gpu' else 'cpu-py313'}"
        whisper_pack = (
            "model-whisper-turbo" if recognition_model in {"turbo", "large-v3-turbo"}
            else "model-whisper-small"
        )
        translation_packs: list[str] = []
        if str(capability) == "translation":
            translation_model = str(context.get("translation_model") or "auto").lower()
            if translation_model.startswith("gemini-"):
                translation_packs = []
            elif translation_model == "auto":
                from haizflow.core.hardware import runtime_profile

                profile = runtime_profile()
                translation_model = "full" if device == "gpu" and profile.total_vram_gib >= 12 else "q4"
            if not translation_model.startswith("gemini-"):
                translation_device = "gpu" if translation_model == "full" else "cpu"
                translation_engine = f"engine-{'cuda128-py313' if translation_device == 'gpu' else 'cpu-py313'}"
                translation_packs = [translation_engine, f"model-hymt2-{translation_device}"]
        mapping = {
            "recognition": [engine_pack, whisper_pack],
            "translation": translation_packs,
            "voice": voice_packs,
            "separation": [
                f"engine-{'cuda128-py313' if device == 'gpu' else 'cpu-py313'}",
                f"model-demucs-{device}",
            ],
            "ocr": ["engine-vision-onnx", "model-subtitle-ocr"],
            "speaker": speaker_packs,
        }
        return list(dict.fromkeys(mapping.get(str(capability), [])))

    def missing_packs(self, capability: str, context: dict | None = None) -> list[str]:
        ready_states = {"installed", "bundled"}
        return [
            pack_id
            for pack_id in self.required_packs(capability, context)
            if self.status(pack_id) not in ready_states
        ]

    def external_engine_pack(self, capability: str, context: dict | None = None) -> str:
        """Return the installed external engine serving a capability, if any."""
        for pack_id in self.required_packs(capability, context):
            definition = self.definitions.get(pack_id)
            if definition is not None and definition.engine_modules and self._engine_is_valid(definition):
                return pack_id
        return ""

    def warm_engine_pack(self, capability: str, context: dict | None = None) -> str:
        """Return an engine suitable for isolated speculative warm-up.

        Source checkouts may still expose AI dependencies from the application
        virtual environment.  Those dependencies are never imported by Qt:
        the warm-up pool hosts them through the same JSON-lines protocol used
        by installed resource engines.  Foreground source-mode tools retain
        their existing subprocess paths and testable command contracts.
        """

        installed = self.external_engine_pack(capability, context)
        if installed:
            return installed
        for pack_id in self.required_packs(capability, context):
            definition = self.definitions.get(pack_id)
            if (
                definition is not None
                and definition.engine_modules
                and self._bundled_engine_available(definition)
            ):
                return pack_id
        return ""

    @staticmethod
    def _bundled_engine_command(definition: ResourcePackDefinition, command_name: str) -> list[str]:
        """Run a source/development AI runtime behind the engine boundary."""

        profile = ENGINE_PROFILE_BY_PACK.get(definition.pack_id, "")
        base = ([sys.executable, "--engine-worker"] if getattr(sys, "frozen", False)
                else [sys.executable, "-m", "haizflow.engine.main"])
        if command_name == "smoke_command":
            return [*base, "--smoke", "--profile", profile] if profile else []
        if command_name == "rpc_command":
            return [*base, "--rpc"]
        if command_name == "hymt2_server":
            return [*base, "--hymt2-worker", "--server"]
        if command_name == "omnivoice_worker":
            return [*base, "--omnivoice-worker"]
        if command_name == "omnivoice_server":
            return [*base, "--omnivoice-server"]
        if command_name == "demucs":
            return [*base, "--demucs-separate"]
        if command_name in {"demucs_task", "transcribe", "subtitle_ocr", "speaker_identification"}:
            return base
        if command_name == "runtime_probe":
            return [*base, "--runtime-probe"]
        return []

    def engine_command(self, pack_id: str, command_name: str) -> list[str]:
        """Resolve a command declared by an installed engine without shell expansion."""
        definition = self.definitions.get(str(pack_id))
        if definition is None or not definition.engine_modules:
            return []
        if not self._engine_is_valid(definition):
            if self._bundled_engine_available(definition):
                return self._bundled_engine_command(definition, str(command_name))
            return []
        root = self._engine_marker(definition).parent.resolve()
        try:
            payload = json.loads((root / "engine.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        command = payload.get(str(command_name))
        if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
            return []
        executable = (root / command[0]).resolve()
        if not executable.is_relative_to(root) or not executable.is_file():
            return []
        substitutions = {
            "{models_dir}": str(models_dir()),
            "{resource_root}": str(self.storage_root),
            "{engine_root}": str(root),
        }
        resolved = [str(executable)]
        for argument in command[1:]:
            for token, value in substitutions.items():
                argument = argument.replace(token, value)
            resolved.append(argument)
        return resolved

    def requirement_summary(self, pack_ids: Iterable[str]) -> dict:
        definitions = [self.definitions[pack_id] for pack_id in pack_ids if pack_id in self.definitions]
        ready_states = {"installed", "bundled"}
        pending = [item for item in definitions if self.status(item.pack_id) not in ready_states]
        download = sum(self.download_bytes(item.pack_id) for item in pending)
        installed = sum(
            item.installed_size
            if item.engine_modules or not item.assets
            else self.download_bytes(item.pack_id)
            for item in pending
        )
        rollback = sum(
            self.installed_bytes(item.pack_id)
            for item in definitions
            if item.engine_modules and self.status(item.pack_id) not in ready_states
        )
        # Multipart downloads and their assembled ZIP coexist until all checks
        # pass. Never omit this second compressed copy from disk preflight.
        assembly = sum(item.download_size for item in pending
                       if item.archive_parts and self.offline_archive_path(item.pack_id) is None)
        return {
            "downloadBytes": download,
            "installedBytes": installed,
            "rollbackBytes": rollback,
            "assemblyBytes": assembly,
            "requiredBytes": download + installed + rollback + assembly + MINIMUM_OPERATIONAL_FREE_BYTES,
            "freeBytes": shutil.disk_usage(self.storage_root).free,
        }

    def _verify_model_pack(self, definition: ResourcePackDefinition) -> None:
        root = models_dir()
        pack_id = definition.pack_id
        if pack_id == "model-whisper-small":
            verify_whisper_model(root / "whisper" / "small")
            verify_whisperx_vad_model(root / "whisperx-vad")
            for language in ALIGNMENT_MODELS:
                verify_alignment_model(root / "alignment", language)
        elif pack_id == "model-whisper-turbo":
            verify_whisper_turbo_model(root / "whisper" / "large-v3-turbo")
            verify_whisperx_vad_model(root / "whisperx-vad")
            for language in ALIGNMENT_MODELS:
                verify_alignment_model(root / "alignment", language)
        elif pack_id == "model-hymt2-cpu":
            verify_cpu_model(root / "hymt2-gguf" / HYMT2_CPU_FILE)
        elif pack_id == "model-hymt2-gpu":
            verify_gpu_model(root / "hymt2-transformers")
        elif pack_id == "model-omnivoice":
            verify_omnivoice_model(root / "omnivoice")
            verify_omnivoice_sdk(root / "omnivoice")
        elif pack_id.startswith("model-demucs"):
            verify_demucs_model(root / "demucs")
        elif pack_id == "model-subtitle-ocr":
            verify_subtitle_ocr_models(root / "subtitle-ocr")
        elif pack_id == "model-speaker-identification":
            from haizflow.pipeline.speaker_identity import verify_model

            verify_model(root / "speaker-identification")

    def install(self, pack_id: str, progress: Callable[[str, ModelProgress], None]) -> None:
        definition = self.definitions[pack_id]
        if definition.engine_modules and self.archive_available(pack_id):
            self._install_engine_archive(definition, progress)
            return
        if not definition.assets:
            raise ResourcePackError(
                "Gói bộ xử lý được phát hành cùng release asset riêng; manifest hiện tại chưa có archive để tải."
            )
        summary = self.requirement_summary((pack_id,))
        if summary["freeBytes"] < summary["requiredBytes"]:
            raise ResourcePackError("Không đủ dung lượng trống để tải, cài và giữ bản khôi phục an toàn.")
        cancel = threading.Event()
        with self._lock:
            if pack_id in self._active:
                return
            self._active.add(pack_id)
            self._cancel_events[pack_id] = cancel
        try:
            install_model_assets(
                models_dir(),
                definition.assets,
                progress=lambda event: progress(pack_id, event),
                cancel_event=cancel,
                verify_complete=lambda _root: self._verify_model_pack(definition),
            )
            if pack_id in {"model-demucs-cpu", "model-demucs-gpu"}:
                from haizflow.update.filesystem import atomic_json

                atomic_json(models_dir() / "demucs/profiles" / f"{pack_id}.json",
                            {"pack_id": pack_id, "version": definition.version})
        finally:
            with self._lock:
                self._active.discard(pack_id)
                self._cancel_events.pop(pack_id, None)

    @staticmethod
    def _safe_extract_zip(archive: Path, destination: Path, *, progress=None, cancelled=None) -> None:
        destination = destination.resolve()
        with zipfile.ZipFile(archive) as bundle:
            total = sum(member.file_size for member in bundle.infolist())
            completed = 0
            for member in bundle.infolist():
                if cancelled is not None and cancelled():
                    raise ModelBootstrapCancelled("Engine installation cancelled.")
                target = (destination / member.filename).resolve()
                if not target.is_relative_to(destination):
                    raise ResourcePackError("Gói tài nguyên chứa đường dẫn không an toàn.")
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(member) as source, target.open("wb") as output:
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        if cancelled is not None and cancelled():
                            raise ModelBootstrapCancelled("Engine installation cancelled.")
                        output.write(block)
                        completed += len(block)
                        if progress is not None:
                            progress(completed, total)

    def _verify_engine_staging(self, definition: ResourcePackDefinition, staging: Path) -> dict:
        manifest_path = staging / "engine.json"
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ResourcePackError("Gói bộ xử lý thiếu engine.json hợp lệ.") from exc
        if (
            payload.get("pack_id") != definition.pack_id
            or payload.get("profile") != ENGINE_PROFILE_BY_PACK.get(definition.pack_id)
            or payload.get("version") != definition.version
            or payload.get("protocol_version") != definition.protocol_version
            or (definition.runtime_contract and payload.get("runtime_contract") != definition.runtime_contract)
        ):
            raise ResourcePackError("Phiên bản hoặc giao thức của gói bộ xử lý không tương thích.")
        for command_name in sorted(ENGINE_REQUIRED_COMMANDS.get(definition.pack_id, {"smoke_command", "rpc_command"})):
            command = payload.get(command_name)
            if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
                raise ResourcePackError(f"Gói bộ xử lý không khai báo {command_name}.")
            executable = (staging / command[0]).resolve()
            if not executable.is_relative_to(staging.resolve()) or not executable.is_file():
                raise ResourcePackError(f"Không tìm thấy chương trình cho {command_name}.")
        command = payload["smoke_command"]
        executable = (staging / command[0]).resolve()
        # Configuration imports create caches. Keep smoke writes outside the
        # immutable engine and away from the user's existing projects/models.
        with tempfile.TemporaryDirectory(prefix=".engine-smoke-", dir=staging.parent) as smoke:
            smoke_root = Path(smoke)
            environment = os.environ.copy()
            environment.update({
                "HAIZFLOW_HOME": smoke,
                "RUNTIME_DATA_DIR": str(smoke_root / "data"),
                "MODELS_DIR": str(smoke_root / "models"),
                "HAIZFLOW_TMP_DIR": str(smoke_root / "tmp"),
                "HAIZFLOW_SMOKE_TEST": "1",
            })
            result = subprocess.run(
                [str(executable), *command[1:]],
                cwd=staging, env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        if (staging / "runtime").exists():
            raise ResourcePackError("Bộ xử lý ghi dữ liệu vào thư mục cài đặt bất biến.")
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "smoke test failed").strip()
            raise ResourcePackError(f"Bộ xử lý không vượt qua kiểm tra: {detail}")
        return payload

    def _install_engine_archive(
        self,
        definition: ResourcePackDefinition,
        progress: Callable[[str, ModelProgress], None],
    ) -> None:
        cancel = threading.Event()
        if definition.download_size <= 0 or len(definition.archive_sha256) != 64:
            raise ResourcePackError("Manifest của gói bộ xử lý chưa đầy đủ.")
        summary = self.requirement_summary((definition.pack_id,))
        if summary["freeBytes"] < summary["requiredBytes"]:
            raise ResourcePackError("Không đủ dung lượng trống để tải, cài và giữ bản khôi phục an toàn.")
        with self._lock:
            if definition.pack_id in self._active:
                return
            self._active.add(definition.pack_id)
            self._cancel_events[definition.pack_id] = cancel
        package_name = f"{definition.pack_id}-{definition.version}.zip"
        asset = ModelAsset(
            "engine",
            definition.label,
            definition.archive_url,
            package_name,
            definition.download_size,
            definition.archive_sha256,
        )
        packages = resource_packages_dir()
        target = self._engine_marker(definition).parent
        staging = target.parent / f".{definition.version}-{os.getpid()}.partial"
        backup: Path | None = None
        try:
            offline = self.offline_archive_path(definition.pack_id)
            part_assets = tuple(ModelAsset(
                "engine", definition.label, part.url, package_name + f".{index:03d}", part.size, part.sha256,
            ) for index, part in enumerate(definition.archive_parts, 1))
            archive = offline or packages / package_name
            if offline is not None:
                digest = hashlib.sha256()
                with offline.open("rb") as source:
                    completed = 0
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        if cancel.is_set():
                            raise ModelBootstrapCancelled("Engine installation cancelled.")
                        digest.update(block)
                        completed += len(block)
                        progress(definition.pack_id, ModelProgress(
                            "verifying", definition.label, "Đang kiểm tra gói cài đặt", completed, asset.size, "transfer"))
                if completed != asset.size or digest.hexdigest() != asset.sha256:
                    raise ResourcePackError("Gói cài đặt bị hỏng hoặc không đúng phiên bản. Hãy tải lại bộ cài.")
            cached_multipart = bool(part_assets) and archive_matches(archive, size=asset.size, sha256=asset.sha256)
            if offline is None and not cached_multipart:
                install_model_assets(
                    packages,
                    part_assets or (asset,),
                    progress=lambda event: progress(definition.pack_id, replace(event, phase="transfer")),
                    cancel_event=cancel,
                )
            if offline is None and part_assets and not cached_multipart:
                try:
                    join_archive_parts(
                        tuple((packages / part_asset.relative_path, part) for part_asset, part in zip(part_assets, definition.archive_parts)),
                        archive, size=asset.size, sha256=asset.sha256, cancelled=cancel.is_set,
                        progress=lambda done: progress(definition.pack_id, ModelProgress(
                            "verifying", definition.label, "Đang kiểm tra gói bộ xử lý", done, asset.size)),
                    )
                except InterruptedError as error:
                    raise ModelBootstrapCancelled(str(error)) from error
                for part_asset in part_assets:
                    (packages / part_asset.relative_path).unlink(missing_ok=True)
            if cancel.is_set():
                raise ModelBootstrapCancelled("Engine installation cancelled.")
            if staging.exists():
                shutil.rmtree(staging)
            staging.mkdir(parents=True)
            self._safe_extract_zip(archive, staging, cancelled=cancel.is_set,
                progress=lambda done, total: progress(definition.pack_id, ModelProgress(
                    "installing", definition.label, "Đang giải nén bộ xử lý", done, total, "installing")))
            progress(definition.pack_id, ModelProgress(
                "verifying", definition.label, "Đang kiểm tra bộ xử lý", 0, 0, "finalizing"))
            self._verify_engine_staging(definition, staging)
            if cancel.is_set():
                raise ModelBootstrapCancelled("Engine installation cancelled.")
            marker_payload = {
                "schema": RESOURCE_STATE_VERSION,
                "pack_id": definition.pack_id,
                "version": definition.version,
                "protocol_version": definition.protocol_version,
                "archive_sha256": definition.archive_sha256,
            }
            marker = staging / "complete.json"
            marker.write_text(json.dumps(marker_payload, indent=2) + "\n", encoding="utf-8")
            if target.exists():
                backup = target.parent / f".{definition.version}-{os.getpid()}.rollback"
                if backup.exists():
                    shutil.rmtree(backup)
                os.replace(target, backup)
            os.replace(staging, target)
            if backup is not None:
                shutil.rmtree(backup, ignore_errors=True)
            # A successful smoke-tested promotion makes older engine versions
            # obsolete. Keep them until this point so any failure above leaves
            # the previous executable available for rollback.
            pack_root = target.parent
            for previous in pack_root.iterdir():
                if previous != target and previous.is_dir() and not previous.name.startswith("."):
                    shutil.rmtree(previous, ignore_errors=True)
            progress(
                definition.pack_id,
                ModelProgress("ready", definition.label, "Bộ xử lý đã sẵn sàng", asset.size, asset.size),
            )
        except Exception:
            # If promotion failed after moving the existing engine aside,
            # restore it before propagating the error. Never replace a target
            # that already exists (another writer may have created it).
            if backup is not None and backup.exists() and not target.exists():
                os.replace(backup, target)
            raise
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            with self._lock:
                self._active.discard(definition.pack_id)
                self._cancel_events.pop(definition.pack_id, None)

    def cancel(self, pack_id: str) -> None:
        with self._lock:
            event = self._cancel_events.get(pack_id)
        if event is not None:
            event.set()

    def remove(self, pack_id: str, *, in_use: bool = False) -> int:
        from haizflow.update.filesystem import no_links, UpdateError

        if in_use or self._active:
            raise ResourcePackError("Gói đang được một tác vụ sử dụng.")
        definition = self.definitions[pack_id]
        if self.status(pack_id) == "bundled":
            raise ResourcePackError("Không thể gỡ tài nguyên tích hợp trong ứng dụng.")
        removed = 0
        if definition.engine_modules:
            root = self._engine_marker(definition).parent
            try:
                no_links(root)
                for path in root.rglob("*"):
                    no_links(path)
            except UpdateError as error:
                raise ResourcePackError("Vị trí gói chứa liên kết hoặc junction; không thể gỡ.") from error
            if root.is_dir():
                removed = sum(path.stat().st_size for path in root.rglob("*") if path.is_file())
                shutil.rmtree(root)
            return removed
        root = models_dir()
        candidates = [candidate for asset in definition.assets for candidate in
                      (root / asset.relative_path, (root / asset.relative_path).with_name(Path(asset.relative_path).name + ".part"))]
        receipt = root / "demucs/profiles" / f"{pack_id}.json" if pack_id in {"model-demucs-cpu", "model-demucs-gpu"} else None
        if receipt is not None:
            candidates.append(receipt)
        try:
            for candidate in candidates:
                no_links(candidate)
        except UpdateError as error:
            raise ResourcePackError("Vị trí model chứa liên kết hoặc junction; không thể gỡ.") from error
        for asset in definition.assets:
            shared_by_installed_pack = any(
                other.pack_id != definition.pack_id
                and other.pack_id != "model-demucs"
                and not other.engine_modules
                and any(candidate.relative_path == asset.relative_path for candidate in other.assets)
                and self.status(other.pack_id) == "installed"
                for other in self.definitions.values()
            )
            if shared_by_installed_pack:
                continue
            path = root / asset.relative_path
            for candidate in (path, path.with_name(path.name + ".part")):
                try:
                    removed += candidate.stat().st_size
                    candidate.unlink()
                except FileNotFoundError:
                    pass
        if receipt is not None:
            receipt.unlink(missing_ok=True)
        return removed

    def clean_unused(self, *, minimum_age_seconds: int = 0) -> int:
        from haizflow.update.filesystem import no_links, UpdateError

        if self._active:
            return 0
        removed = 0
        cutoff = time.time() - max(0, int(minimum_age_seconds))
        for root in (models_dir(), resource_packages_dir(), engines_dir()):
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or not path.name.endswith((".part", ".partial", ".tmp")):
                    continue
                try:
                    no_links(path)
                    if path.stat().st_mtime > cutoff:
                        continue
                    removed += path.stat().st_size
                    path.unlink()
                except (OSError, UpdateError):
                    pass
        return removed

    def verify_installed(self, pack_id: str) -> None:
        """Run a native runtime smoke test or verify the model's pinned files."""
        definition = self.definitions[pack_id]
        if definition.engine_modules:
            self._verify_engine_staging(definition, self._engine_marker(definition).parent)
        else:
            self._verify_model_pack(definition)

    def move_storage(self, destination: Path) -> Path:
        from haizflow.update.filesystem import no_links

        no_links(destination.expanduser())
        no_links(self.storage_root)
        destination = destination.expanduser().resolve()
        if str(destination).startswith("\\\\"):
            raise ResourcePackError("Không hỗ trợ ổ mạng cho gói tài nguyên.")
        source = self.storage_root.resolve()
        if destination == source:
            return source
        target = destination / "HaizFlowResources"
        if target.is_relative_to(source) or source.is_relative_to(target):
            raise ResourcePackError("Hãy chọn một thư mục ngoài vị trí tài nguyên hiện tại.")
        no_links(target)
        if target.exists() and (not target.is_dir() or any(
                child.name not in {"models", "engines", "packages"} for child in target.iterdir())):
            raise ResourcePackError("Thư mục đích chứa dữ liệu khác. Hãy chọn vị trí trống.")
        for root in (source, target):
            for name in ("models", "engines", "packages"):
                no_links(root / name)
                for path in (root / name).rglob("*"):
                    no_links(path)
        destination.mkdir(parents=True, exist_ok=True)
        required = sum(
            path.stat().st_size
            for name in ("models", "engines", "packages")
            for path in (source / name).rglob("*")
            if path.is_file()
        )
        if shutil.disk_usage(destination).free < required + MINIMUM_OPERATIONAL_FREE_BYTES:
            raise ResourcePackError("Ổ đích không đủ dung lượng trống.")
        staging = destination / f".haizflow-resources-{os.getpid()}.partial"
        if staging.exists():
            raise ResourcePackError("Vị trí đích còn bản chuyển dở. Hãy chọn thư mục khác.")
        staging.mkdir(parents=True)
        backup: Path | None = None
        promoted = False
        try:
            for name in ("models", "engines", "packages"):
                origin = source / name
                if origin.is_dir():
                    shutil.copytree(origin, staging / name)
            if self._tree_fingerprint(source) != self._tree_fingerprint(staging):
                raise ResourcePackError("Không thể xác minh bản sao gói tài nguyên trên ổ đích.")
            if target.exists():
                backup = destination / f".haizflow-resources-{os.getpid()}.backup"
                if backup.exists():
                    raise ResourcePackError("Vị trí đích còn bản khôi phục. Hãy chọn thư mục khác.")
                os.replace(target, backup)
            os.replace(staging, target)
            promoted = True
            pointer = resource_storage_pointer_path()
            pointer.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=".resource-storage-", suffix=".json", dir=pointer.parent)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(
                    {
                        "version": RESOURCE_STATE_VERSION,
                        "path": str(target),
                        "cleanup_previous": str(source),
                    },
                    stream,
                    indent=2,
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, pointer)
            if backup is not None:
                shutil.rmtree(backup, ignore_errors=True)
            return target
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            if backup is not None and backup.exists():
                if promoted:
                    shutil.rmtree(target, ignore_errors=True)
                if not target.exists():
                    os.replace(backup, target)
            elif promoted:
                shutil.rmtree(target, ignore_errors=True)
            raise

    @staticmethod
    def _tree_fingerprint(root: Path) -> tuple[tuple[str, int, str], ...]:
        """Hash only the three resource payload trees for an atomic storage move."""
        records: list[tuple[str, int, str]] = []
        for name in ("models", "engines", "packages"):
            directory = root / name
            if not directory.is_dir():
                continue
            for path in sorted(item for item in directory.rglob("*") if item.is_file()):
                digest = hashlib.sha256()
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                records.append((path.relative_to(root).as_posix(), path.stat().st_size, digest.hexdigest()))
        return tuple(records)


__all__ = [
    "ENGINE_REQUIRED_COMMANDS",
    "PACK_PROTOCOL_VERSION",
    "ResourcePackDefinition",
    "ResourcePackError",
    "ResourcePackManager",
    "built_in_pack_definitions",
    "ModelBootstrapCancelled",
]


def installed_engine_command(capability: str, command_name: str, context: dict | None = None) -> list[str]:
    """Resolve a command from the currently active external engine."""
    manager = ResourcePackManager()
    pack_id = manager.external_engine_pack(str(capability), dict(context or {}))
    if not pack_id and capability == "speaker":
        pack_id = manager.warm_engine_pack(capability, context)
    return manager.engine_command(pack_id, str(command_name)) if pack_id else []

"""Independent AI resource packs for the small HaizFlow Core application."""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import threading
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
    models_dir,
    resource_packages_dir,
    resource_storage_dir,
    resource_storage_pointer_path,
)
from haizflow.core.storage_policy import MINIMUM_OPERATIONAL_FREE_BYTES
from haizflow.services.model_bootstrap import (
    ModelAsset,
    ModelBootstrapCancelled,
    ModelProgress,
    install_model_assets,
    required_assets,
)

PACK_PROTOCOL_VERSION = 1
RESOURCE_STATE_VERSION = 1
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
    protocol_version: int = PACK_PROTOCOL_VERSION


def _assets_by_component() -> dict[str, tuple[ModelAsset, ...]]:
    combined = {asset.relative_path: asset for asset in (*required_assets("cpu"), *required_assets("gpu"))}
    grouped: dict[str, list[ModelAsset]] = {}
    for asset in combined.values():
        grouped.setdefault(asset.component, []).append(asset)
    return {key: tuple(sorted(values, key=lambda item: item.relative_path)) for key, values in grouped.items()}


def _alignment_asset(language: str, assets: Iterable[ModelAsset]) -> tuple[ModelAsset, ...]:
    try:
        filename = ALIGNMENT_MODELS[language][1]
    except KeyError:
        return ()
    return tuple(asset for asset in assets if Path(asset.relative_path).name == filename)


def _load_release_pack_metadata() -> dict[str, dict]:
    """Read immutable release metadata without contacting the network.

    Source checkouts intentionally ship empty engine URLs. Release automation
    writes pinned URLs, sizes, and SHA-256 values after each engine archive is
    built and signed. This prevents the application from guessing a mutable
    latest-release URL.
    """
    from haizflow.core.paths import bundle_root, project_root

    candidates = (
        bundle_root() / "RESOURCE-PACKS.json",
        project_root() / "runtime" / "resource-pack-manifest.json",
    )
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("schema") != 1 or payload.get("protocol_version") != PACK_PROTOCOL_VERSION:
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
            engine_modules=("torch", "ctranslate2", "llama_cpp"),
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
            engine_modules=("torch", "torchaudio", "torchvision"),
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
        model_pack(
            "model-whisper-small",
            "Whisper Small",
            "recognition",
            "recognition",
            ("whisper", "whisperx-vad"),
            (),
            backend="cpu",
        ),
        model_pack(
            "model-whisper-turbo",
            "Whisper Large v3 Turbo",
            "recognition",
            "recognition",
            ("whisper-turbo", "whisperx-vad"),
            ("engine-cuda128-py313",),
            backend="gpu",
        ),
        model_pack(
            "model-hymt2-cpu",
            "HY-MT2 CPU",
            "translation",
            "translation",
            ("hymt2-cpu",),
            ("engine-cpu-py313",),
            backend="cpu",
        ),
        model_pack(
            "model-hymt2-gpu",
            "HY-MT2 GPU",
            "translation",
            "translation",
            ("hymt2-gpu",),
            ("engine-cuda128-py313",),
            backend="gpu",
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
        model_pack(
            "model-subtitle-ocr",
            "OCR phụ đề",
            "image",
            "ocr",
            ("subtitle-ocr",),
            ("engine-vision-onnx",),
        ),
    ]
    for language in sorted(ALIGNMENT_MODELS):
        assets = _alignment_asset(language, grouped.get("alignment", ()))
        definitions.append(
            ResourcePackDefinition(
                pack_id=f"model-alignment-{language}",
                label=f"Căn thời gian · {language.upper()}",
                group="recognition",
                version="1",
                capability="alignment",
                backend=language,
                assets=assets,
                download_size=sum(asset.size for asset in assets),
                installed_size=sum(asset.size for asset in assets),
            )
        )
    release_metadata = _load_release_pack_metadata()
    resolved: list[ResourcePackDefinition] = []
    for definition in definitions:
        metadata = release_metadata.get(definition.pack_id, {})
        url = str(metadata.get("url") or "")
        digest = str(metadata.get("sha256") or "").lower()
        try:
            download_size = int(metadata.get("download_size") or definition.download_size)
            installed_size = int(metadata.get("installed_size") or definition.installed_size)
        except (TypeError, ValueError):
            download_size = definition.download_size
            installed_size = definition.installed_size
        if definition.engine_modules and url and len(digest) == 64:
            definition = replace(
                definition,
                version=str(metadata.get("version") or definition.version),
                archive_url=url,
                archive_sha256=digest,
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
    def cleanup_previous_storage() -> None:
        """Remove a moved resource tree; safe to run after the UI is visible."""
        pointer = resource_storage_pointer_path()
        try:
            payload = json.loads(pointer.read_text(encoding="utf-8"))
            previous = Path(str(payload.get("cleanup_previous") or "")).resolve()
            active = Path(str(payload.get("path") or "")).resolve()
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return
        if not str(previous) or previous == active or str(previous).startswith("\\\\"):
            return
        for name in ("models", "engines", "packages"):
            candidate = (previous / name).resolve()
            if candidate.parent != previous:
                continue
            shutil.rmtree(candidate, ignore_errors=True)
        payload.pop("cleanup_previous", None)
        try:
            pointer.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
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

    def snapshot(self) -> list[dict]:
        storage_root = self.storage_root
        usage_path = storage_root
        while not usage_path.exists() and usage_path.parent != usage_path:
            usage_path = usage_path.parent
        usage = shutil.disk_usage(usage_path)
        result = []
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
                    "downloadSize": definition.download_size,
                    "installedSize": self.installed_bytes(definition.pack_id),
                    "location": str(storage_root),
                    "dependencies": list(definition.dependencies),
                    "canInstall": bool(definition.assets or definition.archive_url)
                    and status in {"missing", "paused", "failed"},
                    "canRemove": status == "installed",
                    "blockedReason": (
                        "Bộ xử lý này thuộc bản cài cũ và không thể gỡ riêng."
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
        recognition_model = str(context.get("model") or "small").strip().lower()
        source_language = str(context.get("source_language") or context.get("language") or "").lower().split("-")[0]
        provider = str(context.get("provider") or "omnivoice").lower()
        mapping = {
            "recognition": [
                f"engine-{'cuda128-py313' if device == 'gpu' else 'cpu-py313'}",
                "model-whisper-turbo"
                if device == "gpu" and recognition_model in {"turbo", "large-v3-turbo"}
                else "model-whisper-small",
            ],
            "translation": [
                f"engine-{'cuda128-py313' if device == 'gpu' else 'cpu-py313'}",
                "model-hymt2-gpu" if device == "gpu" else "model-hymt2-cpu",
            ],
            "voice": []
            if provider == "edge"
            else [f"engine-{'cuda128-py313' if device == 'gpu' else 'cpu-py313'}", "model-omnivoice"],
            "separation": [
                f"engine-{'cuda128-py313' if device == 'gpu' else 'cpu-py313'}",
                "model-demucs",
            ],
            "ocr": ["engine-vision-onnx", "model-subtitle-ocr"],
        }
        result = list(mapping.get(str(capability), []))
        if capability == "recognition" and source_language in ALIGNMENT_MODELS:
            result.append(f"model-alignment-{source_language}")
        return result

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

    def engine_command(self, pack_id: str, command_name: str) -> list[str]:
        """Resolve a command declared by an installed engine without shell expansion."""
        definition = self.definitions.get(str(pack_id))
        if definition is None or not definition.engine_modules or not self._engine_is_valid(definition):
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
        download = sum(item.download_size for item in definitions if self.status(item.pack_id) not in ready_states)
        installed = sum(item.installed_size for item in definitions if self.status(item.pack_id) not in ready_states)
        rollback = sum(
            self.installed_bytes(item.pack_id)
            for item in definitions
            if item.engine_modules and self.status(item.pack_id) not in ready_states
        )
        return {
            "downloadBytes": download,
            "installedBytes": installed,
            "rollbackBytes": rollback,
            "requiredBytes": download + installed + rollback + MINIMUM_OPERATIONAL_FREE_BYTES,
            "freeBytes": shutil.disk_usage(self.storage_root).free,
        }

    def _verify_model_pack(self, definition: ResourcePackDefinition) -> None:
        root = models_dir()
        pack_id = definition.pack_id
        if pack_id == "model-whisper-small":
            verify_whisper_model(root / "whisper" / "small")
            verify_whisperx_vad_model(root / "whisperx-vad")
        elif pack_id == "model-whisper-turbo":
            verify_whisper_turbo_model(root / "whisper" / "large-v3-turbo")
            verify_whisperx_vad_model(root / "whisperx-vad")
        elif pack_id == "model-hymt2-cpu":
            verify_cpu_model(root / "hymt2-gguf" / HYMT2_CPU_FILE)
        elif pack_id == "model-hymt2-gpu":
            verify_gpu_model(root / "hymt2-transformers")
        elif pack_id == "model-omnivoice":
            verify_omnivoice_model(root / "omnivoice")
            verify_omnivoice_sdk(root / "omnivoice")
        elif pack_id == "model-demucs":
            verify_demucs_model(root / "demucs")
        elif pack_id == "model-subtitle-ocr":
            verify_subtitle_ocr_models(root / "subtitle-ocr")
        elif pack_id.startswith("model-alignment-"):
            verify_alignment_model(root / "alignment", pack_id.rsplit("-", 1)[-1])

    def install(self, pack_id: str, progress: Callable[[str, ModelProgress], None]) -> None:
        definition = self.definitions[pack_id]
        if definition.engine_modules and definition.archive_url:
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
        finally:
            with self._lock:
                self._active.discard(pack_id)
                self._cancel_events.pop(pack_id, None)

    @staticmethod
    def _safe_extract_zip(archive: Path, destination: Path) -> None:
        destination = destination.resolve()
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                target = (destination / member.filename).resolve()
                if not target.is_relative_to(destination):
                    raise ResourcePackError("Gói tài nguyên chứa đường dẫn không an toàn.")
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)

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
        result = subprocess.run(
            [str(executable), *command[1:]],
            cwd=staging,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
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
            install_model_assets(
                packages,
                (asset,),
                progress=lambda event: progress(definition.pack_id, event),
                cancel_event=cancel,
            )
            archive = packages / package_name
            if staging.exists():
                shutil.rmtree(staging)
            staging.mkdir(parents=True)
            self._safe_extract_zip(archive, staging)
            self._verify_engine_staging(definition, staging)
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
        if in_use:
            raise ResourcePackError("Gói đang được một tác vụ sử dụng.")
        definition = self.definitions[pack_id]
        if self.status(pack_id) == "bundled":
            raise ResourcePackError("Không thể gỡ bộ xử lý được đóng gói trong bản cài cũ.")
        removed = 0
        if definition.engine_modules:
            root = self._engine_marker(definition).parent
            if root.is_dir():
                removed = sum(path.stat().st_size for path in root.rglob("*") if path.is_file())
                shutil.rmtree(root)
            return removed
        root = models_dir()
        for asset in definition.assets:
            shared_by_installed_pack = any(
                other.pack_id != definition.pack_id
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
        return removed

    def clean_unused(self) -> int:
        removed = 0
        for root in (models_dir(), resource_packages_dir(), engines_dir()):
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or not path.name.endswith((".part", ".partial", ".tmp")):
                    continue
                try:
                    removed += path.stat().st_size
                    path.unlink()
                except OSError:
                    pass
        return removed

    def move_storage(self, destination: Path) -> Path:
        destination = destination.expanduser().resolve()
        if str(destination).startswith("\\\\"):
            raise ResourcePackError("Không hỗ trợ ổ mạng cho gói tài nguyên.")
        source = self.storage_root.resolve()
        if destination == source:
            return source
        target = destination / "HaizFlowResources"
        if target.is_relative_to(source) or source.is_relative_to(target):
            raise ResourcePackError("Hãy chọn một thư mục ngoài vị trí tài nguyên hiện tại.")
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
            shutil.rmtree(staging)
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
                    shutil.rmtree(backup)
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
            if promoted and backup is not None and backup.exists():
                shutil.rmtree(target, ignore_errors=True)
                os.replace(backup, target)
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
    return manager.engine_command(pack_id, str(command_name)) if pack_id else []

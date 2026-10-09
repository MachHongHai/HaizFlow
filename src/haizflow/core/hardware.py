"""Hardware-aware runtime policy shared by speech, translation, and rendering."""

from __future__ import annotations

import csv
import ctypes
import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, replace
from functools import lru_cache
from haizflow.core.memory import MemorySnapshot, memory_snapshot

_GIB = 1024 ** 3
# Installed DIMM capacity establishes the public minimum. Usable RAM drives
# inference policy, not an approximation of how much RAM was installed.
_MIN_INSTALLED_RAM_BYTES = 16 * _GIB
_MIN_USABLE_RAM_BYTES = 8 * _GIB
MIN_GPU_VRAM_GIB = 5
_MIN_GPU_VRAM_BYTES = MIN_GPU_VRAM_GIB * _GIB
_FULL_GPU_VRAM_BYTES = 12 * _GIB
_DEVICE_PREFERENCES = {"cpu", "gpu"}
_TRANSLATION_MODELS = {"auto", "q4", "full"}
_WINDOWS_INFO_CACHE: dict = {}
_WINDOWS_INFO_REFRESHING = False
_WINDOWS_INFO_LOCK = threading.Lock()
# CIM data is static for an app session (CPU, driver and adapter details).
# Dynamic telemetry such as VRAM and battery status is collected without
# PowerShell. Avoid launching a shell repeatedly while Settings is closed.
_WINDOWS_INFO_TTL_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class _NvidiaSnapshot:
    name: str = ""
    total_vram_bytes: int = 0
    free_vram_bytes: int = 0
    compute_capability: tuple[int, int] = (0, 0)

    @property
    def available(self) -> bool:
        return bool(self.name and self.total_vram_bytes)


def _ram_capacity_supported(capabilities) -> bool:
    usable = capabilities.total_ram_bytes or 0
    installed = getattr(capabilities, "installed_ram_bytes", None)
    # Known usable capacity proves a lower bound if SMBIOS is unavailable.
    capacity = installed if installed is not None else usable
    return capacity >= _MIN_INSTALLED_RAM_BYTES and usable >= _MIN_USABLE_RAM_BYTES


@dataclass(frozen=True)
class HardwareCapabilities:
    cuda_available: bool
    cuda_name: str
    total_vram_bytes: int
    free_vram_bytes: int
    total_ram_bytes: int
    logical_cpu_count: int
    ac_powered: bool | None
    battery_percent: int | None
    active_display_gpu_name: str = ""
    active_display_gpu_driver: str = ""
    active_display_gpu_resolution: str = ""
    detected_graphics: tuple[str, ...] = ()
    cpu_name: str = ""
    cpu_manufacturer: str = ""
    cpu_physical_cores: int = 0
    cpu_max_mhz: int = 0
    cuda_compute_capability: tuple[int, int] = (0, 0)
    cuda_bf16_supported: bool = False
    installed_ram_bytes: int | None = None

    @property
    def gpu_supported(self) -> bool:
        if not self.cuda_available or self.total_vram_bytes < _MIN_GPU_VRAM_BYTES:
            return False
        # Free VRAM and AC state change during a session. They affect speed or
        # whether a particular load succeeds, not whether the GPU is capable.
        return self.cpu_supported

    @property
    def cpu_supported(self) -> bool:
        return _ram_capacity_supported(self)


@dataclass(frozen=True)
class RuntimeProfile:
    key: str
    label: str
    requested_device: str
    cuda_available: bool
    cuda_name: str
    total_vram_bytes: int
    total_ram_bytes: int
    logical_cpu_count: int
    cpu_threads: int
    whisper_batch_size: int
    hymt2_backend: str
    warm_whisper_on_startup: bool
    warm_hymt2_on_startup: bool
    translation_idle_seconds: int
    hymt2_dtype: str = "float16"

    @property
    def total_ram_gib(self) -> float:
        return self.total_ram_bytes / _GIB if self.total_ram_bytes else 0.0

    @property
    def total_vram_gib(self) -> float:
        return self.total_vram_bytes / _GIB if self.total_vram_bytes else 0.0

    @property
    def is_cpu_only(self) -> bool:
        return not self.cuda_available

    @property
    def summary(self) -> str:
        if self.cuda_available:
            vram = f", {self.total_vram_gib:.0f} GiB VRAM" if self.total_vram_bytes else ""
            return f"GPU acceleration - {self.cuda_name or 'CUDA'}{vram}"
        ram = f"{self.total_ram_gib:.0f} GiB usable RAM" if self.total_ram_bytes else "RAM unknown"
        return f"CPU mode - {ram}, {self.cpu_threads} threads"


def _total_memory_bytes() -> int:
    return memory_snapshot().usable_bytes or 0


def available_memory_bytes(*, commit: bool = False) -> int:
    """Legacy integer API. New admission checks use MemorySnapshot for unknowns."""
    snapshot = memory_snapshot()
    return (snapshot.commit_available_bytes if commit else snapshot.available_bytes) or 0


def available_commit_bytes() -> int:
    """Windows commit headroom, distinct from free RAM or free paging-file space."""
    return available_memory_bytes(commit=True)


def _nvidia_smi_path() -> str:
    located = shutil.which("nvidia-smi")
    if located:
        return located
    if os.name == "nt":
        candidates = (
            os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "nvidia-smi.exe"),
            os.path.join(
                os.environ.get("ProgramFiles", r"C:\Program Files"),
                "NVIDIA Corporation",
                "NVSMI",
                "nvidia-smi.exe",
            ),
        )
        for candidate in candidates:
            if os.path.isfile(candidate):
                return candidate
    return ""


def _run_nvidia_query(fields: tuple[str, ...]) -> list[str]:
    executable = _nvidia_smi_path()
    if not executable:
        return []
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        result = subprocess.run(
            [
                executable,
                f"--query-gpu={','.join(fields)}",
                "--format=csv,noheader,nounits",
                "--id=0",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            check=False,
            creationflags=creationflags,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    rows = list(csv.reader(line for line in result.stdout.splitlines() if line.strip()))
    return [value.strip() for value in rows[0]] if rows else []


@lru_cache(maxsize=1)
def _nvidia_snapshot() -> _NvidiaSnapshot:
    values = _run_nvidia_query(("name", "memory.total", "memory.free", "compute_cap"))
    if len(values) != 4:
        values = _run_nvidia_query(("name", "memory.total", "memory.free"))
    if len(values) < 3:
        return _NvidiaSnapshot()
    try:
        total = int(float(values[1])) * 1024**2
        free = int(float(values[2])) * 1024**2
    except (TypeError, ValueError):
        return _NvidiaSnapshot()
    capability = (0, 0)
    if len(values) > 3:
        try:
            major, minor = values[3].split(".", 1)
            capability = (int(major), int(minor))
        except (TypeError, ValueError):
            capability = (0, 0)
    return _NvidiaSnapshot(values[0], total, free, capability)


def _cuda_details() -> tuple[bool, str]:
    snapshot = _nvidia_snapshot()
    return snapshot.available, snapshot.name


def _cuda_memory_bytes() -> int:
    return _nvidia_snapshot().total_vram_bytes


def _cuda_free_memory_bytes() -> int:
    """Return free VRAM without allocating a model; zero means unavailable."""
    return _nvidia_snapshot().free_vram_bytes


def _cuda_precision_details() -> tuple[tuple[int, int], bool]:
    """Return the active CUDA architecture and its safe HY-MT2 precision."""
    capability = _nvidia_snapshot().compute_capability
    # NVIDIA Ampere (SM 8.x) and newer provide native BF16 tensor support.
    # The engine smoke/probe remains the final authority before inference.
    return capability, capability[0] >= 8


def _power_status() -> tuple[bool | None, int | None]:
    """Return AC status and battery percentage when Windows exposes them."""
    if os.name != "nt":
        return None, None

    class SystemPowerStatus(ctypes.Structure):
        _fields_ = [
            ("ACLineStatus", ctypes.c_ubyte),
            ("BatteryFlag", ctypes.c_ubyte),
            ("BatteryLifePercent", ctypes.c_ubyte),
            ("SystemStatusFlag", ctypes.c_ubyte),
            ("BatteryLifeTime", ctypes.c_uint32),
            ("BatteryFullLifeTime", ctypes.c_uint32),
        ]

    status = SystemPowerStatus()
    try:
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            return None, None
    except (AttributeError, OSError):
        return None, None
    ac_powered = {0: False, 1: True}.get(int(status.ACLineStatus))
    battery_percent = None if status.BatteryLifePercent == 255 else int(status.BatteryLifePercent)
    return ac_powered, battery_percent


def _normalize_cim_items(value) -> list[dict]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _read_windows_system_info() -> dict:
    """Read display and CPU metadata without using CUDA's static device list."""
    if os.name != "nt":
        return {}
    command = (
        "$video = Get-CimInstance Win32_VideoController | Select-Object "
        "Name,VideoProcessor,CurrentHorizontalResolution,CurrentVerticalResolution,"
        "CurrentBitsPerPixel,DriverVersion,Availability; "
        "$cpu = Get-CimInstance Win32_Processor | Select-Object "
        "Name,Manufacturer,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed; "
        "[pscustomobject]@{video=$video;cpu=$cpu} | ConvertTo-Json -Depth 4 -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {}
        payload = json.loads(result.stdout.lstrip("\ufeff").strip())
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return {}

    adapters = _normalize_cim_items(payload.get("video"))
    active = next(
        (
            adapter for adapter in adapters
            if int(adapter.get("CurrentHorizontalResolution") or 0) > 0
            and int(adapter.get("CurrentVerticalResolution") or 0) > 0
        ),
        None,
    )
    if active is None:
        active = next((adapter for adapter in adapters if int(adapter.get("Availability") or 0) == 3), None)
    cpu_items = _normalize_cim_items(payload.get("cpu"))
    cpu = cpu_items[0] if cpu_items else {}
    width = int((active or {}).get("CurrentHorizontalResolution") or 0)
    height = int((active or {}).get("CurrentVerticalResolution") or 0)
    return {
        "active_display_gpu_name": str((active or {}).get("Name") or ""),
        "active_display_gpu_driver": str((active or {}).get("DriverVersion") or ""),
        "active_display_gpu_resolution": f"{width} x {height}" if width and height else "",
        "detected_graphics": tuple(str(adapter.get("Name") or "") for adapter in adapters if adapter.get("Name")),
        "cpu_name": str(cpu.get("Name") or ""),
        "cpu_manufacturer": str(cpu.get("Manufacturer") or ""),
        "cpu_physical_cores": int(cpu.get("NumberOfCores") or 0),
        "cpu_max_mhz": int(cpu.get("MaxClockSpeed") or 0),
    }


def _windows_system_info() -> dict:
    """Return cached platform telemetry and refresh it off the UI thread."""
    global _WINDOWS_INFO_REFRESHING
    if os.name != "nt":
        return {}
    now = time.monotonic()
    with _WINDOWS_INFO_LOCK:
        cached_at = float(_WINDOWS_INFO_CACHE.get("timestamp", 0.0))
        stale = now - cached_at >= _WINDOWS_INFO_TTL_SECONDS
        if stale and not _WINDOWS_INFO_REFRESHING:
            _WINDOWS_INFO_REFRESHING = True

            def refresh():
                global _WINDOWS_INFO_REFRESHING
                details = _read_windows_system_info()
                with _WINDOWS_INFO_LOCK:
                    if details:
                        _WINDOWS_INFO_CACHE.clear()
                        _WINDOWS_INFO_CACHE.update(details)
                        _WINDOWS_INFO_CACHE["timestamp"] = time.monotonic()
                    _WINDOWS_INFO_REFRESHING = False

            threading.Thread(target=refresh, name="hardware-telemetry", daemon=True).start()
        return {key: value for key, value in _WINDOWS_INFO_CACHE.items() if key != "timestamp"}


def detect_hardware_capabilities() -> HardwareCapabilities:
    """Probe live hardware telemetry without changing the active runtime profile."""
    # The snapshot is cached only so the several CUDA fields in this one
    # probe share a single nvidia-smi query. A failed first query must not
    # report "no GPU" forever when the driver finishes starting later.
    _nvidia_snapshot.cache_clear()
    cuda_available, cuda_name = _cuda_details()
    cuda_compute_capability, cuda_bf16_supported = (
        _cuda_precision_details() if cuda_available else ((0, 0), False)
    )
    ac_powered, battery_percent = _power_status()
    system_info = _windows_system_info()
    memory = memory_snapshot()
    return HardwareCapabilities(
        cuda_available=cuda_available,
        cuda_name=cuda_name,
        total_vram_bytes=_cuda_memory_bytes() if cuda_available else 0,
        free_vram_bytes=_cuda_free_memory_bytes() if cuda_available else 0,
        total_ram_bytes=memory.usable_bytes or 0,
        installed_ram_bytes=memory.installed_bytes,
        logical_cpu_count=max(1, os.cpu_count() or 1),
        ac_powered=ac_powered,
        battery_percent=battery_percent,
        active_display_gpu_name=system_info.get("active_display_gpu_name", ""),
        active_display_gpu_driver=system_info.get("active_display_gpu_driver", ""),
        active_display_gpu_resolution=system_info.get("active_display_gpu_resolution", ""),
        detected_graphics=tuple(system_info.get("detected_graphics", ())),
        cpu_name=system_info.get("cpu_name", ""),
        cpu_manufacturer=system_info.get("cpu_manufacturer", ""),
        cpu_physical_cores=int(system_info.get("cpu_physical_cores", 0)),
        cpu_max_mhz=int(system_info.get("cpu_max_mhz", 0)),
        cuda_compute_capability=cuda_compute_capability,
        cuda_bf16_supported=cuda_bf16_supported,
    )


def basic_hardware_capabilities() -> HardwareCapabilities:
    """Return cheap host telemetry without importing Torch or initializing CUDA.

    The desktop uses this snapshot for its first frame.  Full CUDA detection is
    deliberately deferred to the model warm-up worker because importing Torch
    and initializing the driver can take several seconds on Windows.
    """
    ac_powered, battery_percent = _power_status()
    system_info = _windows_system_info()
    memory = memory_snapshot()
    return HardwareCapabilities(
        cuda_available=False,
        cuda_name="",
        total_vram_bytes=0,
        free_vram_bytes=0,
        total_ram_bytes=memory.usable_bytes or 0,
        installed_ram_bytes=memory.installed_bytes,
        logical_cpu_count=max(1, os.cpu_count() or 1),
        ac_powered=ac_powered,
        battery_percent=battery_percent,
        active_display_gpu_name=system_info.get("active_display_gpu_name", ""),
        active_display_gpu_driver=system_info.get("active_display_gpu_driver", ""),
        active_display_gpu_resolution=system_info.get("active_display_gpu_resolution", ""),
        detected_graphics=tuple(system_info.get("detected_graphics", ())),
        cpu_name=system_info.get("cpu_name", ""),
        cpu_manufacturer=system_info.get("cpu_manufacturer", ""),
        cpu_physical_cores=int(system_info.get("cpu_physical_cores", 0)),
        cpu_max_mhz=int(system_info.get("cpu_max_mhz", 0)),
    )


def processing_device_preference() -> str:
    if os.getenv("HAIZFLOW_FORCE_CPU", "").strip().lower() in {"1", "true", "yes"}:
        return "cpu"
    preference = os.getenv("HAIZFLOW_PROCESSING_DEVICE", "cpu").strip().lower()
    return preference if preference in _DEVICE_PREFERENCES else "cpu"


def translation_model_preference() -> str:
    preference = os.getenv("HAIZFLOW_TRANSLATION_MODEL", "auto").strip().lower()
    return preference if preference in _TRANSLATION_MODELS else "auto"


def translation_model_signature_parts(preference: str | None = None) -> tuple[str, ...]:
    """Keep legacy automatic caches valid; explicit model choices get distinct caches."""
    preference = preference or translation_model_preference()
    return () if preference == "auto" else (f"translation-model:{preference}",)


def configure_translation_model(preference: str) -> str:
    normalized = preference if preference in _TRANSLATION_MODELS else "auto"
    os.environ["HAIZFLOW_TRANSLATION_MODEL"] = normalized
    return normalized


@lru_cache(maxsize=1)
def hardware_capabilities() -> HardwareCapabilities:
    return detect_hardware_capabilities()


def recommended_processing_device(capabilities: HardwareCapabilities | None = None) -> str:
    """Choose the fastest safe device for the current live hardware state."""
    capabilities = capabilities or detect_hardware_capabilities()
    return "gpu" if capabilities.gpu_supported else "cpu"


def validate_processing_device(
    preference: str,
    capabilities: HardwareCapabilities | None = None,
    *, language: str = "en",
) -> tuple[bool, str]:
    preference = preference if preference in _DEVICE_PREFERENCES else "cpu"
    capabilities = capabilities or detect_hardware_capabilities()
    if preference == "gpu":
        if not capabilities.cuda_available:
            return False, "Không phát hiện GPU NVIDIA tương thích CUDA." if language == "vi" else "CUDA-compatible NVIDIA GPU was not detected."
        if capabilities.total_vram_bytes < _MIN_GPU_VRAM_BYTES:
            available = capabilities.total_vram_bytes / _GIB
            return False, (f"Cần GPU NVIDIA 6 GB (ít nhất 5 GiB VRAM khả dụng); hiện có {available:.1f} GiB." if language == "vi" else
                f"GPU mode requires a 6 GB NVIDIA GPU (at least 5 GiB usable VRAM); detected {available:.1f} GiB."
            )
    installed = getattr(capabilities, "installed_ram_bytes", None)
    usable = capabilities.total_ram_bytes
    installed_text = "chưa xác định" if installed is None else f"{installed / _GIB:.1f} GiB"
    usable_text = "chưa xác định" if not usable else f"{usable / _GIB:.1f} GiB"
    if not _ram_capacity_supported(capabilities):
        if language == "vi":
            return False, (
                f"HaizFlow cần RAM lắp đặt từ 16 GB (16 GiB) và ít nhất 8 GiB RAM Windows sử dụng được. "
                f"RAM lắp đặt: {installed_text}; Windows sử dụng được: {usable_text}. "
                "Kiểm tra lại cấu hình/bộ nhớ dành riêng cho phần cứng nếu số liệu chưa đúng."
            )
        installed_en = "unknown" if installed is None else f"{installed / _GIB:.1f} GiB"
        usable_en = "unknown" if not usable else f"{usable / _GIB:.1f} GiB"
        return False, (
            "HaizFlow requires 16 GB installed RAM (16 GiB DIMM capacity) and at least 8 GiB OS-usable RAM; "
            f"installed: {installed_en}; OS-usable: {usable_en}. Check hardware memory detection/reservation."
        )
    if preference == "gpu":
        return True, (f"GPU sẵn sàng: {capabilities.cuda_name}, {capabilities.total_vram_bytes / _GIB:.1f} GiB VRAM." if language == "vi" else
                      f"GPU ready: {capabilities.cuda_name}, {capabilities.total_vram_bytes / _GIB:.1f} GiB VRAM.")
    return True, (f"CPU sẵn sàng: Windows sử dụng được {usable / _GIB:.1f} GiB RAM, {capabilities.logical_cpu_count} luồng logic." if language == "vi" else
                  f"CPU ready: {usable / _GIB:.1f} GiB OS-usable RAM, {capabilities.logical_cpu_count} logical processors.")


def configure_processing_device(preference: str) -> str:
    normalized = preference if preference in _DEVICE_PREFERENCES else "cpu"
    os.environ["HAIZFLOW_PROCESSING_DEVICE"] = normalized
    os.environ.pop("HAIZFLOW_FORCE_CPU", None)
    clear_runtime_profile_cache()
    return normalized


@lru_cache(maxsize=1)
def runtime_profile() -> RuntimeProfile:
    """Detect a conservative profile that remains usable on CPU-only PCs."""
    return runtime_profile_for(hardware_capabilities(), processing_device_preference())


def runtime_profile_for(
    capabilities: HardwareCapabilities,
    preference: str | None = None,
) -> RuntimeProfile:
    """Build a runtime profile from an existing, non-blocking snapshot."""
    preference = preference or processing_device_preference()
    preference = preference if preference in _DEVICE_PREFERENCES else "cpu"
    use_cuda = capabilities.gpu_supported and preference == "gpu"
    total_ram = capabilities.total_ram_bytes
    logical_cpus = capabilities.logical_cpu_count

    if use_cuda:
        low_vram = capabilities.total_vram_bytes < _FULL_GPU_VRAM_BYTES
        constrained_memory = low_vram or (total_ram > 0 and total_ram < 24 * _GIB)
        return RuntimeProfile(
            key="cuda_low_memory" if low_vram else "cuda",
            label="GPU low memory" if low_vram else "GPU accelerated",
            requested_device=preference,
            cuda_available=True,
            cuda_name=capabilities.cuda_name,
            total_vram_bytes=capabilities.total_vram_bytes,
            total_ram_bytes=total_ram,
            logical_cpu_count=logical_cpus,
            cpu_threads=max(1, min(8, logical_cpus - 1 if logical_cpus > 2 else logical_cpus)),
            whisper_batch_size=2 if capabilities.total_vram_bytes < 7 * _GIB else 8 if low_vram else 16,
            # CUDA keeps the official checkpoint. Precision is selected from
            # the active GPU architecture without changing model quality.
            hymt2_backend="transformers",
            warm_whisper_on_startup=not constrained_memory,
            warm_hymt2_on_startup=not constrained_memory,
            # Low-memory workers are loaded on demand and released shortly
            # after use instead of pinning model weights for the whole session.
            translation_idle_seconds=30 if constrained_memory else 0,
            hymt2_dtype="bfloat16" if capabilities.cuda_bf16_supported else "float16",
        )

    total_gib = total_ram / _GIB if total_ram else 0
    # Installed capacity decides eligibility; usable capacity decides workload.
    # A 16 GB installation must not retain multiple heavy CPU models.
    if total_gib >= 24:
        key = "cpu_balanced"
        label = "CPU balanced"
        batch_size = 4
        cpu_threads = max(1, min(8, logical_cpus - 1 if logical_cpus > 2 else logical_cpus))
        idle_seconds = 300
    elif total_gib >= 7:
        key = "cpu_low_memory"
        label = "CPU low memory"
        batch_size = 2
        cpu_threads = max(1, min(4, logical_cpus - 1 if logical_cpus > 2 else logical_cpus))
        idle_seconds = 90
    else:
        key = "cpu_minimum"
        label = "CPU minimum memory"
        batch_size = 1
        cpu_threads = max(1, min(2, logical_cpus))
        idle_seconds = 30

    return RuntimeProfile(
        key=key,
        label=label,
        requested_device=preference,
        cuda_available=False,
        cuda_name="",
        total_vram_bytes=capabilities.total_vram_bytes,
        total_ram_bytes=total_ram,
        logical_cpu_count=logical_cpus,
        cpu_threads=cpu_threads,
        whisper_batch_size=batch_size,
        hymt2_backend="llama_cpp",
        # Avoid competing with the desktop and OS on constrained RAM. The
        # model will still load on demand when the user starts a project.
        warm_whisper_on_startup=key == "cpu_balanced",
        warm_hymt2_on_startup=False,
        translation_idle_seconds=idle_seconds,
        hymt2_dtype="float32",
    )


def cpu_runtime_profile(profile: RuntimeProfile | None = None, *, memory: MemorySnapshot | None = None, force_cpu: bool = False) -> RuntimeProfile:
    """Downsize CPU work from live budgets; do not change inference precision.

    Called at task boundaries, not in the UI. Never increase a cached profile's
    batches/threads on the strength of a transient free-memory measurement.
    """
    profile = profile or runtime_profile()
    if profile.cuda_available:
        if not force_cpu:
            return profile
        profile = runtime_profile_for(hardware_capabilities(), "cpu")
    memory = memory if memory is not None else memory_snapshot()
    free = memory.available_bytes
    commit = memory.commit_available_bytes
    unknown = free is None or (os.name == "nt" and commit is None)
    tight = unknown or free < 3 * _GIB or (commit is not None and commit < 4 * _GIB)
    constrained = tight or free < 6 * _GIB or (commit is not None and commit < 8 * _GIB)
    if not constrained:
        return profile
    return replace(
        profile, key="cpu_minimum" if tight else "cpu_low_memory",
        label="CPU memory constrained", cpu_threads=min(profile.cpu_threads, 2 if tight else 4),
        whisper_batch_size=min(profile.whisper_batch_size, 1 if tight else 2),
        warm_whisper_on_startup=False, warm_hymt2_on_startup=False,
        translation_idle_seconds=min(profile.translation_idle_seconds, 30 if tight else 90),
    )


def clear_runtime_profile_cache() -> None:
    """Test helper for environment-forced hardware profiles."""
    runtime_profile.cache_clear()
    hardware_capabilities.cache_clear()
    _nvidia_snapshot.cache_clear()

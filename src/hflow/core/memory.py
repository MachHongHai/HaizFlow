"""Lightweight memory telemetry; unknown (None) is not exhausted (zero).

All values are bytes. Windows physical capacity and commit are different
budgets: virtual address space and free page-file space are neither of these.
"""

from __future__ import annotations

import ctypes
import logging
import os
import time
from dataclasses import dataclass

GIB = 1024**3
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class MemorySnapshot:
    installed_bytes: int | None = None
    usable_bytes: int | None = None
    available_bytes: int | None = None
    commit_limit_bytes: int | None = None
    commit_used_bytes: int | None = None
    process_commit_available_bytes: int | None = None

    @property
    def commit_available_bytes(self) -> int | None:
        system = None
        if self.commit_limit_bytes is not None and self.commit_used_bytes is not None:
            system = max(0, self.commit_limit_bytes - self.commit_used_bytes)
        budgets = [value for value in (system, self.process_commit_available_bytes) if value is not None]
        return min(budgets) if budgets else None

    def diagnostic(self) -> str:
        def gib(value):
            return "unknown" if value is None else f"{value / GIB:.2f}GiB"
        return " ".join(f"{name}={gib(value)}" for name, value in (
            ("installed", self.installed_bytes), ("usable", self.usable_bytes),
            ("available", self.available_bytes), ("commit_limit", self.commit_limit_bytes),
            ("commit_used", self.commit_used_bytes), ("commit_headroom", self.commit_available_bytes),
        ))


class _MemoryStatus(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_uint32), ("dwMemoryLoad", ctypes.c_uint32)] + [
        (name, ctypes.c_uint64) for name in (
            "ullTotalPhys", "ullAvailPhys", "ullTotalPageFile", "ullAvailPageFile",
            "ullTotalVirtual", "ullAvailVirtual", "ullAvailExtendedVirtual",
        )
    ]


class _PerformanceInfo(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_uint32)] + [
        (name, ctypes.c_size_t) for name in (
            "CommitTotal", "CommitLimit", "CommitPeak", "PhysicalTotal", "PhysicalAvailable",
            "SystemCache", "KernelTotal", "KernelPaged", "KernelNonpaged", "PageSize",
        )
    ] + [(name, ctypes.c_uint32) for name in ("HandleCount", "ProcessCount", "ThreadCount")]


def _windows_memory_snapshot(kernel32) -> MemorySnapshot:
    installed = usable = available = process_commit = limit = used = None
    status = _MemoryStatus()
    status.dwLength = ctypes.sizeof(status)
    try:
        if kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            usable = int(status.ullTotalPhys) or None
            available = int(status.ullAvailPhys)
            process_commit = int(status.ullAvailPageFile)
    except (AttributeError, OSError):
        pass
    kib = ctypes.c_uint64()
    try:
        if kernel32.GetPhysicallyInstalledSystemMemory(ctypes.byref(kib)) and kib.value:
            installed = int(kib.value) * 1024  # This API returns KiB, not bytes.
    except (AttributeError, OSError):
        pass
    if installed is not None and usable is not None and installed < usable:
        installed = None  # Invalid SMBIOS data must not establish eligibility.
    performance = _PerformanceInfo()
    performance.cb = ctypes.sizeof(performance)
    try:
        if kernel32.K32GetPerformanceInfo(ctypes.byref(performance), performance.cb) and performance.PageSize:
            limit = int(performance.CommitLimit * performance.PageSize)
            used = int(performance.CommitTotal * performance.PageSize)
            if used > limit:
                limit = used = None
    except (AttributeError, OSError):
        pass
    return MemorySnapshot(installed, usable, available, limit, used, process_commit)


def memory_snapshot() -> MemorySnapshot:
    """Read live counters without Torch, PowerShell, psutil or cached free RAM."""
    if os.name == "nt":
        try:
            return _windows_memory_snapshot(ctypes.windll.kernel32)
        except (AttributeError, OSError):
            return MemorySnapshot()
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        usable = int(os.sysconf("SC_PHYS_PAGES") * page_size)
        available = int(os.sysconf("SC_AVPHYS_PAGES") * page_size)
        return MemorySnapshot(usable_bytes=usable, available_bytes=available)
    except (AttributeError, OSError, ValueError):
        return MemorySnapshot()


# Admission reserves, not measured peak-RSS promises. Pinned OmniVoice tensor
# headers contain ~3.03 GiB FP32 weights (model + codec); allow another ~3 GiB
# for imports, loading and synthesis buffers. No precision/checkpoint change.
CPU_STAGE_RESERVES = {
    "recognition": (1 * GIB, 3 * GIB),
    "translation": (1 * GIB, 3 * GIB),
    "separation": (int(1.5 * GIB), 4 * GIB),
    "voice": (2 * GIB, 6 * GIB),
}


def cpu_memory_constrained(snapshot: MemorySnapshot | None = None) -> bool:
    snapshot = snapshot if snapshot is not None else memory_snapshot()
    return (
        snapshot.usable_bytes is None or snapshot.usable_bytes < 24 * GIB
        or snapshot.available_bytes is None or snapshot.available_bytes < 6 * GIB
        or (os.name == "nt" and snapshot.commit_available_bytes is None)
        or (snapshot.commit_available_bytes is not None and snapshot.commit_available_bytes < 8 * GIB)
    )


def require_cpu_memory(stage: str, *, resident: bool = False, snapshot: MemorySnapshot | None = None,
                       settle_seconds: float = 0) -> None:
    """Check immediately before CPU inference. Call after idle-model release.

    Existing resident weights are already charged to commit; only their working
    reserve is required again. This check cannot prevent other apps racing us.
    """
    supplied = snapshot is not None
    snapshot = snapshot if supplied else memory_snapshot()
    physical, commit = CPU_STAGE_RESERVES[stage] if not resident else (GIB // 2, GIB)
    # Windows can report the just-retired worker's commit/working set briefly.
    # A bounded fresh measurement may admit it; never lower either reserve.
    if not supplied and settle_seconds > 0:
        deadline = time.monotonic() + min(float(settle_seconds), 2.0)
        while (snapshot.available_bytes is not None
               and (os.name != "nt" or snapshot.commit_available_bytes is not None)
               and (snapshot.available_bytes < physical
                    or (snapshot.commit_available_bytes is not None and snapshot.commit_available_bytes < commit))):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(0.2, remaining))
            snapshot = memory_snapshot()
    LOGGER.info("CPU memory preflight stage=%s resident=%s %s", stage, resident, snapshot.diagnostic())
    if snapshot.available_bytes is None or (os.name == "nt" and snapshot.commit_available_bytes is None):
        raise RuntimeError("Không đọc được bộ nhớ RAM/bộ nhớ hệ thống Windows. Hãy kiểm tra lại cấu hình trước khi xử lý.")
    if snapshot.available_bytes < physical or (
        snapshot.commit_available_bytes is not None and snapshot.commit_available_bytes < commit
    ):
        remaining = snapshot.commit_available_bytes
        label = {"recognition": "Whisper", "translation": "HY-MT2 Q4", "separation": "Demucs", "voice": "OmniVoice"}[stage]
        headroom = "chưa xác định" if remaining is None else f"{remaining / GIB:.1f} GiB"
        raise RuntimeError(
            f"Chưa đủ bộ nhớ để chạy {label} trên CPU: RAM trống {snapshot.available_bytes / GIB:.1f} GiB; "
            f"bộ nhớ Windows còn cấp phát được {headroom}. Cần ít nhất {physical / GIB:.1f} GiB RAM trống "
            f"và {commit / GIB:.1f} GiB bộ nhớ cấp phát. Đóng ứng dụng khác hoặc để Windows tự quản lý bộ nhớ ảo rồi thử lại."
        )

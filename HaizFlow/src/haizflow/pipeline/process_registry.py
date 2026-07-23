import os
import subprocess
import threading
from typing import Dict, List, Set

from haizflow.config import MEDIA_PROCESS_TIMEOUT_SECONDS


_cancelled_videos: Set[str] = set()
_paused_videos: Set[str] = set()
_active_processes: Dict[str, List[subprocess.Popen]] = {}
_windows_job_handles: Dict[int, object] = {}
_REGISTRY_LOCK = threading.RLock()


def _attach_windows_kill_on_close_job(process: subprocess.Popen) -> None:
    """Place a child process tree in a Windows Job Object killed with HaizFlow."""
    with _REGISTRY_LOCK:
        if os.name != "nt" or id(process) in _windows_job_handles:
            return
    try:
        import ctypes
        from ctypes import wintypes

        class JobObjectBasicLimitInformation(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IoCounters(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class JobObjectExtendedLimitInformation(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JobObjectBasicLimitInformation),
                ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        )
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL

        job_handle = kernel32.CreateJobObjectW(None, None)
        if not job_handle:
            return
        information = JobObjectExtendedLimitInformation()
        information.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        configured = kernel32.SetInformationJobObject(
            job_handle,
            9,  # JobObjectExtendedLimitInformation
            ctypes.byref(information),
            ctypes.sizeof(information),
        )
        process_handle = wintypes.HANDLE(int(process._handle))
        if not configured or not kernel32.AssignProcessToJobObject(job_handle, process_handle):
            kernel32.CloseHandle(job_handle)
            return
        with _REGISTRY_LOCK:
            _windows_job_handles[id(process)] = job_handle
    except (AttributeError, OSError, TypeError, ValueError):
        return


def _release_windows_job(process: subprocess.Popen, *, force: bool = False) -> None:
    if os.name != "nt" or (process.poll() is None and not force):
        return
    with _REGISTRY_LOCK:
        handle = _windows_job_handles.pop(id(process), None)
    if handle is None:
        return
    try:
        import ctypes

        ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(handle)
    except (AttributeError, OSError, TypeError, ValueError):
        pass


def start_video(video_id: str):
    with _REGISTRY_LOCK:
        _cancelled_videos.discard(video_id)
        _paused_videos.discard(video_id)
        _active_processes[video_id] = []


def _kill_process_tree(process: subprocess.Popen, timeout: float = 1.5):
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=max(1.0, min(timeout, 5.0)),
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            try:
                process.kill()
            except Exception:
                pass
    else:
        try:
            process.kill()
        except Exception:
            pass
    if process.poll() is None:
        try:
            process.kill()
        except Exception:
            pass
    try:
        process.wait(timeout=timeout)
    except Exception:
        pass


def cancel_video(video_id: str):
    """Atomically mark a video cancelled and stop every registered child."""
    with _REGISTRY_LOCK:
        _cancelled_videos.add(video_id)
        processes = list(_active_processes.get(video_id, ()))
        _active_processes[video_id] = []
    # Do not hold the registry lock while waiting for operating-system process
    # teardown.  A process registered after the snapshot is still killed by
    # register_process because the cancellation flag remains set.
    for process in processes:
        _kill_process_tree(process)
        _release_windows_job(process, force=True)


def pause_video(video_id: str):
    with _REGISTRY_LOCK:
        _paused_videos.add(video_id)
    cancel_video(video_id)


def is_paused(video_id: str) -> bool:
    with _REGISTRY_LOCK:
        return video_id in _paused_videos


def is_cancelled(video_id: str) -> bool:
    with _REGISTRY_LOCK:
        return video_id in _cancelled_videos


def check_cancellation(video_id: str):
    if is_cancelled(video_id):
        raise RuntimeError("Video cancelled by user.")


def register_process(video_id: str, process: subprocess.Popen):
    """Register a process without a cancel/register race."""
    with _REGISTRY_LOCK:
        cancelled = video_id in _cancelled_videos
        if not cancelled:
            _attach_windows_kill_on_close_job(process)
            _active_processes.setdefault(video_id, []).append(process)
    if cancelled:
        _kill_process_tree(process)
        raise RuntimeError("Video cancelled by user.")


def unregister_process(video_id: str, process: subprocess.Popen, *, force: bool = False):
    with _REGISTRY_LOCK:
        try:
            _active_processes.get(video_id, []).remove(process)
        except ValueError:
            pass
    _release_windows_job(process, force=force)


def communicate_process(
    video_id: str,
    process: subprocess.Popen,
    *,
    label: str,
    timeout_seconds: float = MEDIA_PROCESS_TIMEOUT_SECONDS,
) -> tuple[str, str]:
    """Wait for a registered media process with cancellation-safe cleanup."""
    registered = False
    force_release = False
    try:
        register_process(video_id, process)
        registered = True
        return process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        force_release = True
        _kill_process_tree(process)
        raise RuntimeError(f"{label} timed out after {timeout_seconds} seconds.") from exc
    except Exception:
        force_release = True
        _kill_process_tree(process)
        raise
    finally:
        if registered:
            unregister_process(video_id, process, force=force_release or process.poll() is None)


def clean_video(video_id: str):
    with _REGISTRY_LOCK:
        _cancelled_videos.discard(video_id)
        _paused_videos.discard(video_id)
        processes = _active_processes.pop(video_id, [])
    for process in processes:
        _kill_process_tree(process)
        _release_windows_job(process, force=True)

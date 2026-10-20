import threading
import queue
import json
import sys
import subprocess
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

from haizflow.core import hardware
from haizflow.desktop.runtime_device_controller import RuntimeDeviceController


def test_first_probe_runs_before_one_day_of_windows_uptime():
    worker = Mock()
    with patch.object(hardware, "os", SimpleNamespace(name="nt")), \
         patch.object(hardware, "_WINDOWS_INFO_CACHE", {}), \
         patch.object(hardware, "_WINDOWS_INFO_REFRESHING", False), \
         patch.object(hardware, "_read_windows_cpu_info", return_value={}), \
         patch.object(hardware.time, "monotonic", return_value=20), \
         patch.object(hardware.threading, "Thread", return_value=worker):
        hardware._windows_system_info()
        worker.start.assert_called_once()


def test_unexpected_metadata_failure_does_not_leave_refresh_locked():
    class ImmediateThread:
        def __init__(self, *, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

    with patch.object(hardware, "os", SimpleNamespace(name="nt")), \
         patch.object(hardware, "_WINDOWS_INFO_CACHE", {}), \
         patch.object(hardware, "_WINDOWS_INFO_REFRESHING", False), \
         patch.object(hardware, "_read_windows_cpu_info", return_value={}), \
         patch.object(hardware, "_WINDOWS_INFO_LOCK", threading.Lock()), \
         patch.object(hardware.time, "monotonic", return_value=100000), \
         patch.object(hardware, "_read_windows_system_info", side_effect=ValueError("bad CIM field")), \
         patch.object(hardware.threading, "Thread", ImmediateThread):
        hardware._windows_system_info()
        assert not hardware._WINDOWS_INFO_REFRESHING


def test_cpu_registry_fallback_identifies_ryzen_without_wmi():
    key = Mock()
    context = Mock(__enter__=Mock(return_value=key), __exit__=Mock(return_value=False))
    values = {"ProcessorNameString": " AMD Ryzen 7 PRO 4750G with Radeon Graphics ",
              "VendorIdentifier": "AuthenticAMD", "~MHz": 3600}
    registry = SimpleNamespace(HKEY_LOCAL_MACHINE=1, OpenKey=Mock(return_value=context),
        QueryValueEx=Mock(side_effect=lambda _, name: (values[name], 1)))
    with patch.object(hardware, "os", SimpleNamespace(name="nt", environ={})), \
         patch.dict(sys.modules, {"winreg": registry}):
        result = hardware._read_windows_cpu_info()
    assert result == {"cpu_name": "AMD Ryzen 7 PRO 4750G with Radeon Graphics",
                      "cpu_manufacturer": "AuthenticAMD", "cpu_max_mhz": 3600}


def test_cpu_logical_count_is_not_the_processing_thread_budget():
    worker = Mock()
    with patch.object(hardware, "os", SimpleNamespace(name="nt", cpu_count=lambda: 16)), \
         patch.object(hardware, "_WINDOWS_INFO_CACHE", {}), \
         patch.object(hardware, "_WINDOWS_INFO_REFRESHING", False), \
         patch.object(hardware, "_read_windows_cpu_info", return_value={"cpu_name": "Ryzen 7 PRO 4750G"}), \
         patch.object(hardware, "_power_status", return_value=(True, None)), \
         patch.object(hardware, "memory_snapshot", return_value=SimpleNamespace(
             usable_bytes=16 * 1024**3, installed_bytes=16 * 1024**3)), \
         patch.object(hardware.threading, "Thread", return_value=worker):
        capabilities = hardware.basic_hardware_capabilities()
    assert capabilities.cpu_name == "Ryzen 7 PRO 4750G"
    assert capabilities.logical_cpu_count == 16
    assert hardware.runtime_profile_for(capabilities, "cpu").cpu_threads == 4


def test_cim_probe_tolerates_bad_fields_and_inherited_pwsh_module_paths():
    payload = {"cpu": {"Name": "Ryzen 7 PRO 4750G", "NumberOfCores": 8, "MaxClockSpeed": "unknown"},
               "video": {"Name": "Radeon", "Availability": "unknown", "CurrentHorizontalResolution": "unknown"}}
    with patch.object(hardware, "os", SimpleNamespace(name="nt", environ={"PSModulePath": "PowerShell7", "keep": "value"})), \
         patch.object(hardware.subprocess, "run", return_value=SimpleNamespace(
             returncode=0, stdout=json.dumps(payload))) as run:
        result = hardware._read_windows_system_info()
    assert result["cpu_name"] == "Ryzen 7 PRO 4750G"
    assert result["cpu_physical_cores"] == 8
    assert result["cpu_max_mhz"] == 0
    assert run.call_args.kwargs["env"] == {"keep": "value"}
    assert run.call_args.kwargs["timeout"] == 8
    assert "UTF8Encoding" in run.call_args.args[0][-1]


def test_failed_probe_has_a_cooldown_and_keeps_registry_identity():
    class ImmediateThread:
        def __init__(self, *, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

    with patch.object(hardware, "os", SimpleNamespace(name="nt")), \
         patch.object(hardware, "_WINDOWS_INFO_CACHE", {}), \
         patch.object(hardware, "_WINDOWS_INFO_REFRESHING", False), \
         patch.object(hardware, "_read_windows_cpu_info", return_value={"cpu_name": "Ryzen 7 PRO 4750G"}), \
         patch.object(hardware, "_read_windows_system_info", return_value={}) as probe, \
         patch.object(hardware.time, "monotonic", return_value=20) as clock, \
         patch.object(hardware.threading, "Thread", ImmediateThread):
        assert hardware._windows_system_info()["cpu_name"] == "Ryzen 7 PRO 4750G"
        hardware._windows_system_info()
        assert probe.call_count == 1
        clock.return_value = 81
        assert hardware._windows_system_info()["cpu_name"] == "Ryzen 7 PRO 4750G"
        assert probe.call_count == 2


def test_completed_static_metadata_reaches_ui_without_gpu_reprobe():
    original = hardware.HardwareCapabilities(False, "", 0, 0, 16 * 1024**3, 16, True, None)
    completed = replace(original, cpu_name="Ryzen 7 PRO 4750G", cpu_physical_cores=8)
    host = SimpleNamespace(_hardware_capabilities=original, _hardware_probe_events=queue.Queue(),
                           hardwareChanged=Mock())
    controller = RuntimeDeviceController(host, detect_hardware=Mock(side_effect=AssertionError("CUDA probe")))
    with patch("haizflow.desktop.runtime_device_controller.refresh_hardware_metadata", return_value=completed):
        controller.drain_hardware_events()
        controller.drain_hardware_events()
    assert host._hardware_capabilities == completed
    host.hardwareChanged.emit.assert_called_once()


def test_cim_timeout_is_bounded_and_returns_no_bad_metadata():
    with patch.object(hardware, "os", SimpleNamespace(name="nt", environ={})), \
         patch.object(hardware.subprocess, "run", side_effect=subprocess.TimeoutExpired("powershell", 8)):
        assert hardware._read_windows_system_info() == {}


def test_failure_to_start_thread_releases_refresh_flag():
    worker = Mock()
    worker.start.side_effect = RuntimeError("thread unavailable")
    with patch.object(hardware, "os", SimpleNamespace(name="nt")), \
         patch.object(hardware, "_WINDOWS_INFO_CACHE", {}), \
         patch.object(hardware, "_WINDOWS_INFO_REFRESHING", False), \
         patch.object(hardware, "_read_windows_cpu_info", return_value={"cpu_name": "Ryzen"}), \
         patch.object(hardware.threading, "Thread", return_value=worker):
        assert hardware._windows_system_info()["cpu_name"] == "Ryzen"
        assert not hardware._WINDOWS_INFO_REFRESHING

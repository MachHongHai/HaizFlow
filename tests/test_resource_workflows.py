"""User-visible pack operations and missing-setup notices stay transactional."""
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QObject, Signal

from haizflow.desktop.resource_pack_controller import ResourcePackController
from haizflow.desktop.resource_progress import gemini_key_notice, missing_resource_notice
from haizflow.services.model_bootstrap import ModelProgress
from haizflow.services.resource_packs import ResourcePackDefinition, ResourcePackManager


class Host(QObject):
    appAlertRequested = Signal(str, str, str)

    def __init__(self):
        super().__init__()
        self._settings_processing_device = "cpu"
        self._settings_language = "vi"
        self._processing_queue = SimpleNamespace(has_work=False)
        self._device_switching = False
        self._smart_warmup = None


@pytest.fixture
def packs(tmp_path, monkeypatch):
    monkeypatch.setenv("HAIZFLOW_HOME", str(tmp_path / "app"))
    monkeypatch.setenv("HAIZFLOW_RESOURCE_ROOT", str(tmp_path / "resources"))
    monkeypatch.setenv("RUNTIME_DATA_DIR", str(tmp_path / "app/data"))
    definitions = [ResourcePackDefinition("engine-test", "Runtime", "processor", "1", "engine", engine_modules=("unavailable_test_module",)),
                   ResourcePackDefinition("model-demucs", "Demucs", "voice", "1", "separation"),
                   ResourcePackDefinition("model-subtitle-ocr", "OCR", "image", "1", "ocr")]
    manager = ResourcePackManager(definitions)
    manager.cleanup_previous_storage = lambda: None
    manager.archive_available = lambda _: True
    states = dict.fromkeys(manager.definitions, "missing")
    manager.status = lambda pack: states[pack]
    host = Host()
    controller = ResourcePackController(host, manager)
    controller._inventory_thread.join(2)
    controller._maintenance_thread.join(2)
    controller.drain_events()
    controller._supporting_packs = lambda _: ["engine-test"]
    yield controller, manager, states
    controller.shutdown()


def finish(controller, pack):
    controller._threads[pack].join(3)
    assert not controller._threads[pack].is_alive()
    controller.drain_events()


def test_pause_runtime_dependency_then_resume_model(packs):
    controller, manager, states = packs
    started, release = threading.Event(), threading.Event()
    calls = []

    def install(unit, report):
        calls.append(unit)
        if len(calls) == 1:
            started.set()
            release.wait(2)
        report(unit, ModelProgress("downloading", "Runtime", "", 1, 2, "transfer"))
        states[unit] = "installed"
        report(unit, ModelProgress("ready", "Runtime", "", 2, 2))

    manager.install = install
    manager.cancel = Mock()
    controller.installResourcePacks(["model-demucs"])
    assert started.wait(1)
    controller.cancelResourcePackOperation("model-demucs")
    manager.cancel.assert_any_call("engine-test")
    release.set()
    finish(controller, "model-demucs")
    assert states["model-demucs"] == "missing"
    assert controller.model._operation_state["model-demucs"]["status"] == "paused"
    controller.installResourcePacks(["model-demucs"])
    finish(controller, "model-demucs")
    assert calls == ["engine-test", "engine-test", "model-demucs"]
    assert states["model-demucs"] == "installed"
    assert "model-demucs" not in controller.model._operation_state


def test_cancel_waiting_model_does_not_cancel_another_models_runtime(packs):
    controller, manager, states = packs
    started, release = threading.Event(), threading.Event()

    def install(unit, report):
        if unit == "engine-test":
            started.set()
            release.wait(2)
        states[unit] = "installed"
        report(unit, ModelProgress("ready", unit, "", 1, 1))

    manager.install = install
    manager.cancel = Mock()
    controller.installResourcePacks(["model-demucs", "model-subtitle-ocr"])
    assert started.wait(1)
    controller.cancelResourcePackOperation("model-subtitle-ocr")
    assert ("engine-test",) not in [call.args for call in manager.cancel.call_args_list]
    release.set()
    finish(controller, "model-demucs")
    finish(controller, "model-subtitle-ocr")
    assert states["model-demucs"] == "installed"
    assert states["model-subtitle-ocr"] == "missing"


def test_shared_runtime_is_installed_once_and_mutations_are_blocked_while_downloading(packs, tmp_path):
    controller, manager, states = packs
    started, release = threading.Event(), threading.Event()
    calls = []

    def install(unit, report):
        calls.append(unit)
        if unit == "engine-test":
            started.set()
            release.wait(2)
        states[unit] = "installed"
        report(unit, ModelProgress("ready", unit, "", 1, 1))

    manager.install = install
    manager.remove = Mock()
    manager.clean_unused = Mock()
    controller.installResourcePacks(["model-demucs", "model-subtitle-ocr"])
    assert started.wait(1)
    assert not controller.removeResourcePack("model-subtitle-ocr")
    assert not controller.moveResourceStorage(str(tmp_path / "moved"))
    controller.cleanUnusedResourcePacks()
    manager.remove.assert_not_called()
    manager.clean_unused.assert_not_called()
    assert not any(row["canInstall"] for row in controller.displayRows)
    release.set()
    finish(controller, "model-demucs")
    finish(controller, "model-subtitle-ocr")
    assert calls == ["engine-test", "model-demucs", "model-subtitle-ocr"]


def test_repair_checks_the_installed_runtime_and_reinstalls_if_broken(packs):
    from haizflow.services.resource_packs import ResourcePackError

    controller, manager, states = packs
    states.update({"engine-test": "installed", "model-demucs": "installed"})
    manager.verify_installed = Mock(side_effect=ResourcePackError("Broken DLL"))
    manager.install = Mock()
    controller.repairResourcePack("model-demucs")
    finish(controller, "model-demucs")
    manager.verify_installed.assert_called_once_with("engine-test")
    assert [call.args[0] for call in manager.install.call_args_list] == ["engine-test", "model-demucs"]


def test_missing_setup_notices_are_bilingual_and_do_not_show_zero_download_as_unknown():
    summary = {"downloadBytes": 0, "requiredBytes": 1024**3}
    title, vi = missing_resource_notice(["engine-cuda128-py313", "model-demucs"], summary, "vi", "Tách giọng")
    assert "--" not in vi and "có sẵn" in vi
    assert "Cài đặt → Gói tài nguyên" in vi
    assert "Download" not in vi
    _, en = missing_resource_notice(["engine-cuda128-py313", "model-demucs"], summary, "en")
    assert "Settings → Resource packs" in en and "Cài đặt" not in en
    assert "API Key → Gemini" in gemini_key_notice("vi")[1]
    assert "Settings → API Key → Gemini" in gemini_key_notice("en")[1]


def test_button_tooltips_are_opt_in_and_setting_help_is_preserved():
    from pathlib import Path

    qml = Path(__file__).resolve().parents[1] / "src/haizflow/desktop/qml"
    for name in ("IconButton.qml", "AppButton.qml"):
        text = (qml / name).read_text(encoding="utf-8")
        assert "property bool showToolTip: false" in text
        assert "Accessible.name:" in text
    assert "HelpPopover" in (qml / "SettingLabel.qml").read_text(encoding="utf-8")
    assert "helpText: root.helpText" in (qml / "SettingLabel.qml").read_text(encoding="utf-8")


def test_zernio_missing_key_notifies_without_navigation():
    from haizflow.desktop.social_publish_controller import SocialPublishController

    host = SimpleNamespace(_settings_language="vi", appAlertRequested=SimpleNamespace(emit=Mock()),
                           apiKeySettingsRequested=SimpleNamespace(emit=Mock()))
    controller = SimpleNamespace(_host=host, _status="")
    SocialPublishController._missing_api_key_notice(controller)
    assert "Cài đặt → API Key → Zernio" in controller._status
    host.appAlertRequested.emit.assert_called_once()
    host.apiKeySettingsRequested.emit.assert_not_called()


def test_cpu_only_demucs_needs_no_cuda_pack_and_gpu_options_are_blocked():
    from haizflow.core.hardware import HardwareCapabilities

    capabilities = HardwareCapabilities(cuda_available=False, cuda_name="", total_vram_bytes=0,
        free_vram_bytes=0, total_ram_bytes=16 * 1024**3, logical_cpu_count=8, ac_powered=True, battery_percent=100)
    host = SimpleNamespace(_settings_processing_device="cpu", _settings_language="vi", _hardware_capabilities=capabilities)
    controller = SimpleNamespace(_host=host, manager=ResourcePackManager())
    controller._display_context = lambda: ResourcePackController._display_context(controller)
    assert ResourcePackController._supporting_packs(controller, "model-demucs") == ["engine-cpu-py313"]
    # Installing either explicit pack must ignore the app's current device.
    assert ResourcePackController._supporting_packs(controller, "model-demucs-gpu") == ["engine-cuda128-py313"]
    host._settings_processing_device = "gpu"
    assert ResourcePackController._supporting_packs(controller, "model-demucs-cpu") == ["engine-cpu-py313"]
    assert ResourcePackController._hardware_compatibility(controller, "engine-cpu-py313")[0]
    assert not ResourcePackController._hardware_compatibility(controller, "model-whisper-turbo")[0]
    assert not ResourcePackController._hardware_compatibility(controller, "model-hymt2-gpu")[0]
    assert not ResourcePackController._hardware_compatibility(controller, "engine-cuda128-py313")[0]
    assert not ResourcePackController._hardware_compatibility(controller, "model-demucs-gpu")[0]


def test_demucs_preflight_follows_app_device_even_with_other_profile_installed(tmp_path, monkeypatch):
    monkeypatch.setenv("HAIZFLOW_RESOURCE_ROOT", str(tmp_path))
    manager = ResourcePackManager()
    installed = {"engine-cuda128-py313", "model-demucs-gpu"}
    monkeypatch.setattr(manager, "status", lambda pack: "installed" if pack in installed else "missing")
    cpu = {"device": "cpu"}
    gpu = {"device": "gpu"}
    assert manager.missing_packs("separation", cpu) == ["engine-cpu-py313", "model-demucs-cpu"]
    assert manager.missing_packs("separation", gpu) == []
    _, text = missing_resource_notice(manager.missing_packs("separation", cpu),
        {"downloadBytes": 0, "requiredBytes": 1024**3}, "vi", "Tách giọng")
    assert "Demucs CPU" in text and "CUDA" not in text
    installed.update({"engine-cpu-py313", "model-demucs-cpu"})
    assert manager.missing_packs("separation", cpu) == []
    assert manager.required_packs("separation", gpu) == ["engine-cuda128-py313", "model-demucs-gpu"]


@pytest.mark.parametrize("device,missing_pack", [("cpu", "model-demucs-cpu"), ("gpu", "model-demucs-gpu")])
def test_manual_separation_missing_pack_stays_in_editor(device, missing_pack, monkeypatch):
    from haizflow.desktop.qml_controller import HaizFlowController
    from haizflow.schemas.video import VideoConfig

    video = SimpleNamespace(**VideoConfig(project_type="manual").model_dump(), video_id="demucs-preflight")
    manager = ResourcePackManager()
    monkeypatch.setattr(manager, "status", lambda pack: "missing" if pack == missing_pack else "installed")
    monkeypatch.setattr(manager, "requirement_summary", lambda _: {"downloadBytes": 0, "requiredBytes": 1024**3})
    host = SimpleNamespace(_settings_processing_device=device, _settings_language="vi", _project_type="manual",
        _selected_video=lambda: video, _ensure_hardware_ready_for_action=lambda: True,
        appAlertRequested=Mock(), resourcePacksRequested=Mock(), _enqueue_video=Mock(),
        _resource_packs=SimpleNamespace(manager=manager, _hardware_compatibility=lambda _: (True, "")))
    assert not HaizFlowController.runManualTool(host, "separation")
    assert ("Demucs CPU" if device == "cpu" else "Demucs GPU NVIDIA") in host.appAlertRequested.emit.call_args.args[1]
    host.resourcePacksRequested.emit.assert_not_called()
    host._enqueue_video.assert_not_called()


@pytest.mark.parametrize("device,model,missing_pack", [
    ("cpu", "small-cpu", "engine-cpu-py313"),
    ("cpu", "small-cpu", "model-whisper-small"),
    ("gpu", "small-gpu", "engine-cuda128-py313"),
    ("gpu", "small-gpu", "model-whisper-small"),
    ("gpu", "large-v3-turbo", "engine-cuda128-py313"),
    ("gpu", "large-v3-turbo", "model-whisper-turbo"),
])
def test_manual_recognition_blocks_missing_runtime_or_model(device, model, missing_pack, monkeypatch):
    from haizflow.desktop.qml_controller import HaizFlowController
    from haizflow.schemas.video import VideoConfig

    video = SimpleNamespace(**VideoConfig(project_type="manual", speech_recognition_model=model,
                            translation_model="gemini-3.1-flash-lite").model_dump(), video_id="whisper-preflight")
    manager = ResourcePackManager()
    monkeypatch.setattr(manager, "status", lambda pack: "missing" if pack == missing_pack else "installed")
    monkeypatch.setattr(manager, "requirement_summary", lambda _: {"downloadBytes": 0, "requiredBytes": 1024**3})
    host = SimpleNamespace(_settings_processing_device=device, _settings_language="vi", _project_type="manual",
        geminiKeyConfigured=True, _selected_video=lambda: video, _ensure_hardware_ready_for_action=lambda: True,
        appAlertRequested=Mock(), resourcePacksRequested=Mock(), _enqueue_video=Mock(),
        _resource_packs=SimpleNamespace(manager=manager, _hardware_compatibility=lambda _: (True, "")))
    assert not HaizFlowController.runManualTool(host, "translation")
    host.appAlertRequested.emit.assert_called_once()
    host.resourcePacksRequested.emit.assert_not_called()
    host._enqueue_video.assert_not_called()


@pytest.mark.parametrize("device,model,missing_pack", [
    ("cpu", "small-cpu", "engine-cpu-py313"),
    ("cpu", "small-cpu", "model-whisper-small"),
    ("gpu", "large-v3-turbo", "engine-cuda128-py313"),
    ("gpu", "large-v3-turbo", "model-whisper-turbo"),
])
def test_auto_batch_recognition_blocks_missing_runtime_or_model(device, model, missing_pack, monkeypatch):
    from haizflow.desktop.project_commands_controller import ProjectCommandsController
    from haizflow.schemas.video import VideoConfig

    video = SimpleNamespace(**VideoConfig(speech_recognition_model=model, translation_model="q4").model_dump(),
                            video_id="auto-whisper-preflight", status="pending")
    manager = ResourcePackManager()
    monkeypatch.setattr(manager, "status", lambda pack: "missing" if pack == missing_pack else "installed")
    monkeypatch.setattr(manager, "requirement_summary", lambda _: {"downloadBytes": 0, "requiredBytes": 1024**3})
    host = SimpleNamespace(_settings_processing_device=device, _settings_language="vi",
        _processing_queue=SimpleNamespace(contains=lambda _: False),
        appAlertRequested=Mock(), resourcePacksRequested=Mock(),
        _resource_packs=SimpleNamespace(manager=manager, _hardware_compatibility=lambda _: (True, "")))
    assert not ProjectCommandsController._resources_ready_for_videos(host, [video])
    host.appAlertRequested.emit.assert_called_once()
    host.resourcePacksRequested.emit.assert_not_called()


def test_downloaded_whisper_model_with_missing_runtime_is_not_shown_installed():
    manager = ResourcePackManager()
    manager.status = lambda pack: "missing" if pack.startswith("engine-") else "installed"
    source = {"packId": "model-whisper-turbo", "status": "installed", "downloadSize": 0, "canRemove": True}
    controller = SimpleNamespace(_host=SimpleNamespace(_settings_language="vi"), manager=manager,
        model=SimpleNamespace(_rows=[source]), busy=False,
        _hardware_compatibility=lambda _: (True, ""), _supporting_packs=lambda _: ["engine-cuda128-py313"])
    manager.archive_available = lambda _: True
    row = ResourcePackController.displayRows.fget(controller)[0]
    assert row["status"] == "missing"
    assert row["canInstall"]
    assert "môi trường xử lý" in row["detail"]


def test_old_whisper_runtime_contract_is_not_ready(tmp_path, monkeypatch):
    import json
    from dataclasses import replace
    from haizflow.services.resource_packs import ENGINE_REQUIRED_COMMANDS

    monkeypatch.setenv("HAIZFLOW_RESOURCE_ROOT", str(tmp_path))
    definition = replace(ResourcePackManager().definitions["engine-cuda128-py313"], version="5", archive_sha256="")
    manager = ResourcePackManager([definition])
    monkeypatch.setattr(manager, "_bundled_engine_available", lambda _: False)
    root = manager._engine_marker(definition).parent
    root.mkdir(parents=True)
    (root / "engine.exe").write_bytes(b"fixture")
    payload = {"pack_id": definition.pack_id, "profile": "cuda128", "version": "5", "protocol_version": 1}
    payload.update({name: ["engine.exe"] for name in ENGINE_REQUIRED_COMMANDS[definition.pack_id]})
    (root / "engine.json").write_text(json.dumps(payload))
    (root / "complete.json").write_text(json.dumps(payload))
    assert manager.status(definition.pack_id) == "missing"
    payload["runtime_contract"] = 2
    (root / "engine.json").write_text(json.dumps(payload))
    assert manager.status(definition.pack_id) == "installed"


def test_demucs_profiles_share_model_but_install_and_remove_independently(tmp_path, monkeypatch):
    import hashlib
    import json
    from haizflow.services.model_bootstrap import ModelAsset

    monkeypatch.setenv("HAIZFLOW_RESOURCE_ROOT", str(tmp_path))
    monkeypatch.setenv("HAIZFLOW_HOME", str(tmp_path))
    monkeypatch.setenv("RUNTIME_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MODELS_DIR", str(tmp_path / "models"))
    payload = b"verified shared checkpoint"
    asset = ModelAsset("demucs", "Demucs", "https://example.invalid/demucs", "demucs/checkpoint.th",
                       len(payload), hashlib.sha256(payload).hexdigest())
    definitions = [ResourcePackDefinition(f"model-demucs-{device}", f"Demucs {device}",
        "separation", "1", "separation", assets=(asset,)) for device in ("cpu", "gpu")]
    manager = ResourcePackManager(definitions)
    model = tmp_path / "models/demucs/checkpoint.th"
    model.parent.mkdir(parents=True)
    model.write_bytes(payload)
    monkeypatch.setattr(manager, "_verify_model_pack", lambda _: None)
    assert manager.status("model-demucs-cpu") == "missing"
    assert manager.status("model-demucs-gpu") == "missing"
    assert manager.download_bytes("model-demucs-cpu") == 0
    manager.install("model-demucs-gpu", lambda *_: None)
    assert manager.status("model-demucs-gpu") == "installed"
    assert manager.status("model-demucs-cpu") == "missing"
    manager.install("model-demucs-cpu", lambda *_: None)
    manager.remove("model-demucs-gpu")
    assert model.read_bytes() == payload
    assert manager.status("model-demucs-cpu") == "installed"
    assert manager.status("model-demucs-gpu") == "missing"
    receipt = model.parent / "profiles/model-demucs-cpu.json"
    assert json.loads(receipt.read_text())["pack_id"] == "model-demucs-cpu"
    manager.remove("model-demucs-cpu")
    assert not model.exists() and not receipt.exists()

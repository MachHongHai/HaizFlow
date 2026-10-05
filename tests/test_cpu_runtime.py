import queue
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.core import hardware
from haizflow.desktop import qml_controller
from haizflow.desktop.runtime_device_controller import RuntimeDeviceController
from haizflow.pipeline import audio_separation
from haizflow.pipeline import manual_tools
from haizflow.services import hymt2_worker
from haizflow.services import desktop_settings
from haizflow.services import translation
from haizflow.utils import ffmpeg


class CpuRuntimeTests(unittest.TestCase):
    def tearDown(self):
        hardware.clear_runtime_profile_cache()
        ffmpeg.available_video_encoders.cache_clear()
        ffmpeg._encoder_works.cache_clear()

    def _profile(
        self,
        *,
        cuda=False,
        vram_gib=8,
        ram_gib=16,
        cpu_count=12,
        preference="gpu",
        bf16=True,
    ):
        hardware.clear_runtime_profile_cache()
        with (
            mock.patch.dict(
                hardware.os.environ,
                {"HAIZFLOW_PROCESSING_DEVICE": preference, "HAIZFLOW_FORCE_CPU": ""},
                clear=False,
            ),
            mock.patch.object(hardware, "_cuda_details", return_value=(cuda, "Test GPU" if cuda else "")),
            mock.patch.object(
                hardware,
                "_cuda_precision_details",
                return_value=((8, 9), bf16) if cuda else ((0, 0), False),
            ),
            mock.patch.object(hardware, "_cuda_memory_bytes", return_value=vram_gib * 1024**3),
            mock.patch.object(hardware, "_cuda_free_memory_bytes", return_value=vram_gib * 1024**3),
            mock.patch.object(hardware, "_total_memory_bytes", return_value=ram_gib * 1024**3),
            mock.patch.object(hardware, "_power_status", return_value=(True, 80)),
            mock.patch.object(hardware.os, "cpu_count", return_value=cpu_count),
        ):
            return hardware.runtime_profile()

    def test_hardware_profiles_are_conservative_on_cpu(self):
        balanced = self._profile(ram_gib=32, cpu_count=16)
        self.assertEqual(balanced.key, "cpu_balanced")
        self.assertEqual(balanced.whisper_batch_size, 4)
        self.assertEqual(balanced.cpu_threads, 8)
        self.assertTrue(balanced.warm_whisper_on_startup)
        self.assertFalse(balanced.warm_hymt2_on_startup)

        low_memory = self._profile(ram_gib=10, cpu_count=8)
        self.assertEqual(low_memory.key, "cpu_low_memory")
        self.assertEqual(low_memory.whisper_batch_size, 2)
        self.assertEqual(low_memory.cpu_threads, 4)

        minimum = self._profile(ram_gib=6, cpu_count=8)
        self.assertEqual(minimum.key, "cpu_minimum")
        self.assertEqual(minimum.whisper_batch_size, 1)
        self.assertFalse(minimum.warm_whisper_on_startup)

    def test_public_processing_requirement_rejects_sub_16gb_systems(self):
        capabilities = hardware.HardwareCapabilities(
            cuda_available=False,
            cuda_name="",
            total_vram_bytes=0,
            free_vram_bytes=0,
            total_ram_bytes=10 * 1024**3,
            logical_cpu_count=8,
            ac_powered=True,
            battery_percent=100,
        )
        compatible, message = hardware.validate_processing_device("cpu", capabilities)
        self.assertFalse(compatible)
        self.assertIn("16 GB", message)

    def test_basic_hardware_snapshot_never_initializes_cuda(self):
        with (
            mock.patch.object(hardware, "_cuda_details") as cuda_details,
            mock.patch.object(hardware, "_cuda_memory_bytes") as cuda_memory,
            mock.patch.object(hardware, "_cuda_free_memory_bytes") as cuda_free_memory,
            mock.patch.object(hardware, "_total_memory_bytes", return_value=16 * 1024**3),
            mock.patch.object(hardware, "_power_status", return_value=(True, 80)),
            mock.patch.object(hardware, "_windows_system_info", return_value={}),
            mock.patch.object(hardware.os, "cpu_count", return_value=12),
        ):
            capabilities = hardware.basic_hardware_capabilities()

        cuda_details.assert_not_called()
        cuda_memory.assert_not_called()
        cuda_free_memory.assert_not_called()
        self.assertFalse(capabilities.cuda_available)
        self.assertEqual(capabilities.logical_cpu_count, 12)

    def test_nvidia_driver_probe_does_not_require_torch(self):
        hardware.clear_runtime_profile_cache()
        with mock.patch.object(
            hardware,
            "_run_nvidia_query",
            return_value=["NVIDIA RTX Test", "12288", "9216", "8.6"],
        ) as query:
            snapshot = hardware._nvidia_snapshot()

        query.assert_called_once()
        self.assertTrue(snapshot.available)
        self.assertEqual(snapshot.total_vram_bytes, 12288 * 1024**2)
        self.assertEqual(snapshot.compute_capability, (8, 6))

    def test_live_hardware_probe_does_not_cache_an_initial_nvidia_failure(self):
        with (
            mock.patch.object(hardware, "_run_nvidia_query", side_effect=[
                [], [], ["NVIDIA RTX Test", "8192", "7168", "8.9"],
            ]) as query,
            mock.patch.object(hardware, "_power_status", return_value=(True, 90)),
            mock.patch.object(hardware, "_windows_system_info", return_value={}),
            mock.patch.object(hardware, "_total_memory_bytes", return_value=16 * 1024**3),
        ):
            self.assertFalse(hardware.detect_hardware_capabilities().cuda_available)
            self.assertTrue(hardware.detect_hardware_capabilities().cuda_available)
        self.assertEqual(query.call_count, 3)

    def test_runtime_profile_can_use_a_cached_snapshot_without_detecting_hardware(self):
        capabilities = hardware.HardwareCapabilities(
            cuda_available=False,
            cuda_name="",
            total_vram_bytes=0,
            free_vram_bytes=0,
            total_ram_bytes=16 * 1024**3,
            logical_cpu_count=12,
            ac_powered=True,
            battery_percent=90,
        )
        with mock.patch.object(hardware, "detect_hardware_capabilities") as detect:
            profile = hardware.runtime_profile_for(capabilities, "cpu")

        detect.assert_not_called()
        self.assertEqual(profile.key, "cpu_balanced")

    def test_live_hardware_refresh_only_schedules_the_expensive_probe(self):
        capabilities = hardware.HardwareCapabilities(
            cuda_available=False,
            cuda_name="",
            total_vram_bytes=0,
            free_vram_bytes=0,
            total_ram_bytes=16 * 1024**3,
            logical_cpu_count=8,
            ac_powered=True,
            battery_percent=70,
        )
        host = SimpleNamespace(
            _hardware_telemetry_active=True,
            _shutdown_started=False,
            _hardware_probe_lock=threading.Lock(),
            _hardware_probe_running=False,
            _hardware_probe_events=queue.Queue(),
        )
        detect = mock.Mock(return_value=capabilities)
        controller = RuntimeDeviceController(host, detect_hardware=detect)
        worker = mock.Mock()
        with mock.patch(
            "haizflow.desktop.runtime_device_controller.threading.Thread",
            return_value=worker,
        ) as thread:
            controller._refresh_live_hardware()

        detect.assert_not_called()
        worker.start.assert_called_once_with()
        thread.call_args.kwargs["target"]()
        detect.assert_called_once_with()
        self.assertEqual(host._hardware_probe_events.get_nowait()["capabilities"], capabilities)

    def test_startup_hardware_probe_selects_gpu_before_model_warmup(self):
        capabilities = hardware.HardwareCapabilities(
            cuda_available=True,
            cuda_name="RTX Test",
            total_vram_bytes=8 * 1024**3,
            free_vram_bytes=7 * 1024**3,
            total_ram_bytes=16 * 1024**3,
            logical_cpu_count=12,
            ac_powered=True,
            battery_percent=80,
        )
        host = SimpleNamespace(
            _hardware_probe_lock=threading.Lock(),
            _hardware_probe_running=False,
            _hardware_probe_events=queue.Queue(),
            _settings_processing_device="cpu",
            _processing_device_origin="detected",
            _settings_theme="graphite",
            _settings_language="en",
            _active_processing_device="cpu",
            _startup_hardware_resolved=False,
            _status_message="Ready",
        )
        controller = RuntimeDeviceController(host, detect_hardware=mock.Mock(return_value=capabilities))
        with (
            mock.patch("haizflow.desktop.runtime_device_controller.configure_processing_device") as configure,
            mock.patch.object(desktop_settings, "save_settings") as save_settings,
        ):
            selected = controller._resolve_startup_processing_device()

        self.assertEqual(selected, "gpu")
        self.assertEqual(host._active_processing_device, "gpu")
        self.assertTrue(host._startup_hardware_resolved)
        configure.assert_called_once_with("gpu")
        save_settings.assert_called_once()
        self.assertEqual(host._hardware_probe_events.get_nowait()["kind"], "startup")

    def test_startup_hardware_probe_retries_transient_nvidia_driver_gap(self):
        unavailable = hardware.HardwareCapabilities(
            cuda_available=False, cuda_name="", total_vram_bytes=0, free_vram_bytes=0,
            total_ram_bytes=16 * 1024**3, logical_cpu_count=12,
            ac_powered=True, battery_percent=80,
            detected_graphics=("NVIDIA GeForce RTX 4060 Laptop GPU",),
        )
        available = hardware.HardwareCapabilities(
            cuda_available=True, cuda_name="RTX 4060", total_vram_bytes=8 * 1024**3,
            free_vram_bytes=7 * 1024**3, total_ram_bytes=16 * 1024**3,
            logical_cpu_count=12, ac_powered=True, battery_percent=80,
        )
        host = SimpleNamespace(
            _hardware_probe_lock=threading.Lock(), _hardware_probe_running=False,
            _hardware_probe_events=queue.Queue(), _settings_processing_device="cpu",
            _processing_device_origin="detected", _settings_theme="graphite",
            _settings_language="vi", _active_processing_device="cpu",
            _startup_hardware_resolved=False, _status_message="Ready",
        )
        detect = mock.Mock(side_effect=[unavailable, available])
        controller = RuntimeDeviceController(host, detect_hardware=detect)
        with (
            mock.patch("haizflow.desktop.runtime_device_controller.time.sleep") as sleep,
            mock.patch("haizflow.desktop.runtime_device_controller.configure_processing_device"),
            mock.patch.object(desktop_settings, "save_settings"),
        ):
            self.assertEqual(controller._resolve_startup_processing_device(), "gpu")
        self.assertEqual(detect.call_count, 2)
        sleep.assert_called_once_with(0.75)

    def test_cuda_profile_keeps_existing_fast_path(self):
        profile = self._profile(cuda=True, vram_gib=12, ram_gib=16, cpu_count=12)
        self.assertEqual(profile.key, "cuda")
        self.assertEqual(profile.hymt2_backend, "transformers")
        self.assertEqual(profile.whisper_batch_size, 16)
        self.assertFalse(profile.warm_hymt2_on_startup)
        self.assertEqual(profile.hymt2_dtype, "bfloat16")

        marketed_eight_gib = self._profile(cuda=True, vram_gib=8, ram_gib=16, cpu_count=12)
        self.assertEqual(marketed_eight_gib.key, "cuda_low_memory")
        self.assertEqual(marketed_eight_gib.hymt2_backend, "transformers")
        self.assertFalse(marketed_eight_gib.warm_hymt2_on_startup)
        self.assertEqual(marketed_eight_gib.translation_idle_seconds, 30)

        older_gpu = self._profile(cuda=True, vram_gib=8, ram_gib=16, cpu_count=12, bf16=False)
        self.assertEqual(older_gpu.hymt2_dtype, "float16")

    def test_device_preference_and_vram_select_the_expected_backend(self):
        forced_cpu = self._profile(cuda=True, vram_gib=8, preference="cpu")
        self.assertFalse(forced_cpu.cuda_available)
        self.assertEqual(forced_cpu.hymt2_backend, "llama_cpp")

        low_vram_gpu = self._profile(cuda=True, vram_gib=6, preference="gpu")
        self.assertFalse(low_vram_gpu.cuda_available)
        self.assertEqual(low_vram_gpu.key, "cpu_balanced")

        unsupported_gpu = self._profile(cuda=True, vram_gib=4, preference="gpu")
        self.assertFalse(unsupported_gpu.cuda_available)

    def test_gpu_capability_does_not_depend_on_transient_free_memory(self):
        hardware.clear_runtime_profile_cache()
        with (
            mock.patch.object(hardware, "_cuda_details", return_value=(True, "Test GPU")),
            mock.patch.object(hardware, "_cuda_precision_details", return_value=((8, 9), True)),
            mock.patch.object(hardware, "_cuda_memory_bytes", return_value=8 * 1024**3),
            mock.patch.object(hardware, "_cuda_free_memory_bytes", return_value=4 * 1024**3),
            mock.patch.object(hardware, "_total_memory_bytes", return_value=16 * 1024**3),
            mock.patch.object(hardware, "_power_status", return_value=(True, 80)),
            mock.patch.object(hardware.os, "cpu_count", return_value=8),
        ):
            compatible, message = hardware.validate_processing_device("gpu")
            capabilities = hardware.detect_hardware_capabilities()

        self.assertTrue(compatible)
        self.assertIn("GPU ready", message)
        self.assertEqual(hardware.recommended_processing_device(capabilities), "gpu")

    def test_gpu_status_reports_low_free_vram_as_advice_not_incompatibility(self):
        capabilities = hardware.HardwareCapabilities(
            cuda_available=True, cuda_name="RTX 4060", total_vram_bytes=8 * 1024**3,
            free_vram_bytes=3 * 1024**3, total_ram_bytes=16 * 1024**3,
            logical_cpu_count=12, ac_powered=False, battery_percent=70,
        )
        host = SimpleNamespace(
            _startup_hardware_resolved=True, _hardware_capabilities=capabilities,
            _settings_language="vi",
        )
        status = qml_controller.HaizFlowController.processingDeviceStatus(host, "gpu")
        self.assertIn("GPU sẵn sàng", status)
        self.assertIn("VRAM trống đang thấp", status)

    def test_device_validation_reports_missing_gpu(self):
        hardware.clear_runtime_profile_cache()
        with (
            mock.patch.object(hardware, "_cuda_details", return_value=(False, "")),
            mock.patch.object(hardware, "_total_memory_bytes", return_value=16 * 1024**3),
            mock.patch.object(hardware.os, "cpu_count", return_value=8),
        ):
            compatible, message = hardware.validate_processing_device("gpu")
        self.assertFalse(compatible)
        self.assertIn("not detected", message)

    def test_invalid_translation_model_is_rejected_without_saving(self):
        controller = SimpleNamespace(
            _settings_processing_device="cpu",
            _is_processing=False,
            _device_switching=False,
            _pipeline_is_active=lambda: False,
        )
        with mock.patch.object(qml_controller.desktop_settings, "save_settings") as save:
            applied = qml_controller.HaizFlowController.applySettings(controller, "dark", "en", "gpu")

        self.assertFalse(applied)
        save.assert_not_called()

    def test_translation_model_change_is_rejected_while_a_video_is_processing(self):
        signal = mock.Mock()
        switch_runtime = mock.Mock()
        controller = SimpleNamespace(
            _settings_processing_device="gpu",
            _settings_theme="dark",
            _settings_language="en",
            _settings_translation_model="auto",
            _processing_device_origin="detected",
            _pending_processing_device="",
            _device_switching=False,
            _pipeline_is_active=lambda: True,
            settingsChanged=signal,
            languageOptionsChanged=signal,
            statusMessageChanged=signal,
            _switch_processing_device=switch_runtime,
        )
        with (
            mock.patch.object(qml_controller.desktop_settings, "save_settings") as save,
            mock.patch.object(qml_controller.QMessageBox, "warning") as warning,
        ):
            applied = qml_controller.HaizFlowController.applySettings(controller, "dark", "en", "q4")

        self.assertFalse(applied)
        self.assertEqual(controller._settings_translation_model, "auto")
        save.assert_not_called()
        warning.assert_called_once()
        switch_runtime.assert_not_called()

    def test_translation_model_change_is_saved_globally_without_device_switch(self):
        signal = mock.Mock()
        controller = SimpleNamespace(
            _settings_processing_device="gpu",
            _settings_translation_model="auto",
            _settings_language="vi",
            _pipeline_is_active=lambda: False,
            _switch_processing_device=mock.Mock(),
            settingsChanged=signal,
            languageOptionsChanged=signal,
            statusMessageChanged=signal,
        )
        saved = {
            "theme": "graphite", "language": "vi", "processing_device": "gpu",
            "processing_device_origin": "detected", "translation_model": "q4",
        }
        with (
            mock.patch.object(qml_controller.desktop_settings, "save_settings", return_value=saved) as save,
            mock.patch.object(translation, "shutdown_hymt2_worker") as shutdown,
            mock.patch("haizflow.desktop.settings_controller._set_ui_language"),
            mock.patch.dict(hardware.os.environ, {}, clear=False),
        ):
            self.assertTrue(qml_controller.HaizFlowController.applySettings(controller, "graphite", "vi", "q4"))
            self.assertEqual(hardware.translation_model_preference(), "q4")
        self.assertEqual(save.call_args.args[0]["translation_model"], "q4")
        self.assertEqual(save.call_args.args[0]["processing_device_origin"], "detected")
        controller._switch_processing_device.assert_not_called()
        shutdown.assert_called_once()

    def test_q4_translation_uses_cpu_engine_on_gpu_profile(self):
        with (
            mock.patch.object(translation, "translation_model_preference", return_value="q4"),
            mock.patch("haizflow.services.resource_packs.installed_engine_command", return_value=["cpu-engine"]) as engine,
        ):
            self.assertEqual(translation._worker_command(), ["cpu-engine"])
        self.assertEqual(engine.call_args.args[2], {"device": "cpu", "translation_model": "q4"})

    def test_full_translation_uses_gpu_engine(self):
        with (
            mock.patch.object(translation, "translation_model_preference", return_value="full"),
            mock.patch("haizflow.services.resource_packs.installed_engine_command", return_value=["gpu-engine"]) as engine,
        ):
            self.assertEqual(translation._worker_command(), ["gpu-engine"])
        self.assertEqual(engine.call_args.args[2], {"device": "gpu", "translation_model": "full"})

    def test_low_memory_gpu_translates_one_prompt_at_a_time(self):
        profile = SimpleNamespace(key="cuda_low_memory", is_cpu_only=False)
        with mock.patch.object(hymt2_worker, "runtime_profile", return_value=profile):
            self.assertEqual(
                list(hymt2_worker._inference_batches(["one", "two", "three"])),
                [(0, 1), (1, 2), (2, 3)],
            )

    def test_q4_model_selection_does_not_import_torch(self):
        profile = SimpleNamespace(key="cuda_low_memory", hymt2_backend="transformers", cuda_available=True, cpu_threads=4)
        llama = mock.Mock(return_value="loaded-q4")
        with (
            mock.patch.object(hymt2_worker, "runtime_profile", return_value=profile),
            mock.patch.object(hymt2_worker, "translation_model_preference", return_value="q4"),
            mock.patch.object(hymt2_worker.importlib.util, "find_spec", return_value=object()),
            mock.patch.object(hymt2_worker, "_cpu_model_path", return_value="model.gguf"),
            mock.patch.object(hymt2_worker, "_prepare_torch_runtime", side_effect=AssertionError("Torch must stay unloaded")),
            mock.patch.object(hymt2_worker, "_emit_diagnostic"),
            mock.patch.object(hymt2_worker, "_emit_event"),
            mock.patch.dict(sys.modules, {"llama_cpp": SimpleNamespace(Llama=llama)}),
        ):
            self.assertEqual(hymt2_worker._load_model("HY-MT2"), ("loaded-q4", None, None, "cpu-gguf"))

    def test_staged_gpu_load_checks_free_ram_before_native_model_loader(self):
        with tempfile.TemporaryDirectory() as temporary:
            checkpoint = Path(temporary) / "model.safetensors"
            checkpoint.write_bytes(b"test checkpoint")
            with mock.patch.object(hymt2_worker, "available_memory_bytes", return_value=1):
                with self.assertRaisesRegex(RuntimeError, "Không đủ RAM trống"):
                    hymt2_worker._require_staged_cuda_memory(temporary)
            with mock.patch.object(hymt2_worker, "available_memory_bytes", return_value=2 * 1024**3):
                hymt2_worker._require_staged_cuda_memory(temporary)
            # A prior successful HY-MT2 GPU load on this 16 GiB Windows host
            # reported ~0.34 GiB physically available while its pageable
            # staging copy and CUDA transfer completed normally.
            with mock.patch.object(hymt2_worker, "available_memory_bytes", return_value=int(0.34 * 1024**3)):
                hymt2_worker._require_staged_cuda_memory(temporary)

    def test_active_manual_translation_strip_never_says_translation_finished(self):
        video = SimpleNamespace(
            status="processing", step="manual_translation", step_detail="Đang dịch phụ đề"
        )
        host = SimpleNamespace(_selected_video=lambda: video, _settings_language="vi")
        label = qml_controller.HaizFlowController.selectedStageLabel.fget(host)
        self.assertEqual(label, "Đang nhận dạng và dịch")

    def test_manual_translation_cache_changes_with_global_model(self):
        video = SimpleNamespace(target_language="vi")
        with mock.patch.object(manual_tools, "recognition_signature", return_value="same-source"):
            with mock.patch.object(manual_tools, "translation_model_signature_parts", return_value=("translation-model:q4",)):
                q4 = manual_tools.translation_signature(video)
            with mock.patch.object(manual_tools, "translation_model_signature_parts", return_value=("translation-model:full",)):
                full = manual_tools.translation_signature(video)
        self.assertNotEqual(q4, full)

    def test_default_translation_model_keeps_legacy_cache_signature(self):
        with mock.patch.dict(hardware.os.environ, {"HAIZFLOW_TRANSLATION_MODEL": "auto"}):
            self.assertEqual(hardware.translation_model_signature_parts(), ())

    def test_desktop_settings_persist_processing_device(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            original_path = desktop_settings.SETTINGS_PATH
            desktop_settings.SETTINGS_PATH = Path(temp_dir) / "desktop-settings.json"
            try:
                saved = desktop_settings.save_settings(
                    {"theme": "dark", "language": "en", "processing_device": "cpu"}
                )
                loaded = desktop_settings.load_settings()
            finally:
                desktop_settings.SETTINGS_PATH = original_path
        self.assertEqual(saved["processing_device"], "cpu")
        self.assertEqual(loaded["processing_device"], "cpu")
        self.assertEqual(saved["theme"], "graphite")
        self.assertEqual(loaded["theme"], "graphite")

    def test_saving_identical_desktop_settings_does_not_create_a_new_temp_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            original_path = desktop_settings.SETTINGS_PATH
            desktop_settings.SETTINGS_PATH = Path(temp_dir) / "desktop-settings.json"
            try:
                settings = {"theme": "dark", "language": "en", "processing_device": "cpu"}
                desktop_settings.save_settings(settings)
                with mock.patch.object(desktop_settings.tempfile, "mkstemp") as make_temp:
                    saved = desktop_settings.save_settings(settings)
            finally:
                desktop_settings.SETTINGS_PATH = original_path

        self.assertEqual(saved["processing_device"], "cpu")
        make_temp.assert_not_called()

    def test_legacy_auto_device_setting_migrates_to_detected_cpu_or_gpu(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "desktop-settings.json"
            settings_path.write_text(
                '{"theme": "dark", "language": "en", "processing_device": "auto"}',
                encoding="utf-8",
            )
            original_path = desktop_settings.SETTINGS_PATH
            desktop_settings.SETTINGS_PATH = settings_path
            try:
                loaded = desktop_settings.load_settings()
                persisted = settings_path.read_text(encoding="utf-8")
            finally:
                desktop_settings.SETTINGS_PATH = original_path

        self.assertEqual(loaded["processing_device"], "cpu")
        self.assertEqual(loaded["processing_device_origin"], "detected")
        self.assertNotIn('"processing_device": "auto"', persisted)
        self.assertEqual(loaded["theme"], "graphite")
        self.assertIn('"graphite"', persisted)

    def test_battery_power_does_not_misclassify_gpu_capability(self):
        hardware.clear_runtime_profile_cache()
        with (
            mock.patch.object(hardware, "_cuda_details", return_value=(True, "Laptop GPU")),
            mock.patch.object(hardware, "_cuda_precision_details", return_value=((8, 9), True)),
            mock.patch.object(hardware, "_cuda_memory_bytes", return_value=8 * 1024**3),
            mock.patch.object(hardware, "_cuda_free_memory_bytes", return_value=7 * 1024**3),
            mock.patch.object(hardware, "_total_memory_bytes", return_value=16 * 1024**3),
            mock.patch.object(hardware, "_power_status", return_value=(False, 72)),
            mock.patch.object(hardware.os, "cpu_count", return_value=8),
        ):
            capabilities = hardware.detect_hardware_capabilities()
            compatible, message = hardware.validate_processing_device("gpu", capabilities)
            recommended = hardware.recommended_processing_device(capabilities)

        self.assertTrue(compatible)
        self.assertIn("GPU ready", message)
        self.assertEqual(recommended, "gpu")

    def test_hymt2_gguf_uses_chat_completion_and_plain_translation(self):
        class FakeLlama:
            def __init__(self):
                self.requests = []

            def create_chat_completion(self, **kwargs):
                self.requests.append(kwargs)
                return {"choices": [{"message": {"content": "Xin chao"}}]}

        model = FakeLlama()
        result = hymt2_worker._translate_prompt_batch(
            model,
            None,
            None,
            "cpu-gguf",
            ["Translate this"],
            ["Hello"],
        )
        self.assertEqual(result, ["Xin chao"])
        self.assertEqual(model.requests[0]["messages"][0]["content"], "Translate this")
        self.assertLessEqual(model.requests[0]["max_tokens"], 24)
        self.assertEqual(model.requests[0]["temperature"], 0.0)

    def test_hymt2_resolves_an_installed_transformers_snapshot_without_network(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot = Path(temp_dir) / "hymt2-transformers"
            snapshot.mkdir()
            for filename in ("config.json", "tokenizer_config.json", "tokenizer.json", "model.safetensors"):
                (snapshot / filename).write_bytes(b"installed")

            with (
                mock.patch("haizflow.config.MODELS_DIR", temp_dir),
                mock.patch("huggingface_hub.snapshot_download") as resolve_snapshot,
                mock.patch("haizflow.core.model_integrity.verify_gpu_model", return_value=snapshot),
            ):
                model_source, local_files_only = hymt2_worker._local_transformers_model_source(
                    "tencent/Hy-MT2-1.8B"
                )

        self.assertEqual(model_source, str(snapshot.resolve()))
        self.assertTrue(local_files_only)
        resolve_snapshot.assert_not_called()

    def test_frozen_hymt2_models_never_download_when_payload_is_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                mock.patch("haizflow.config.MODELS_DIR", temp_dir),
                mock.patch("haizflow.core.paths.bundle_root", return_value=Path(temp_dir)),
                mock.patch("haizflow.core.paths.is_frozen", return_value=True),
                mock.patch("huggingface_hub.hf_hub_download") as cpu_download,
                mock.patch("huggingface_hub.snapshot_download") as gpu_download,
            ):
                with self.assertRaisesRegex(RuntimeError, "CPU is missing"):
                    hymt2_worker._cpu_model_path()
                with self.assertRaisesRegex(RuntimeError, "GPU is missing"):
                    hymt2_worker._local_transformers_model_source("tencent/Hy-MT2-1.8B")

        cpu_download.assert_not_called()
        gpu_download.assert_not_called()

    def test_hymt2_rejects_an_incomplete_sharded_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot = Path(temp_dir) / "snapshot"
            snapshot.mkdir()
            for filename in ("config.json", "tokenizer_config.json", "tokenizer.json"):
                (snapshot / filename).write_text("{}", encoding="utf-8")
            (snapshot / "model.safetensors.index.json").write_text(
                '{"weight_map":{"layer":"missing-00001-of-00002.safetensors"}}',
                encoding="utf-8",
            )
            self.assertFalse(hymt2_worker._transformers_snapshot_complete(snapshot))

            (snapshot / "missing-00001-of-00002.safetensors").write_bytes(b"weights")
            self.assertTrue(hymt2_worker._transformers_snapshot_complete(snapshot))

    def test_hymt2_torch_threading_is_configured_only_once(self):
        fake_torch = SimpleNamespace(
            set_num_threads=mock.Mock(),
            set_num_interop_threads=mock.Mock(),
        )
        original_configured = hymt2_worker._TORCH_THREADING_CONFIGURED
        hymt2_worker._TORCH_THREADING_CONFIGURED = False
        try:
            hymt2_worker._configure_torch_threading(fake_torch)
            hymt2_worker._configure_torch_threading(fake_torch)
        finally:
            hymt2_worker._TORCH_THREADING_CONFIGURED = original_configured

        fake_torch.set_num_threads.assert_called_once_with(1)
        fake_torch.set_num_interop_threads.assert_called_once_with(1)

    def test_hymt2_keeps_existing_interop_pool_when_torch_already_started(self):
        fake_torch = SimpleNamespace(
            set_num_threads=mock.Mock(),
            set_num_interop_threads=mock.Mock(
                side_effect=RuntimeError(
                    "Error: cannot set number of interop threads after parallel work has started"
                )
            ),
        )
        original_configured = hymt2_worker._TORCH_THREADING_CONFIGURED
        hymt2_worker._TORCH_THREADING_CONFIGURED = False
        try:
            hymt2_worker._configure_torch_threading(fake_torch)
            self.assertTrue(hymt2_worker._TORCH_THREADING_CONFIGURED)
        finally:
            hymt2_worker._TORCH_THREADING_CONFIGURED = original_configured

    def test_encoder_selection_probes_hardware_then_falls_back(self):
        with mock.patch.object(
            ffmpeg,
            "_encoder_works",
            side_effect=lambda name: name == "h264_nvenc",
        ):
            encoder, _args = ffmpeg.preferred_video_encoder()
        self.assertEqual(encoder, "h264_nvenc")

        with mock.patch.object(ffmpeg, "_encoder_works", return_value=False):
            encoder, args = ffmpeg.preferred_video_encoder()
        self.assertEqual(encoder, "libx264")
        self.assertIn("veryfast", args)

    def test_encoder_selection_is_independent_from_ai_device(self):
        with mock.patch.object(
            ffmpeg,
            "_encoder_works",
            side_effect=lambda name: name == "h264_qsv",
        ):
            encoder, args = ffmpeg.preferred_video_encoder()

        self.assertEqual(encoder, "h264_qsv")
        self.assertIn("-global_quality", args)

        with mock.patch.object(
            ffmpeg,
            "_encoder_works",
            side_effect=lambda name: name == "h264_amf",
        ):
            encoder, _args = ffmpeg.preferred_video_encoder()
        self.assertEqual(encoder, "h264_amf")

    def test_demucs_cpu_profile_limits_parallel_work(self):
        captured = {}

        class FakeProcess:
            returncode = 0

            def __init__(self, command, **_kwargs):
                captured["command"] = command
                output_root = Path(command[command.index("-o") + 1])
                track_root = output_root / "htdemucs" / "audio"
                track_root.mkdir(parents=True)
                (track_root / "vocals.wav").write_bytes(b"V" * 100)
                (track_root / "no_vocals.wav").write_bytes(b"B" * 100)

            def communicate(self):
                return "", ""

        profile = SimpleNamespace(cuda_available=False, key="cpu_low_memory", cpu_threads=4)
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                mock.patch.object(audio_separation, "runtime_profile", return_value=profile),
                mock.patch.object(audio_separation, "_demucs_model_directory", return_value=Path(temp_dir)),
                mock.patch.object(audio_separation.subprocess, "Popen", FakeProcess),
                mock.patch.object(audio_separation, "communicate_process", return_value=("", "")),
                mock.patch.object(audio_separation, "check_cancellation"),
                mock.patch.object(audio_separation, "log_to_video"),
            ):
                audio_separation.separate_audio(
                    "audio.wav",
                    str(Path(temp_dir) / "out"),
                    "video",
                )

        command = captured["command"]
        self.assertEqual(command[command.index("-j") + 1], "1")
        self.assertEqual(command[command.index("-d") + 1], "cpu")
        self.assertIn("--segment", command)


if __name__ == "__main__":
    unittest.main()

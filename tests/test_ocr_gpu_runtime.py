import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from omegaconf import OmegaConf

from haizflow.pipeline import ocr_runtime as runtime


@pytest.mark.parametrize(
    ("system", "available", "expected"),
    [
        ("win32", [runtime.CPU], runtime.CPU),
        ("win32", [runtime.DML, runtime.CPU], runtime.DML),
        ("win32", [runtime.CUDA, runtime.DML, runtime.CPU], runtime.CUDA),
        ("linux", [runtime.DML, runtime.CPU], runtime.CPU),
        ("linux", [runtime.CUDA, runtime.CPU], runtime.CUDA),
    ],
)
def test_provider_requires_an_installed_execution_provider(system, available, expected):
    with patch.object(runtime.sys, "platform", system):
        assert runtime.preferred_provider(available) == expected


def ort_stub():
    return SimpleNamespace(
        get_available_providers=lambda: [runtime.DML, runtime.CPU],
        SessionOptions=SimpleNamespace,
        ExecutionMode=SimpleNamespace(ORT_SEQUENTIAL="serial"),
    )


def test_gpu_initialisation_failure_falls_back_once_and_reports_reason():
    cpu = MagicMock(return_value="cpu output")
    with (
        patch.dict("sys.modules", {"onnxruntime": ort_stub()}),
        patch.object(runtime.sys, "platform", "win32"),
        patch.object(runtime, "_create_engine", side_effect=[RuntimeError("driver unavailable"), cpu]) as create,
    ):
        engine = runtime.SubtitleOCRRuntime(Path("models"))
        assert engine("frame") == "cpu output"
        assert engine("another frame") == "cpu output"
    assert create.call_count == 2
    assert engine.provider == runtime.CPU
    assert "driver unavailable" in engine.detail


def test_gpu_frame_failure_retries_same_frame_on_cpu_without_retrying_gpu():
    gpu = MagicMock(side_effect=RuntimeError("device removed / OOM"))
    cpu = MagicMock(return_value="cpu output")
    with (
        patch.dict("sys.modules", {"onnxruntime": ort_stub()}),
        patch.object(runtime.sys, "platform", "win32"),
        patch.object(runtime, "_create_engine", side_effect=[gpu, cpu]) as create,
    ):
        engine = runtime.SubtitleOCRRuntime(Path("models"))
        assert engine("frame") == "cpu output"
        assert engine("next") == "cpu output"
    gpu.assert_called_once_with("frame")
    assert cpu.call_args_list[0].args == ("frame",)
    assert create.call_count == 2
    assert engine.provider == runtime.CPU


def test_cpu_failure_is_not_swallowed_or_retried_indefinitely():
    cpu = MagicMock(side_effect=RuntimeError("bad input"))
    ort = SimpleNamespace(get_available_providers=lambda: [runtime.CPU])
    with (
        patch.dict("sys.modules", {"onnxruntime": ort}),
        patch.object(runtime, "_create_engine", return_value=cpu) as create,
    ):
        engine = runtime.SubtitleOCRRuntime(Path("models"))
        with pytest.raises(RuntimeError, match="bad input"):
            engine("frame")
    assert cpu.call_count == create.call_count == 1


def test_custom_sessions_apply_directml_requirements_and_verify_effective_provider():
    sessions, options = [], []

    def session_options():
        result = SimpleNamespace(add_session_config_entry=MagicMock())
        options.append(result)
        return result

    def session(_path, *, sess_options, providers):
        result = SimpleNamespace(
            get_providers=lambda: [item[0] for item in providers], disable_fallback=MagicMock(), providers=providers
        )
        sessions.append(result)
        return result

    class FakeRapidOCR:
        def __init__(self, *, params):
            self.params = params
            self.cfg = self._load_config(None, params)

        def _load_config(self, *_args):
            return OmegaConf.create({"Det": {}, "Cls": {}, "Rec": {}})

    ort = SimpleNamespace(
        SessionOptions=session_options, InferenceSession=session, ExecutionMode=SimpleNamespace(ORT_SEQUENTIAL="serial")
    )
    with (
        patch.dict("sys.modules", {"onnxruntime": ort, "rapidocr": SimpleNamespace(RapidOCR=FakeRapidOCR)}),
        patch.object(runtime.os, "cpu_count", return_value=32),
    ):
        engine = runtime._create_engine(Path("models"), runtime.DML)
    assert engine.cfg.Det.session is sessions[0]
    assert engine.cfg.Rec.session is sessions[2]
    assert [item.providers[0][0] for item in sessions] == [runtime.DML, runtime.CPU, runtime.DML]
    assert sessions[0].providers[0][1] == {"performance_preference": "high_performance", "device_filter": "gpu"}
    assert engine.params["Global.use_cls"] is False
    assert engine.params["Rec.rec_batch_num"] == 4
    for item, expected_provider in zip(options, [runtime.DML, runtime.CPU, runtime.DML]):
        assert item.enable_mem_pattern is (expected_provider == runtime.CPU)
        assert item.execution_mode == "serial"
        assert item.intra_op_num_threads == (8 if expected_provider == runtime.CPU else 4)
        assert item.inter_op_num_threads == 1
        item.add_session_config_entry.assert_any_call("session.intra_op.allow_spinning", "0")
    for item in sessions:
        item.disable_fallback.assert_called_once()


@pytest.mark.parametrize("provider", [runtime.CPU, runtime.DML, runtime.CUDA])
@pytest.mark.parametrize("logical_cpus", [None, 1, 2, 4, 8, 16, 64])
def test_session_policy_bounds_cpu_workers_without_disabling_cpu_memory_planner(provider, logical_cpus):
    ort = SimpleNamespace(SessionOptions=lambda: SimpleNamespace(add_session_config_entry=MagicMock()),
                          ExecutionMode=SimpleNamespace(ORT_SEQUENTIAL="serial"))
    with patch.object(runtime.os, "cpu_count", return_value=logical_cpus):
        options = runtime._session_options(ort, provider)
    assert options.enable_mem_pattern is (provider == runtime.CPU)
    assert options.enable_cpu_mem_arena is False  # Do not retain a growing arena on low-RAM machines.
    assert options.intra_op_num_threads == min(8 if provider == runtime.CPU else 4,
                                              max(1, (logical_cpus or 2) // 2))
    assert options.inter_op_num_threads == 1
    options.add_session_config_entry.assert_any_call("session.intra_op.allow_spinning", "0")


def test_silent_ort_cpu_fallback_is_not_reported_as_gpu():
    class FakeRapidOCR:
        def __init__(self, *, params):
            self._load_config(None, params)

        def _load_config(self, *_args):
            return OmegaConf.create({"Det": {}, "Cls": {}, "Rec": {}})

    ort = SimpleNamespace(
        SessionOptions=lambda: SimpleNamespace(add_session_config_entry=MagicMock()),
        InferenceSession=lambda *_args, **_kwargs: SimpleNamespace(get_providers=lambda: [runtime.CPU]),
        ExecutionMode=SimpleNamespace(ORT_SEQUENTIAL="serial"),
    )
    with patch.dict("sys.modules", {"onnxruntime": ort, "rapidocr": SimpleNamespace(RapidOCR=FakeRapidOCR)}):
        with pytest.raises(RuntimeError, match="failed to initialise"):
            runtime._create_engine(Path("models"), runtime.DML)


def test_vision_dependency_does_not_install_two_ort_variants():
    root = Path(__file__).resolve().parents[1]
    lock = (root / "requirements-lock-engine-vision-py313-win64.txt").read_text("utf-8")
    assert "\nonnxruntime-directml==1.24.4" in lock
    assert "\nonnxruntime==" not in lock
    assert "\nonnxruntime-gpu==" not in lock
    script = (root / "scripts/build-resource-engine.ps1").read_text("utf-8")
    assert '"--collect-binaries", "onnxruntime"' in script
    assert '"--copy-metadata", "onnxruntime-directml"' in script
    assert "Vision engine is missing DirectML support" in script


def test_valid_region_cache_does_not_initialise_cpu_or_gpu(tmp_path):
    from haizflow.pipeline import subtitle_ocr

    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    region = {"x_percent": 25, "y_percent": 75, "width_percent": 50, "height_percent": 5}
    (tmp_path / "original_subtitle_region.json").write_text(
        json.dumps(
            {
                "version": subtitle_ocr.DETECTOR_CACHE_VERSION,
                "source": subtitle_ocr._source_state(str(source)),
                "region": region,
            }
        ),
        "utf-8",
    )
    with patch.object(subtitle_ocr, "_ocr_engine") as engine:
        assert subtitle_ocr.detect_original_subtitle_region(str(source), str(tmp_path), "test") == region
    engine.assert_not_called()


def test_model_integrity_failure_is_not_hidden_as_gpu_fallback():
    from haizflow.pipeline import subtitle_ocr

    subtitle_ocr._ocr_engine.cache_clear()
    with (
        patch.object(subtitle_ocr, "verify_subtitle_ocr_models", side_effect=RuntimeError("checksum mismatch")),
        patch.object(runtime, "SubtitleOCRRuntime") as engine,
    ):
        with pytest.raises(RuntimeError, match="checksum mismatch"):
            subtitle_ocr._ocr_engine()
    engine.assert_not_called()
    assert subtitle_ocr._ocr_engine.cache_info().currsize == 0


def test_notice_collector_keeps_native_third_party_notices(tmp_path):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("ocr_notices", root / "scripts/generate-third-party-notices.py")
    notices = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(notices)
    source = tmp_path / "package"
    source.mkdir()
    for name in ("LICENSE", "ThirdPartyNotices.txt"):
        (source / name).write_text(name + " native legal terms", "utf-8")
    distribution = SimpleNamespace(
        files=[Path("LICENSE"), Path("ThirdPartyNotices.txt")], locate_file=lambda entry: source / entry
    )
    assert notices._copy_distribution_licenses(distribution, tmp_path / "collected") == [
        "LICENSE",
        "ThirdPartyNotices.txt",
    ]
    assert "MICROSOFT SOFTWARE LICENSE TERMS" in (root / "licenses/DirectML-1.15.4-LICENSE.txt").read_text("utf-8")

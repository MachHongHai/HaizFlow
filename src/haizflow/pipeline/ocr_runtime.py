"""Small, isolated ONNX OCR runtime with verified GPU sessions and CPU recovery."""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

CPU = "CPUExecutionProvider"
CUDA = "CUDAExecutionProvider"
DML = "DmlExecutionProvider"


def preferred_provider(available: list[str]) -> str:
    if CUDA in available:
        return CUDA
    if sys.platform == "win32" and DML in available:
        return DML
    return CPU


def _session_options(ort):
    options = ort.SessionOptions()
    options.log_severity_level = 3
    options.intra_op_num_threads = min(4, max(1, (os.cpu_count() or 2) // 2))
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    # DirectML requires sequential execution and no memory-pattern optimiser.
    options.enable_mem_pattern = False
    options.enable_cpu_mem_arena = False
    options.add_session_config_entry("session.intra_op.allow_spinning", "0")
    options.add_session_config_entry("session.inter_op.allow_spinning", "0")
    return options


def _provider_options(provider: str) -> dict:
    if provider == DML:
        # Adapter 0 is often a laptop's integrated display GPU. Let DXCore
        # select the high-performance hardware GPU, never a software adapter.
        return {"performance_preference": "high_performance", "device_filter": "gpu"}
    if provider == CUDA:
        return {
            "device_id": 0,
            "gpu_mem_limit": 768 * 1024**2,
            "arena_extend_strategy": "kSameAsRequested",
            "cudnn_conv_algo_search": "HEURISTIC",
        }
    return {}


def _create_engine(model_dir: Path, provider: str):
    import onnxruntime as ort
    from omegaconf import flag_override
    from rapidocr import RapidOCR

    class LocalSubtitleOCR(RapidOCR):
        def _load_config(self, config_path, params):
            cfg = super()._load_config(config_path, params)
            # RapidOCR 3.8.1 supports pre-built sessions. Supply these locally
            # instead of monkey-patching ORT or its process-wide defaults.
            with flag_override(cfg, "allow_objects", True):
                for stage, filename in (("Det", "det"), ("Cls", "cls"), ("Rec", "rec")):
                    selected = CPU if stage == "Cls" else provider  # Classifier is disabled.
                    providers = [(selected, _provider_options(selected))]
                    if selected != CPU:
                        providers.append((CPU, {}))
                    session = ort.InferenceSession(
                        str(model_dir / f"subtitle-{filename}.onnx"),
                        sess_options=_session_options(ort),
                        providers=providers,
                    )
                    if selected not in session.get_providers():
                        raise RuntimeError(f"OCR {stage}: {selected} failed to initialise; CPU was selected by ORT.")
                    # Own recovery at the OCR-frame boundary, not ORT's generic
                    # retry which can silently re-enable a failed GPU session.
                    session.disable_fallback()
                    cfg[stage].session = session
            return cfg

    return LocalSubtitleOCR(
        params={
            "Global.model_root_dir": str(model_dir),
            "Global.use_cls": False,
            "Global.log_level": "error",
            "Rec.rec_batch_num": 4,
            "Det.model_path": str(model_dir / "subtitle-det.onnx"),
            "Rec.model_path": str(model_dir / "subtitle-rec.onnx"),
            "Cls.model_path": str(model_dir / "subtitle-cls.onnx"),
        }
    )


class SubtitleOCRRuntime:
    """Reuse one serial inference runtime; retry a failed GPU frame once on CPU."""

    def __init__(self, model_dir: Path):
        import onnxruntime as ort

        self._model_dir = model_dir
        self._lock = threading.Lock()
        self.provider = preferred_provider(ort.get_available_providers())
        self.fallback_reason = ""
        try:
            self._engine = _create_engine(model_dir, self.provider)
        except Exception as exc:
            if self.provider == CPU:
                raise
            self._fall_back(exc)

    @property
    def detail(self) -> str:
        detail = f"OCR inference: {self.provider} (bounded CPU preprocessing/postprocessing)."
        if self.fallback_reason:
            detail += f" GPU unavailable; CPU fallback: {self.fallback_reason}"
        return detail

    def _fall_back(self, error: Exception) -> None:
        # Drop GPU references before creating CPU sessions, including after OOM.
        self._engine = None
        self.provider = CPU
        self.fallback_reason = str(error).replace("\n", " ")[:400]
        # An exception traceback can retain the failed RapidOCR/session object
        # even after self._engine is cleared. Release it before CPU allocation.
        error.__traceback__ = None
        error.__context__ = None
        error.__cause__ = None
        self._engine = _create_engine(self._model_dir, CPU)

    def __call__(self, image_path: str):
        with self._lock:
            try:
                return self._engine(image_path)
            except Exception as exc:
                if self.provider == CPU:
                    raise
                self._fall_back(exc)
                return self._engine(image_path)

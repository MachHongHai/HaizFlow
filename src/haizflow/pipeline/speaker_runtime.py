"""Bounded ONNX inference owned by the isolated speaker worker, not Qt."""

from __future__ import annotations

from pathlib import Path


class SpeakerSession:
    def __init__(self, model: Path, report=None):
        import onnxruntime as ort

        self.ort = ort
        self.model = model
        self.report = report
        self.device = "cpu"
        self.fallback_reason = ""
        self.options = ort.SessionOptions()
        self.options.intra_op_num_threads = 2
        self.options.inter_op_num_threads = 1
        self.options.log_severity_level = 3
        # Real-media cold benchmarks favor CPU for this small sequential model.
        # Do not load Torch/CUDA or occupy VRAM needed by Whisper and OmniVoice.
        self.session = ort.InferenceSession(str(model), sess_options=self.options, providers=["CPUExecutionProvider"])
        if report:
            report("cpu", "")

    def run(self, features):
        return self.session.run(None, {"feats": features})

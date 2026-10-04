"""The built-in speaker model never loads CUDA, even if it is available."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from haizflow.pipeline.speaker_runtime import SpeakerSession


def test_cpu_session_has_bounded_threads_and_never_loads_cuda():
    session = Mock()
    ort = SimpleNamespace(SessionOptions=Mock(), InferenceSession=Mock(return_value=session), preload_dlls=Mock())
    report = Mock()
    with patch.dict(sys.modules, {"onnxruntime": ort}):
        worker = SpeakerSession(Path("fixture.onnx"), report)
        worker.run("features")
    assert worker.device == "cpu"
    assert ort.InferenceSession.call_args.kwargs["providers"] == ["CPUExecutionProvider"]
    assert ort.SessionOptions.return_value.intra_op_num_threads == 2
    assert ort.SessionOptions.return_value.inter_op_num_threads == 1
    ort.preload_dlls.assert_not_called()
    report.assert_called_once_with("cpu", "")
    session.run.assert_called_once_with(None, {"feats": "features"})


def test_cpu_failure_is_not_hidden_by_repeated_retries():
    session = Mock()
    session.run.side_effect = ValueError("bad input")
    ort = SimpleNamespace(SessionOptions=Mock(), InferenceSession=Mock(return_value=session))
    with patch.dict(sys.modules, {"onnxruntime": ort}):
        worker = SpeakerSession(Path("fixture.onnx"))
        with pytest.raises(ValueError, match="bad input"):
            worker.run("invalid features")
    assert ort.InferenceSession.call_count == 1

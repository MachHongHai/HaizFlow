"""Export-stage progress uses actual copy/encoder work, not time guesses."""
from pathlib import Path
from unittest.mock import patch

import pytest
import shutil

from haizflow.pipeline import sequence_compiler as compiler
from haizflow.utils.ffmpeg import _binary


def test_video_copy_reports_real_bytes_and_cancellation(tmp_path):
    source, target = tmp_path / "source.mp4", tmp_path / "target.mp4"
    source.write_bytes(b"data" * 2500000)
    progress = []
    compiler._copy_video(source, target, "copy-progress", progress.append)
    assert target.read_bytes() == source.read_bytes()
    assert progress == sorted(progress) and progress[-1] == 1
    with pytest.raises(shutil.SameFileError):
        compiler._copy_video(source, source, "copy-progress")
    assert source.read_bytes() == b"data" * 2500000
    with patch.object(compiler, "check_cancellation", side_effect=RuntimeError("cancelled")):
        with pytest.raises(RuntimeError, match="cancelled"):
            compiler._copy_video(source, target, "copy-progress", progress.append)


def test_encoder_stage_reports_measured_work_and_removes_monitor_file(tmp_path):
    progress = []
    compiler._run([
        _binary("ffmpeg"), "-y", "-re", "-f", "lavfi", "-i", "color=s=64x64:r=10:d=2",
        "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", str(tmp_path / "video.mp4"),
    ], cwd=str(tmp_path), process_id="progress-test", label="Progress test",
        progress_callback=progress.append, duration=2)
    assert progress == sorted(progress)
    assert any(0 < value < 1 for value in progress)
    assert progress[-1] == 1
    assert not list(tmp_path.glob(".sequence-progress-*"))


def test_preparation_uses_busy_indicator_not_a_stalled_five_percent_label():
    qml = (Path(__file__).parents[1] / "src/haizflow/desktop/qml/ManualToolProgress.qml").read_text(encoding="utf-8")
    assert 'stepId === "manual_export_preparing"' in qml
    assert "indeterminate: !root.measured" in qml
    assert 'stepId === "manual_export_preparing" ? I18n.progressDetail(detail)' in qml

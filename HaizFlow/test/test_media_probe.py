import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.desktop.media_probe import VideoDimensionProbe
from haizflow.utils import ffmpeg


class MediaProbeTests(unittest.TestCase):
    def test_dimension_probe_runs_off_thread_and_returns_once(self):
        ready = threading.Event()
        results = []
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "clip.mp4"
            path.write_bytes(b"source")
            with patch("haizflow.desktop.media_probe.get_video_dimensions", return_value=(1920, 1080)) as probe:
                worker = VideoDimensionProbe(lambda *result: (results.append(result), ready.set()), workers=1)
                worker.request("video-1", str(path))
                self.assertTrue(ready.wait(2.0))
                worker.shutdown()

        self.assertEqual(results, [("video-1", 1920, 1080)])
        probe.assert_called_once_with(str(path), timeout_seconds=15)

    def test_ffprobe_dimension_call_has_a_timeout(self):
        completed = type("Completed", (), {"stdout": "1920,1080\n"})()
        with patch.object(ffmpeg.subprocess, "run", return_value=completed) as run:
            self.assertEqual(ffmpeg.get_video_dimensions("clip.mp4", timeout_seconds=7), (1920, 1080))

        self.assertEqual(run.call_args.kwargs["timeout"], 7.0)


if __name__ == "__main__":
    unittest.main()

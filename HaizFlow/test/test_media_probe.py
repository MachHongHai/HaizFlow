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

    def test_shutdown_does_not_wait_for_an_active_probe(self):
        started = threading.Event()
        release = threading.Event()

        def blocked_probe(*_args, **_kwargs):
            started.set()
            release.wait(2.0)
            return 1920, 1080

        with patch("haizflow.desktop.media_probe.get_video_dimensions", side_effect=blocked_probe):
            worker = VideoDimensionProbe(lambda *_result: None, workers=1)
            worker.request("video-1", "clip.mp4")
            self.assertTrue(started.wait(1.0))
            worker.shutdown()
            self.assertTrue(all(thread.daemon for thread in worker._workers))
            self.assertTrue(worker._shutdown.is_set())
            release.set()

    def test_ffprobe_dimension_call_has_a_timeout(self):
        completed = type("Completed", (), {"stdout": "1920,1080\n"})()
        with patch.object(ffmpeg.subprocess, "run", return_value=completed) as run:
            self.assertEqual(ffmpeg.get_video_dimensions("clip.mp4", timeout_seconds=7), (1920, 1080))

        self.assertEqual(run.call_args.kwargs["timeout"], 7.0)

    def test_ffprobe_duration_call_has_a_timeout(self):
        completed = type("Completed", (), {"stdout": "42.5\n"})()
        with patch.object(ffmpeg.subprocess, "run", return_value=completed) as run:
            self.assertEqual(ffmpeg.get_video_duration("clip.mp4", timeout_seconds=9), 42.5)

        self.assertEqual(run.call_args.kwargs["timeout"], 9.0)
        self.assertTrue(str(run.call_args.args[0][0]).lower().endswith("ffprobe.exe"))

    def test_integrity_scan_rejects_a_truncated_source(self):
        completed = type("Completed", (), {"returncode": 1, "stderr": "Invalid NAL unit"})()
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch.object(ffmpeg.subprocess, "run", return_value=completed) as run,
        ):
            path = Path(temp_dir) / "clip.mp4"
            path.write_bytes(b"not-empty")
            with self.assertRaisesRegex(RuntimeError, "incomplete or corrupted"):
                ffmpeg.validate_video_integrity(str(path), timeout_seconds=31)

        command = run.call_args.args[0]
        self.assertIn("-xerror", command)
        self.assertEqual(run.call_args.kwargs["timeout"], 31.0)

    def test_integrity_scan_accepts_a_complete_source(self):
        completed = type("Completed", (), {"returncode": 0, "stderr": ""})()
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            ffmpeg.subprocess, "run", return_value=completed
        ):
            path = Path(temp_dir) / "clip.mp4"
            path.write_bytes(b"complete")
            ffmpeg.validate_video_integrity(str(path))


if __name__ == "__main__":
    unittest.main()

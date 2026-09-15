import os
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.desktop.media_download_controller import MediaDownloadController, _safe_output_stem
from haizflow.services.video_download import DownloadCancelled


class MediaDownloadQueueTests(unittest.TestCase):
    def test_audio_title_is_safe_for_windows_filenames(self):
        self.assertEqual(
            _safe_output_stem('Review: "A/B" | final?*'),
            "Review_ _A_B_ _ final__",
        )
        self.assertEqual(_safe_output_stem("CON"), "_CON")
        self.assertEqual(_safe_output_stem("...", "audio"), "audio")

    def test_concurrent_channel_saves_cannot_choose_the_same_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir()
            first = root / "one" / "same.mp4"
            second = root / "two" / "same.mp4"
            first.parent.mkdir()
            second.parent.mkdir()
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            controller = MediaDownloadController()
            try:
                barrier = threading.Barrier(2)

                def move(source):
                    barrier.wait(timeout=2)
                    return controller._move_to_unique_path(source, output / "same.mp4")

                with ThreadPoolExecutor(max_workers=2) as executor:
                    destinations = list(executor.map(move, (first, second)))

                self.assertEqual({path.name for path in destinations}, {"same.mp4", "same (2).mp4"})
                self.assertEqual(
                    {path.read_bytes() for path in destinations},
                    {b"first", b"second"},
                )
            finally:
                controller.shutdown()

    def test_local_audio_extraction_can_be_cancelled_while_ffmpeg_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "audio.m4a"
            controller = MediaDownloadController()
            process = mock.Mock(returncode=None)

            def still_running(timeout=None):
                if timeout is None:
                    return "", ""
                controller._cancel.set()
                raise subprocess.TimeoutExpired("ffmpeg", timeout)

            process.communicate.side_effect = still_running
            with mock.patch(
                "haizflow.desktop.media_download_controller.subprocess.Popen",
                return_value=process,
            ):
                with self.assertRaisesRegex(DownloadCancelled, "cancelled"):
                    controller._extract("source.mp4", destination)

            process.kill.assert_called_once_with()
            self.assertFalse(destination.exists())

    def test_preview_and_channel_scan_do_not_require_an_output_folder(self):
        controller = MediaDownloadController()
        try:
            with (
                mock.patch.object(controller._video_preview, "begin") as begin,
                mock.patch.object(controller._video_preview, "inspect") as inspect,
                mock.patch.object(controller, "_start_channel_scan") as start_channel_scan,
            ):
                controller.inspectVideo("https://www.bilibili.com/video/BV1xx411c7mD")
                controller.inspectChannel(
                    "https://www.youtube.com/@creator", "youtube", "newest", 20, "all", 0,
                )

            begin.assert_called_once_with("single")
            inspect.assert_called_once_with("https://www.bilibili.com/video/BV1xx411c7mD")
            start_channel_scan.assert_called_once()
            self.assertEqual(controller._active_task["output"], "")
        finally:
            controller.shutdown()

    def test_video_and_audio_requests_are_serialized_in_submission_order(self):
        with tempfile.TemporaryDirectory() as output:
            controller = MediaDownloadController()
            try:
                with mock.patch.object(controller, "_run") as run:
                    controller._queue_download("video-one", "video", output, "video download")
                    controller._worker_thread.join(timeout=1)
                    controller._queue_download("audio-two", "audio", output, "audio download")

                    self.assertTrue(controller.busy)
                    self.assertEqual(controller.queueCount, 1)
                    self.assertEqual(run.call_args.args, ("video-one", "video", output))

                    controller._set_finished(os.path.join(output, "one.mp4"))
                    controller._worker_thread.join(timeout=1)
                    self.assertTrue(controller.busy)
                    self.assertEqual(controller.queueCount, 0)
                    self.assertEqual(run.call_args.args, ("audio-two", "audio", output))

                    controller._set_finished(os.path.join(output, "two.m4a"))
                    self.assertFalse(controller.hasWork)
            finally:
                controller.shutdown()


if __name__ == "__main__":
    unittest.main()

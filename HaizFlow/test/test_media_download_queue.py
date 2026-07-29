import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.desktop.media_download_controller import MediaDownloadController


class MediaDownloadQueueTests(unittest.TestCase):
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
